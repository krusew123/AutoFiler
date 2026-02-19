# src/gui/review_tab.py
"""Two-phase review interface with state machine."""

import os
import pathlib
import threading
import tkinter as tk
from tkinter import ttk

from src.review_queue import ReviewQueue
from src.review_engine import (
    classify_review_file,
    diagnose_classification,
    attempt_extraction,
    diagnose_extraction,
    stage_file,
)
from src.config_learner import (
    add_keywords_to_type,
    add_patterns_to_type,
    add_extraction_patterns,
    add_entity_reference,
    add_alias_to_entity,
    get_entity_names,
)


# State machine states
IDLE = "IDLE"
CLASSIFYING = "CLASSIFYING"
PHASE_A = "PHASE_A"
DIAGNOSING_A = "DIAGNOSING_A"
LEARNING_A = "LEARNING_A"
EXTRACTING = "EXTRACTING"
PHASE_B = "PHASE_B"
DIAGNOSING_B = "DIAGNOSING_B"
LEARNING_B = "LEARNING_B"
RE_EXTRACTING = "RE_EXTRACTING"
MANUAL_ENTRY = "MANUAL_ENTRY"
STAGING = "STAGING"
DONE = "DONE"


class ReviewTab(tk.Frame):
    """Two-phase review tab with file list and content panel."""

    def __init__(self, parent, ctx, on_define_new=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.root = ctx["root"]
        self.config = ctx["config"]
        self.af_logger = ctx["logger"]
        self.on_define_new = on_define_new

        settings = self.config.settings
        self.review_queue = ReviewQueue(
            settings["review_path"], settings["config_path"]
        )

        # Current state
        self._state = IDLE
        self._current_file = None
        self._classification = None
        self._scored_candidates = None
        self._extracted_text = None
        self._assigned_type = None
        self._extraction_result = None
        self._gap_analysis = None
        self._learning_record = {
            "keywords_added": [],
            "patterns_added": [],
            "extraction_patterns_added": {},
            "entities_added": [],
        }

        # Paused context for Define tab handoff
        self._paused_context = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resume_with_type(self, type_name, file_path):
        """Called when returning from Define tab with a new type."""
        if type_name and file_path:
            # Restore context and advance
            self._current_file = file_path
            self._assigned_type = type_name
            self._select_file_in_tree(file_path)
            self._set_state(DIAGNOSING_A)
            self._run_diagnosis_a()
        elif file_path:
            # Cancel — return to phase A
            self._current_file = file_path
            self._select_file_in_tree(file_path)
            self._set_state(PHASE_A)
            self._show_phase_a()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # --- Top bar ---
        top = tk.Frame(self, padx=8, pady=6)
        top.pack(fill=tk.X)

        tk.Button(top, text="Scan Queue", command=self._scan_queue).pack(
            side=tk.LEFT)
        self._queue_label = tk.Label(top, text="Queue: not scanned",
                                     font=("Courier", 9))
        self._queue_label.pack(side=tk.LEFT, padx=(12, 0))

        # --- Main paned window ---
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        # Left: file list
        left = tk.Frame(paned, width=200)
        paned.add(left, weight=0)

        self._tree = ttk.Treeview(left, columns=("phase",), show="tree headings",
                                  selectmode="browse")
        self._tree.heading("#0", text="File")
        self._tree.heading("phase", text="Ph")
        self._tree.column("#0", width=160, minwidth=120)
        self._tree.column("phase", width=30, minwidth=30, anchor="center")
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_file_select)

        # Right: content panel
        self._content_frame = tk.Frame(paned)
        paned.add(self._content_frame, weight=1)

        # --- Status bar ---
        self._status_var = tk.StringVar(value="Idle")
        status_bar = tk.Label(self, textvariable=self._status_var,
                              font=("Courier", 9), anchor="w",
                              relief=tk.SUNKEN, padx=6)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 4))

    # ------------------------------------------------------------------
    # Queue scanning
    # ------------------------------------------------------------------

    def _scan_queue(self):
        self.review_queue.scan()
        self._refresh_tree()

    def _refresh_tree(self):
        self._tree.delete(*self._tree.get_children())
        pending = self.review_queue.pending()
        for fp in pending:
            name = pathlib.Path(fp).name
            info = self.review_queue.get_file_info(fp)
            phase = info.get("phase", "A") if info else "A"
            self._tree.insert("", "end", iid=fp, text=name,
                              values=(phase,))
        summary = self.review_queue.summary()
        self._queue_label.config(
            text=f"Queue: {summary['pending']} pending, "
                 f"{summary['resolved']} resolved"
        )

    def _select_file_in_tree(self, file_path):
        """Programmatically select a file in the tree."""
        if self._tree.exists(file_path):
            self._tree.selection_set(file_path)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, state):
        self._state = state
        file_name = (pathlib.Path(self._current_file).name
                     if self._current_file else "")
        self._status_var.set(f"{state} — {file_name}")

    def _on_file_select(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        file_path = sel[0]
        if self._state not in (IDLE, DONE) and file_path != self._current_file:
            return  # Don't switch mid-review
        self._current_file = file_path
        self._reset_review_state()
        self.review_queue.mark_in_review(file_path)
        self._set_state(CLASSIFYING)
        self._run_classification()

    def _reset_review_state(self):
        self._classification = None
        self._scored_candidates = None
        self._extracted_text = None
        self._assigned_type = None
        self._extraction_result = None
        self._gap_analysis = None
        self._learning_record = {
            "keywords_added": [],
            "patterns_added": [],
            "extraction_patterns_added": {},
            "entities_added": [],
        }

    # ------------------------------------------------------------------
    # Content panel helpers
    # ------------------------------------------------------------------

    def _clear_content(self):
        for widget in self._content_frame.winfo_children():
            widget.destroy()

    def _show_processing(self, message):
        self._clear_content()
        tk.Label(self._content_frame, text=message,
                 font=("Courier", 10)).pack(pady=20)

    # ------------------------------------------------------------------
    # CLASSIFYING
    # ------------------------------------------------------------------

    def _run_classification(self):
        self._show_processing("Classifying file...")

        def task():
            try:
                result = classify_review_file(self._current_file, self.config)
                self.root.after(0, lambda: self._on_classification_done(result))
            except Exception as e:
                self.root.after(
                    0, lambda: self._show_error(f"Classification error: {e}")
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_classification_done(self, result):
        self._classification = result["classification"]
        self._scored_candidates = result["scored_candidates"]
        self._extracted_text = result["extracted_text"]

        if result["best_type"]:
            self._assigned_type = result["best_type"]

        self._set_state(PHASE_A)
        self._show_phase_a()

    # ------------------------------------------------------------------
    # PHASE A — Classification Review
    # ------------------------------------------------------------------

    def _show_phase_a(self):
        self._clear_content()
        f = self._content_frame

        tk.Label(f, text="Phase A — Classification Review",
                 font=("Courier", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 4))

        # Show scored candidates summary
        if self._scored_candidates:
            cand_frame = tk.LabelFrame(f, text="Scored Candidates", padx=6, pady=4)
            cand_frame.pack(fill=tk.X, padx=8, pady=4)
            for tname, data in sorted(
                self._scored_candidates.items(),
                key=lambda x: x[1]["score"], reverse=True
            ):
                signals = ", ".join(data["matched_signals"])
                tk.Label(cand_frame,
                         text=f"  {tname}: {data['score']:.2f}  ({signals})",
                         font=("Courier", 9), anchor="w").pack(
                    fill=tk.X)

        # Type assignment
        assign_frame = tk.Frame(f)
        assign_frame.pack(fill=tk.X, padx=8, pady=8)

        tk.Label(assign_frame, text="Assign type:",
                 font=("Courier", 9, "bold")).pack(side=tk.LEFT)

        types = self.config.type_definitions.get("types", {})
        type_names = sorted(t for t in types.keys() if t != "unknown")
        self._type_var = tk.StringVar(
            value=self._assigned_type if self._assigned_type else ""
        )
        combo = ttk.Combobox(assign_frame, textvariable=self._type_var,
                             values=type_names, state="readonly", width=25)
        combo.pack(side=tk.LEFT, padx=6)

        tk.Button(assign_frame, text="Confirm Type",
                  command=self._confirm_type).pack(side=tk.LEFT, padx=4)
        tk.Button(assign_frame, text="Define New Type",
                  command=self._define_new_type).pack(side=tk.LEFT, padx=4)

        # Text preview
        preview_frame = tk.LabelFrame(f, text="Extracted Text Preview",
                                      padx=6, pady=4)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        preview = tk.Text(preview_frame, height=10, font=("Courier", 8),
                          wrap=tk.WORD, state=tk.NORMAL)
        preview.insert("1.0", (self._extracted_text or "")[:3000])
        preview.config(state=tk.DISABLED)
        preview.pack(fill=tk.BOTH, expand=True)

    def _confirm_type(self):
        selected = self._type_var.get()
        if not selected:
            return
        self._assigned_type = selected
        self.review_queue.set_review_reason(
            self._current_file, "user_assigned", phase="A"
        )
        self._set_state(DIAGNOSING_A)
        self._run_diagnosis_a()

    def _define_new_type(self):
        if self.on_define_new:
            self._paused_context = {
                "file_path": self._current_file,
                "classification": self._classification,
                "scored_candidates": self._scored_candidates,
                "extracted_text": self._extracted_text,
            }
            self.on_define_new(self._current_file, self._extracted_text)

    # ------------------------------------------------------------------
    # DIAGNOSING_A — Classification gap analysis
    # ------------------------------------------------------------------

    def _run_diagnosis_a(self):
        self._show_processing("Analyzing classification gap...")

        def task():
            try:
                result = diagnose_classification(
                    self._extracted_text,
                    self._assigned_type,
                    self.config.type_definitions,
                    self._scored_candidates or {},
                )
                self.root.after(0, lambda: self._on_diagnosis_a_done(result))
            except Exception as e:
                self.root.after(
                    0, lambda: self._show_error(f"Diagnosis error: {e}")
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_diagnosis_a_done(self, result):
        self._gap_analysis = result
        self._set_state(LEARNING_A)
        self._show_learning_a()

    # ------------------------------------------------------------------
    # LEARNING_A — Approve keyword/pattern suggestions with 3-way routing
    # ------------------------------------------------------------------

    def _show_learning_a(self):
        self._clear_content()
        f = self._content_frame
        gap = self._gap_analysis

        tk.Label(f, text="Phase A — Learning: Classification Signals",
                 font=("Courier", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 4))

        # Matched keywords summary
        if gap.get("matched_keywords"):
            tk.Label(f, text=f"Already matching: {', '.join(gap['matched_keywords'][:10])}",
                     font=("Courier", 8), fg="gray").pack(
                anchor="w", padx=8)

        # Scrollable area for suggestions
        canvas = tk.Canvas(f, highlightthickness=0)
        scrollbar = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=4)

        # Build entity list for alias dropdown
        entity_names = get_entity_names(self.config)
        entity_choices = ["(new entity)"] + [
            f"{key} — {name}" for key, name in sorted(entity_names.items())
        ]

        # Get doc type code for the assigned type
        type_cfg = self.config.type_definitions.get("types", {}).get(
            self._assigned_type, {}
        )
        self._assigned_type_code = type_cfg.get("code", "000")

        self._kw_route_rows = []  # [(phrase, route_var, role_var, entity_var)]
        self._pat_check_vars = []

        # Suggested keywords — 3-way routing per suggestion
        if gap.get("suggested_keywords"):
            tk.Label(scroll_frame, text="Suggested Keywords:",
                     font=("Courier", 9, "bold")).pack(anchor="w", pady=(4, 2))
            tk.Label(scroll_frame,
                     text="  For each, choose: Keyword (classification signal), "
                          "Entity (add to reference), or Skip",
                     font=("Courier", 8), fg="gray").pack(anchor="w", padx=8)

            for kw in gap["suggested_keywords"]:
                row_frame = tk.Frame(scroll_frame)
                row_frame.pack(fill=tk.X, padx=12, pady=2)

                # The phrase
                tk.Label(row_frame, text=kw, font=("Courier", 9, "bold"),
                         width=24, anchor="w").pack(side=tk.LEFT)

                # 3-way radio: skip / keyword / entity
                route_var = tk.StringVar(value="skip")
                tk.Radiobutton(row_frame, text="Skip", variable=route_var,
                               value="skip", font=("Courier", 8)).pack(
                    side=tk.LEFT, padx=(4, 0))
                tk.Radiobutton(row_frame, text="Keyword", variable=route_var,
                               value="keyword", font=("Courier", 8)).pack(
                    side=tk.LEFT, padx=(4, 0))
                tk.Radiobutton(row_frame, text="Entity", variable=route_var,
                               value="entity", font=("Courier", 8)).pack(
                    side=tk.LEFT, padx=(4, 0))

                # Entity details (role + new/alias) — visible inline
                detail_frame = tk.Frame(row_frame)
                detail_frame.pack(side=tk.LEFT, padx=(8, 0))

                role_var = tk.StringVar(value="vendor")
                role_combo = ttk.Combobox(
                    detail_frame, textvariable=role_var, width=8,
                    values=["vendor", "customer"], state="readonly",
                )
                role_combo.pack(side=tk.LEFT, padx=(0, 4))

                entity_var = tk.StringVar(value="(new entity)")
                entity_combo = ttk.Combobox(
                    detail_frame, textvariable=entity_var, width=28,
                    values=entity_choices, state="readonly",
                )
                entity_combo.pack(side=tk.LEFT)

                # Only show detail_frame when "entity" is selected
                def _toggle_detail(detail=detail_frame, var=route_var):
                    if var.get() == "entity":
                        detail.pack(side=tk.LEFT, padx=(8, 0))
                    else:
                        detail.pack_forget()

                route_var.trace_add("write", lambda *_, cb=_toggle_detail: cb())
                detail_frame.pack_forget()  # hidden by default (skip)

                self._kw_route_rows.append((kw, route_var, role_var, entity_var))

        # Suggested patterns — simple checkboxes (these are always classification signals)
        if gap.get("suggested_patterns"):
            tk.Label(scroll_frame, text="Suggested Patterns:",
                     font=("Courier", 9, "bold")).pack(anchor="w", pady=(8, 2))
            for pat in gap["suggested_patterns"]:
                var = tk.BooleanVar(value=True)
                tk.Checkbutton(scroll_frame, text=pat, variable=var,
                               font=("Courier", 9)).pack(anchor="w", padx=12)
                self._pat_check_vars.append((pat, var))

        if not gap.get("suggested_keywords") and not gap.get("suggested_patterns"):
            tk.Label(scroll_frame, text="No new signals to suggest.",
                     font=("Courier", 9), fg="gray").pack(anchor="w", pady=8)

        # Buttons at bottom of content frame (not in scroll)
        btn_frame = tk.Frame(f)
        btn_frame.pack(fill=tk.X, padx=8, pady=8, side=tk.BOTTOM)
        tk.Button(btn_frame, text="Apply Learning",
                  command=self._apply_learning_a).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Skip Learning",
                  command=self._skip_learning_a).pack(side=tk.LEFT, padx=4)

    def _apply_learning_a(self):
        approved_kw = []
        entities_added = []

        for phrase, route_var, role_var, entity_var in self._kw_route_rows:
            route = route_var.get()
            if route == "keyword":
                approved_kw.append(phrase)
            elif route == "entity":
                role = role_var.get()
                entity_choice = entity_var.get()
                if entity_choice == "(new entity)":
                    key = add_entity_reference(
                        phrase, role, self.config,
                        doc_type_code=self._assigned_type_code,
                    )
                    entities_added.append(
                        {"name": phrase, "action": "new", "key": key, "role": role}
                    )
                    if self.af_logger:
                        self.af_logger.log_reference_entry(
                            role, phrase,
                            {"name": phrase, "key": key, "role": role},
                        )
                else:
                    # Parse "key — name" format
                    entity_key = entity_choice.split(" — ")[0].strip()
                    added = add_alias_to_entity(entity_key, phrase, self.config)
                    if added:
                        entities_added.append(
                            {"name": phrase, "action": "alias",
                             "key": entity_key, "role": role}
                        )

        # Approved patterns (always classification signals)
        approved_pat = [pat for pat, var in self._pat_check_vars if var.get()]

        if approved_kw:
            count = add_keywords_to_type(
                self._assigned_type, approved_kw, self.config
            )
            self._learning_record["keywords_added"] = approved_kw[:count] if count else []

        if approved_pat:
            count = add_patterns_to_type(
                self._assigned_type, approved_pat, self.config
            )
            self._learning_record["patterns_added"] = approved_pat[:count] if count else []

        self._learning_record["entities_added"] = entities_added

        if approved_kw or approved_pat or entities_added:
            self.af_logger.log_learning_event(
                self._current_file,
                self._assigned_type,
                self._learning_record["keywords_added"],
                self._learning_record["patterns_added"],
                {},
            )

        self._advance_to_extraction()

    def _skip_learning_a(self):
        self._advance_to_extraction()

    def _advance_to_extraction(self):
        self._set_state(EXTRACTING)
        self._run_extraction()

    # ------------------------------------------------------------------
    # EXTRACTING
    # ------------------------------------------------------------------

    def _run_extraction(self):
        self._show_processing("Extracting fields...")

        def task():
            try:
                result = attempt_extraction(
                    self._current_file,
                    self._extracted_text,
                    self._assigned_type,
                    self.config,
                    self.af_logger,
                )
                self.root.after(0, lambda: self._on_extraction_done(result))
            except Exception as e:
                self.root.after(
                    0, lambda: self._show_error(f"Extraction error: {e}")
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_extraction_done(self, result):
        self._extraction_result = result
        if result["success"]:
            self._set_state(STAGING)
            self._run_staging()
        else:
            self.review_queue.mark_phase_b(
                self._current_file,
                f"missing:{','.join(result['missing_fields'])}",
            )
            self._set_state(PHASE_B)
            self._show_phase_b()

    # ------------------------------------------------------------------
    # PHASE B — Extraction Review
    # ------------------------------------------------------------------

    def _show_phase_b(self):
        self._clear_content()
        f = self._content_frame
        er = self._extraction_result

        tk.Label(f, text="Phase B — Extraction Review",
                 font=("Courier", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 4))

        # Show extracted fields
        if er["extracted_fields"]:
            ef_frame = tk.LabelFrame(f, text="Extracted Fields", padx=6, pady=4)
            ef_frame.pack(fill=tk.X, padx=8, pady=4)
            for fname, val in er["extracted_fields"].items():
                tk.Label(ef_frame, text=f"  {fname}: {val}",
                         font=("Courier", 9), anchor="w").pack(fill=tk.X)

        # Show missing fields
        if er["missing_fields"]:
            mf_frame = tk.LabelFrame(f, text="Missing Fields", padx=6, pady=4)
            mf_frame.pack(fill=tk.X, padx=8, pady=4)
            for fname in er["missing_fields"]:
                tk.Label(mf_frame, text=f"  {fname}", fg="red",
                         font=("Courier", 9), anchor="w").pack(fill=tk.X)

        tk.Button(f, text="Diagnose Extraction Gaps",
                  command=self._run_diagnosis_b).pack(padx=8, pady=8, anchor="w")

    # ------------------------------------------------------------------
    # DIAGNOSING_B — Extraction gap analysis
    # ------------------------------------------------------------------

    def _run_diagnosis_b(self):
        self._set_state(DIAGNOSING_B)
        self._show_processing("Analyzing extraction gaps...")

        def task():
            try:
                result = diagnose_extraction(
                    self._extracted_text,
                    self._assigned_type,
                    self.config.type_definitions,
                    self._extraction_result["extracted_fields"],
                    self._extraction_result["missing_fields"],
                )
                self.root.after(0, lambda: self._on_diagnosis_b_done(result))
            except Exception as e:
                self.root.after(
                    0, lambda: self._show_error(f"Extraction diagnosis error: {e}")
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_diagnosis_b_done(self, result):
        self._gap_analysis = result
        self._set_state(LEARNING_B)
        self._show_learning_b()

    # ------------------------------------------------------------------
    # LEARNING_B — Approve extraction pattern suggestions
    # ------------------------------------------------------------------

    def _show_learning_b(self):
        self._clear_content()
        f = self._content_frame
        gap = self._gap_analysis

        tk.Label(f, text="Phase B — Learning: Extraction Patterns",
                 font=("Courier", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 4))

        # Scrollable area
        canvas = tk.Canvas(f, highlightthickness=0)
        scrollbar = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=4)

        self._ext_pat_check_vars = {}  # field_name -> [(pattern, BooleanVar)]

        for field_name, field_info in gap.items():
            tk.Label(scroll_frame, text=f"Field: {field_name}",
                     font=("Courier", 9, "bold")).pack(anchor="w", pady=(6, 2))

            # Show existing pattern results
            for pr in field_info.get("pattern_results", []):
                status = "matched" if pr["matched"] else "no match"
                tk.Label(scroll_frame,
                         text=f"  Existing: {pr['pattern']} — {status}",
                         font=("Courier", 8), fg="gray").pack(anchor="w", padx=12)

            # Candidate values and suggested patterns
            self._ext_pat_check_vars[field_name] = []
            for cv in field_info.get("candidate_values", []):
                text = f"  Found \"{cv['text_snippet']}\" (line {cv['line_number']})"
                tk.Label(scroll_frame, text=text,
                         font=("Courier", 8)).pack(anchor="w", padx=12)
                var = tk.BooleanVar(value=True)
                tk.Checkbutton(
                    scroll_frame,
                    text=f"  Pattern: {cv['suggested_pattern']}",
                    variable=var, font=("Courier", 8),
                ).pack(anchor="w", padx=20)
                self._ext_pat_check_vars[field_name].append(
                    (cv["suggested_pattern"], var)
                )

        # Buttons
        btn_frame = tk.Frame(f)
        btn_frame.pack(fill=tk.X, padx=8, pady=8, side=tk.BOTTOM)
        tk.Button(btn_frame, text="Apply Learning",
                  command=self._apply_learning_b).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Skip Learning",
                  command=self._skip_learning_b).pack(side=tk.LEFT, padx=4)

    def _apply_learning_b(self):
        ext_pats_added = {}
        for field_name, items in self._ext_pat_check_vars.items():
            approved = [pat for pat, var in items if var.get()]
            if approved:
                count = add_extraction_patterns(
                    self._assigned_type, field_name, approved, self.config
                )
                if count:
                    ext_pats_added[field_name] = approved[:count]

        if ext_pats_added:
            self._learning_record["extraction_patterns_added"] = ext_pats_added
            self.af_logger.log_learning_event(
                self._current_file,
                self._assigned_type,
                [],
                [],
                ext_pats_added,
            )

        self._set_state(RE_EXTRACTING)
        self._run_re_extraction()

    def _skip_learning_b(self):
        self._set_state(RE_EXTRACTING)
        self._run_re_extraction()

    # ------------------------------------------------------------------
    # RE_EXTRACTING
    # ------------------------------------------------------------------

    def _run_re_extraction(self):
        self._show_processing("Re-extracting fields...")

        def task():
            try:
                result = attempt_extraction(
                    self._current_file,
                    self._extracted_text,
                    self._assigned_type,
                    self.config,
                    self.af_logger,
                )
                self.root.after(0, lambda: self._on_re_extraction_done(result))
            except Exception as e:
                self.root.after(
                    0, lambda: self._show_error(f"Re-extraction error: {e}")
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_re_extraction_done(self, result):
        self._extraction_result = result
        if result["success"]:
            self._set_state(STAGING)
            self._run_staging()
        else:
            self._set_state(MANUAL_ENTRY)
            self._show_manual_entry()

    # ------------------------------------------------------------------
    # MANUAL_ENTRY
    # ------------------------------------------------------------------

    def _show_manual_entry(self):
        self._clear_content()
        f = self._content_frame
        er = self._extraction_result

        tk.Label(f, text="Manual Entry — Supply Missing Fields",
                 font=("Courier", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 4))

        # Show what we have
        if er["extracted_fields"]:
            ef_frame = tk.LabelFrame(f, text="Extracted (OK)", padx=6, pady=4)
            ef_frame.pack(fill=tk.X, padx=8, pady=4)
            for fname, val in er["extracted_fields"].items():
                tk.Label(ef_frame, text=f"  {fname}: {val}",
                         font=("Courier", 9)).pack(anchor="w")

        # Entry fields for missing
        entry_frame = tk.LabelFrame(f, text="Missing (enter values)",
                                    padx=6, pady=4)
        entry_frame.pack(fill=tk.X, padx=8, pady=4)

        self._manual_vars = {}
        for field_name in er["missing_fields"]:
            row = tk.Frame(entry_frame)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"  {field_name}:",
                     font=("Courier", 9), width=20, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar()
            tk.Entry(row, textvariable=var, width=40).pack(side=tk.LEFT)
            self._manual_vars[field_name] = var

        tk.Button(f, text="Stage File", command=self._stage_with_manual).pack(
            padx=8, pady=12, anchor="w")

    def _stage_with_manual(self):
        manual_fields = {
            fname: var.get().strip()
            for fname, var in self._manual_vars.items()
            if var.get().strip()
        }
        self._set_state(STAGING)
        self._run_staging(manual_fields=manual_fields)

    # ------------------------------------------------------------------
    # STAGING
    # ------------------------------------------------------------------

    def _run_staging(self, manual_fields=None):
        self._show_processing("Staging file...")

        review_type = "classification" if not self._extraction_result else "both"
        if self._extraction_result and self._extraction_result["success"]:
            if not self._gap_analysis or self._state == STAGING:
                review_type = "classification"

        review_info = {
            "review_type": review_type,
            "original_reason": (
                self.review_queue.get_file_info(self._current_file) or {}
            ).get("review_reason", "unknown"),
            "assigned_type": self._assigned_type,
            "learning_applied": self._learning_record,
            "manual_fields": manual_fields or {},
        }

        er = self._extraction_result or {
            "extracted_fields": {},
            "resolution_info": {},
        }

        def task():
            try:
                result = stage_file(
                    file_path=self._current_file,
                    type_name=self._assigned_type,
                    extracted_fields=er["extracted_fields"],
                    resolution_info=er.get("resolution_info", {}),
                    extracted_text=self._extracted_text or "",
                    config=self.config,
                    logger=self.af_logger,
                    manual_fields=manual_fields,
                    review_info=review_info,
                )
                self.root.after(0, lambda: self._on_staging_done(result,
                                                                  manual_fields))
            except Exception as e:
                self.root.after(
                    0, lambda: self._show_error(f"Staging error: {e}")
                )

        threading.Thread(target=task, daemon=True).start()

    def _on_staging_done(self, result, manual_fields=None):
        self.review_queue.mark_resolved(self._current_file, self._assigned_type)

        self.af_logger.log_review_stage(
            self._current_file,
            self._assigned_type,
            result["staging_file"],
            "classification" if not manual_fields else "both",
            manual_fields,
        )

        self._set_state(DONE)
        self._show_done(result)

    # ------------------------------------------------------------------
    # DONE
    # ------------------------------------------------------------------

    def _show_done(self, result):
        self._clear_content()
        f = self._content_frame

        tk.Label(f, text="File Staged Successfully",
                 font=("Courier", 12, "bold"), fg="green").pack(
            anchor="w", padx=8, pady=(12, 4))

        tk.Label(f, text=f"Type: {self._assigned_type}",
                 font=("Courier", 10)).pack(anchor="w", padx=8, pady=2)
        tk.Label(f, text=f"Staging: {result['staging_filename']}",
                 font=("Courier", 10)).pack(anchor="w", padx=8, pady=2)
        tk.Label(f, text=f"Vault: {result['vault_file']}",
                 font=("Courier", 9), fg="gray").pack(anchor="w", padx=8, pady=2)

        if self._learning_record["keywords_added"]:
            tk.Label(f, text=f"Keywords added: {', '.join(self._learning_record['keywords_added'])}",
                     font=("Courier", 9)).pack(anchor="w", padx=8, pady=2)
        if self._learning_record["patterns_added"]:
            tk.Label(f, text=f"Patterns added: {len(self._learning_record['patterns_added'])}",
                     font=("Courier", 9)).pack(anchor="w", padx=8, pady=2)
        if self._learning_record["extraction_patterns_added"]:
            count = sum(len(v) for v in self._learning_record["extraction_patterns_added"].values())
            tk.Label(f, text=f"Extraction patterns added: {count}",
                     font=("Courier", 9)).pack(anchor="w", padx=8, pady=2)
        if self._learning_record.get("entities_added"):
            for ent in self._learning_record["entities_added"]:
                action = "New entity" if ent["action"] == "new" else f"Alias for {ent['key']}"
                tk.Label(f, text=f"Entity: {ent['name']} ({action}, role={ent['role']})",
                         font=("Courier", 9)).pack(anchor="w", padx=8, pady=2)

        tk.Button(f, text="Next File", command=self._next_file).pack(
            padx=8, pady=16, anchor="w")

    def _next_file(self):
        self._set_state(IDLE)
        self._clear_content()
        self._refresh_tree()

    # ------------------------------------------------------------------
    # Error display
    # ------------------------------------------------------------------

    def _show_error(self, message):
        self._clear_content()
        tk.Label(self._content_frame, text=message, fg="red",
                 font=("Courier", 10), wraplength=500).pack(pady=20, padx=8)
        tk.Button(self._content_frame, text="Back to Queue",
                  command=self._next_file).pack(pady=8)
