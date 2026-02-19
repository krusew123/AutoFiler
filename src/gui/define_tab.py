# src/gui/define_tab.py
"""Define tab — type creation form with optional document analysis panel."""

import pathlib
import re
import tkinter as tk
from tkinter import ttk, messagebox

from src.gap_analyzer import analyze_document_for_new_type
from src.config_learner import (
    add_entity_reference,
    add_alias_to_entity,
    get_entity_names,
)
from src.type_creator_core import (
    next_available_code,
    validate_type_definition,
    build_type_definition,
    persist_type,
)


# Staging slot names in display order
_STAGING_SLOTS = ["vendor", "customer", "date", "reference", "amount"]


class DefineTab(tk.Frame):
    """Type creation form with optional document analysis panel.

    When opened from the Review tab with a document, shows a side-by-side
    layout: document analysis on the left, form on the right.  Suggested
    keywords, patterns, and fields can be added to the form with a click.
    """

    def __init__(self, parent, ctx, on_type_created=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.root = ctx["root"]
        self.config = ctx["config"]
        self.af_logger = ctx["logger"]
        self.on_type_created = on_type_created

        # Return context when linked from Review tab
        self._return_file_path = None
        self._extracted_text = None
        self._doc_analysis = None

        # Dynamic extraction field rows
        self._field_rows = []

        # Suggestion vars (rebuilt when analysis is shown)
        self._kw_route_rows = []   # [(kw, route_var, role_var, entity_var)]
        self._pat_check_vars = []  # [(pattern_str, BooleanVar)]

        # Track whether analysis pane is showing
        self._analysis_visible = False

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_return_context(self, file_path, extracted_text=None):
        """Set context for returning to Review tab after save."""
        self._return_file_path = file_path
        self._extracted_text = extracted_text

        if file_path:
            name = pathlib.Path(file_path).name
            self._context_banner.config(text=f"Defining type for: {name}")
            self._context_frame.pack(fill=tk.X, padx=10, pady=(4, 0),
                                     before=self._paned)
        else:
            self._context_frame.pack_forget()

        if extracted_text:
            self._doc_analysis = analyze_document_for_new_type(extracted_text)
            self._populate_analysis()
            self._show_analysis_pane()
        else:
            self._hide_analysis_pane()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Title
        tk.Label(self, text="DEFINE NEW DOCUMENT TYPE",
                 font=("Courier", 12, "bold")).pack(pady=(10, 4))

        # Context banner (hidden until set_return_context)
        self._context_frame = tk.Frame(self, bg="#fff3cd", padx=8, pady=4)
        self._context_banner = tk.Label(
            self._context_frame, text="", bg="#fff3cd",
            font=("Courier", 9), anchor="w",
        )
        self._context_banner.pack(fill=tk.X)
        # Don't pack _context_frame by default — shown only when linked

        # Main paned window (horizontal split)
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Left pane: document analysis (built but not added until needed)
        self._analysis_outer = tk.Frame(self._paned)
        self._build_analysis_pane()

        # Right pane: the form (always visible)
        self._form_outer = tk.Frame(self._paned)
        self._build_form_pane()
        self._paned.add(self._form_outer, weight=1)

    # ------------------------------------------------------------------
    # Analysis pane (left side)
    # ------------------------------------------------------------------

    def _build_analysis_pane(self):
        """Build the scrollable document analysis panel."""
        outer = self._analysis_outer

        tk.Label(outer, text="Document Analysis",
                 font=("Courier", 10, "bold")).pack(anchor="w", padx=6,
                                                     pady=(4, 2))

        canvas = tk.Canvas(outer, highlightthickness=0, width=360)
        scrollbar = ttk.Scrollbar(outer, orient="vertical",
                                  command=canvas.yview)
        self._analysis_scroll = tk.Frame(canvas)
        self._analysis_scroll.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._analysis_scroll, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._analysis_canvas = canvas

        # Mousewheel binding — activate when cursor enters this canvas
        canvas.bind("<Enter>", lambda e: self._bind_mousewheel(canvas))

    def _show_analysis_pane(self):
        if not self._analysis_visible:
            self._paned.insert(0, self._analysis_outer, weight=0)
            self._analysis_visible = True

    def _hide_analysis_pane(self):
        if self._analysis_visible:
            self._paned.forget(self._analysis_outer)
            self._analysis_visible = False

    def _populate_analysis(self):
        """Fill the analysis panel with document suggestions."""
        # Clear existing content
        for w in self._analysis_scroll.winfo_children():
            w.destroy()
        self._kw_route_rows = []
        self._pat_check_vars = []

        f = self._analysis_scroll
        analysis = self._doc_analysis
        if not analysis:
            return

        # --- Extracted text preview ---
        text_frame = tk.LabelFrame(f, text="Extracted Text", padx=4, pady=4)
        text_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
        preview = tk.Text(text_frame, height=10, width=44, font=("Courier", 8),
                          wrap=tk.WORD)
        preview.insert("1.0", (self._extracted_text or "")[:5000])
        preview.config(state=tk.DISABLED)
        preview.pack(fill=tk.X)

        # --- Suggested keywords with 5-way routing ---
        kw_list = analysis.get("suggested_keywords", [])
        if kw_list:
            kw_frame = tk.LabelFrame(
                f, text=f"Suggested Keywords ({len(kw_list)})",
                padx=4, pady=4,
            )
            kw_frame.pack(fill=tk.X, padx=6, pady=(0, 6))

            tk.Label(
                kw_frame,
                text="Route each: Skip, Keyword (classification), "
                     "Entity (reference),\nReq Field, or Opt Field "
                     "(extraction)",
                font=("Courier", 7), fg="gray",
            ).pack(anchor="w", pady=(0, 4))

            # Build entity list for alias dropdown
            entity_names = get_entity_names(self.config)
            entity_choices = ["(new entity)"] + [
                f"{key} — {name}"
                for key, name in sorted(entity_names.items())
            ]

            for kw in kw_list:
                row_f = tk.Frame(kw_frame)
                row_f.pack(fill=tk.X, pady=2)

                # Keyword text
                tk.Label(row_f, text=kw, font=("Courier", 8, "bold"),
                         width=22, anchor="w").pack(side=tk.LEFT)

                # Route dropdown
                route_var = tk.StringVar(value="skip")
                route_combo = ttk.Combobox(
                    row_f, textvariable=route_var, width=10,
                    values=["skip", "keyword", "entity",
                            "req field", "opt field"],
                    state="readonly",
                )
                route_combo.pack(side=tk.LEFT, padx=4)

                # Entity detail frame (role + alias target) — hidden by default
                detail_frame = tk.Frame(row_f)

                role_var = tk.StringVar(value="vendor")
                ttk.Combobox(
                    detail_frame, textvariable=role_var, width=8,
                    values=["vendor", "customer"], state="readonly",
                ).pack(side=tk.LEFT, padx=(0, 4))

                entity_var = tk.StringVar(value="(new entity)")
                ttk.Combobox(
                    detail_frame, textvariable=entity_var, width=22,
                    values=entity_choices, state="readonly",
                ).pack(side=tk.LEFT)

                # Toggle detail visibility based on route selection
                def _on_route_change(*_args, df=detail_frame, rv=route_var):
                    if rv.get() == "entity":
                        df.pack(side=tk.LEFT, padx=4)
                    else:
                        df.pack_forget()

                route_var.trace_add("write", _on_route_change)

                self._kw_route_rows.append(
                    (kw, route_var, role_var, entity_var)
                )

            tk.Button(kw_frame, text="Apply Selections",
                      command=self._apply_keyword_selections,
                      font=("Courier", 8)).pack(pady=(6, 0))

        # --- Suggested patterns ---
        pat_list = analysis.get("suggested_patterns", [])
        if pat_list:
            pat_frame = tk.LabelFrame(
                f, text=f"Suggested Patterns ({len(pat_list)})",
                padx=4, pady=4,
            )
            pat_frame.pack(fill=tk.X, padx=6, pady=(0, 6))

            for pat in pat_list:
                var = tk.BooleanVar(value=False)
                tk.Checkbutton(pat_frame, text=pat, variable=var,
                               font=("Courier", 8), anchor="w").pack(
                    fill=tk.X)
                self._pat_check_vars.append((pat, var))

            tk.Button(pat_frame, text="Add Selected to Patterns",
                      command=self._add_selected_patterns,
                      font=("Courier", 8)).pack(pady=(4, 0))

        # --- Detected fields (label:value pairs) with req/opt toggle ---
        fields = analysis.get("detected_fields", [])
        if fields:
            fld_frame = tk.LabelFrame(
                f, text=f"Detected Fields ({len(fields)})",
                padx=4, pady=4,
            )
            fld_frame.pack(fill=tk.X, padx=6, pady=(0, 6))

            for fld in fields:
                row_f = tk.Frame(fld_frame)
                row_f.pack(fill=tk.X, pady=1)

                label_text = f"{fld['label']}: {fld['value']}"
                if len(label_text) > 36:
                    label_text = label_text[:33] + "..."
                tk.Label(row_f, text=label_text,
                         font=("Courier", 8), anchor="w").pack(
                    side=tk.LEFT, fill=tk.X, expand=True)

                tk.Label(row_f, text=f"[{fld['field_type']}]",
                         font=("Courier", 7), fg="gray").pack(
                    side=tk.LEFT, padx=(2, 2))

                # Required/Optional toggle
                req_var = tk.BooleanVar(value=True)
                tk.Checkbutton(row_f, text="Req", variable=req_var,
                               font=("Courier", 7)).pack(
                    side=tk.LEFT, padx=(0, 2))

                tk.Button(
                    row_f, text="Add",
                    font=("Courier", 7),
                    command=lambda d=fld, r=req_var: self._add_detected_field(
                        d, r.get()
                    ),
                ).pack(side=tk.RIGHT)

        if not kw_list and not pat_list and not fields:
            tk.Label(f, text="No suggestions found.",
                     font=("Courier", 9), fg="gray").pack(pady=8)

    # ------------------------------------------------------------------
    # Analysis → Form transfer actions
    # ------------------------------------------------------------------

    def _apply_keyword_selections(self):
        """Process all keyword routing selections."""
        keywords_to_add = []
        entities_to_add = []
        fields_to_add = []

        for kw, route_var, role_var, entity_var in self._kw_route_rows:
            route = route_var.get()
            if route == "skip":
                continue
            elif route == "keyword":
                keywords_to_add.append(kw)
            elif route == "entity":
                entities_to_add.append(
                    (kw, role_var.get(), entity_var.get())
                )
            elif route in ("req field", "opt field"):
                fields_to_add.append((kw, route == "req field"))

        # Add classification keywords to text box
        if keywords_to_add:
            existing = self._keywords_text.get("1.0", "end").strip()
            existing_set = {
                line.strip().lower()
                for line in existing.splitlines() if line.strip()
            }
            new_kws = [
                kw for kw in keywords_to_add
                if kw.lower() not in existing_set
            ]
            if new_kws:
                if existing:
                    self._keywords_text.insert("end", "\n")
                self._keywords_text.insert("end", "\n".join(new_kws))

        # Add entities to fieldname_ref.json
        for kw, role, entity_choice in entities_to_add:
            if entity_choice == "(new entity)":
                add_entity_reference(kw, role, self.config)
            else:
                entity_key = entity_choice.split(" — ")[0].strip()
                add_alias_to_entity(entity_key, kw, self.config)

        # Add extraction field rows
        for kw, required in fields_to_add:
            field_name, pattern, ref_role = self._keyword_to_field(kw)
            exists = any(
                r["name"].get() == field_name for r in self._field_rows
            )
            if not exists:
                self._add_field_row(
                    name=field_name,
                    patterns=pattern,
                    required=required,
                    ref_role=ref_role,
                )

        # Reset all routes to skip
        for _kw, route_var, _role_var, _entity_var in self._kw_route_rows:
            route_var.set("skip")

    def _keyword_to_field(self, keyword):
        """Convert a keyword phrase to a field name, pattern, and ref role."""
        field_name = re.sub(r"[^a-z0-9]+", "_", keyword.lower()).strip("_")
        safe_label = re.escape(keyword)
        kw_lower = keyword.lower()

        if "date" in kw_lower:
            pattern = safe_label + r"[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
            ref_role = ""
        elif any(w in kw_lower for w in (
            "amount", "total", "balance", "charge", "price", "cost", "due",
        )):
            pattern = safe_label + r"[:\s]*\$?([\d,]+\.\d{2})"
            ref_role = ""
        elif any(w in kw_lower for w in (
            "number", "num", "no", "id", "ref", "invoice", "po", "order",
        )):
            pattern = safe_label + r"[:\s]*([A-Za-z0-9][\-A-Za-z0-9]+)"
            ref_role = ""
        elif any(w in kw_lower for w in (
            "vendor", "remit", "from", "sold by", "supplier",
        )):
            pattern = safe_label + r"[:\s]*(.+?)\s*$"
            ref_role = "vendor"
        elif any(w in kw_lower for w in (
            "customer", "client", "bill to", "prepared for", "ship to",
        )):
            pattern = safe_label + r"[:\s]*(.+?)\s*$"
            ref_role = "customer"
        elif "name" in kw_lower:
            pattern = safe_label + r"[:\s]*(.+?)\s*$"
            ref_role = "vendor"
        else:
            pattern = safe_label + r"[:\s]*(.+?)\s*$"
            ref_role = ""

        return field_name, pattern, ref_role

    def _add_selected_patterns(self):
        """Append checked patterns to the Patterns text box."""
        selected = [pat for pat, var in self._pat_check_vars if var.get()]
        if not selected:
            return
        existing = self._patterns_text.get("1.0", "end").strip()
        existing_set = {
            line.strip() for line in existing.splitlines() if line.strip()
        }
        new_pats = [pat for pat in selected if pat not in existing_set]
        if new_pats:
            if existing:
                self._patterns_text.insert("end", "\n")
            self._patterns_text.insert("end", "\n".join(new_pats))
        for pat, var in self._pat_check_vars:
            if pat in selected:
                var.set(False)

    def _add_detected_field(self, field_data, required=True):
        """Add a detected field as an extraction field row in the form."""
        # Check if field name already exists
        for row in self._field_rows:
            if row["name"].get() == field_data["field_name"]:
                return  # Already added
        ref_role = ""
        if field_data["field_type"] == "name":
            ref_role = "vendor"  # Default; user can change
        self._add_field_row(
            name=field_data["field_name"],
            patterns=field_data["suggested_pattern"],
            required=required,
            ref_role=ref_role,
        )

    # ------------------------------------------------------------------
    # Form pane (right side)
    # ------------------------------------------------------------------

    def _build_form_pane(self):
        """Build the scrollable form panel — same fields as original."""
        outer = self._form_outer

        self._form_canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical",
                                  command=self._form_canvas.yview)
        self._form_frame = tk.Frame(self._form_canvas)
        self._form_frame.bind(
            "<Configure>",
            lambda e: self._form_canvas.configure(
                scrollregion=self._form_canvas.bbox("all")
            ),
        )
        self._form_canvas.create_window((0, 0), window=self._form_frame,
                                        anchor="nw")
        self._form_canvas.configure(yscrollcommand=scrollbar.set)
        self._form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mousewheel binding — activate when cursor enters this canvas
        self._form_canvas.bind("<Enter>",
                               lambda e: self._bind_mousewheel(self._form_canvas))

        f = self._form_frame

        # --- Basic fields ---
        row = 0
        tk.Label(f, text="Type Name:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=6, pady=3)
        self._name_var = tk.StringVar()
        tk.Entry(f, textvariable=self._name_var, width=40).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)

        row += 1
        tk.Label(f, text="Container Formats:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=6, pady=3)
        self._formats_var = tk.StringVar()
        tk.Entry(f, textvariable=self._formats_var, width=40).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        tk.Label(f, text="(comma-sep, e.g. .pdf,.docx)",
                 font=("Courier", 8)).grid(row=row, column=2, sticky="w")

        row += 1
        tk.Label(f, text="MIME Types:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=6, pady=3)
        self._mime_var = tk.StringVar()
        tk.Entry(f, textvariable=self._mime_var, width=40).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        tk.Label(f, text="(optional, comma-sep)",
                 font=("Courier", 8)).grid(row=row, column=2, sticky="w")

        row += 1
        tk.Label(f, text="Content Keywords:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="nw", padx=6, pady=3)
        self._keywords_text = tk.Text(f, width=40, height=4,
                                      font=("Courier", 9))
        self._keywords_text.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        tk.Label(f, text="(one per line)",
                 font=("Courier", 8)).grid(row=row, column=2, sticky="nw")

        row += 1
        tk.Label(f, text="Content Patterns:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="nw", padx=6, pady=3)
        self._patterns_text = tk.Text(f, width=40, height=3,
                                      font=("Courier", 9))
        self._patterns_text.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        tk.Label(f, text="(one regex per line, optional)",
                 font=("Courier", 8)).grid(row=row, column=2, sticky="nw")

        row += 1
        tk.Label(f, text="Keyword Threshold:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=6, pady=3)
        self._threshold_var = tk.IntVar(value=2)
        tk.Spinbox(f, from_=1, to=20, textvariable=self._threshold_var,
                   width=5).grid(row=row, column=1, sticky="w", padx=6, pady=3)

        row += 1
        tk.Label(f, text="Destination Subfolder:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=6, pady=3)
        self._dest_var = tk.StringVar()
        tk.Entry(f, textvariable=self._dest_var, width=40).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)

        row += 1
        tk.Label(f, text="Naming Pattern:", font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=6, pady=3)
        self._naming_var = tk.StringVar(value="{original_name}_{date}")
        tk.Entry(f, textvariable=self._naming_var, width=40).grid(
            row=row, column=1, sticky="w", padx=6, pady=3)

        # --- Extraction Fields section ---
        row += 1
        ttk.Separator(f, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew",
            padx=6, pady=(12, 4))

        row += 1
        tk.Label(f, text="Extraction Fields",
                 font=("Courier", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=6, pady=3)

        row += 1
        self._fields_container = tk.Frame(f)
        self._fields_container.grid(row=row, column=0, columnspan=3,
                                    sticky="ew", padx=6)
        self._next_field_row = row + 1

        tk.Button(f, text="+ Add Field", command=self._add_field_row).grid(
            row=row, column=2, sticky="e", padx=6)

        # --- Staging Field Mapping ---
        row = self._next_field_row + 1
        ttk.Separator(f, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew",
            padx=6, pady=(12, 4))

        row += 1
        tk.Label(f, text="Staging Field Mapping",
                 font=("Courier", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=6, pady=3)

        self._staging_vars = {}
        for slot in _STAGING_SLOTS:
            row += 1
            tk.Label(f, text=f"  {slot}:", font=("Courier", 9)).grid(
                row=row, column=0, sticky="w", padx=6, pady=2)
            var = tk.StringVar()
            combo = ttk.Combobox(f, textvariable=var, width=30,
                                 state="readonly")
            combo.grid(row=row, column=1, sticky="w", padx=6, pady=2)
            self._staging_vars[slot] = (var, combo)

        # --- Buttons ---
        row += 1
        btn_frame = tk.Frame(f)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(16, 10))

        tk.Button(btn_frame, text="Validate", width=12,
                  command=self._validate).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Save Type", width=12,
                  command=self._save).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Cancel", width=12,
                  command=self._cancel).pack(side=tk.LEFT, padx=4)

        # Error display area
        row += 1
        self._error_label = tk.Label(f, text="", fg="red",
                                     font=("Courier", 9),
                                     wraplength=600, justify="left")
        self._error_label.grid(row=row, column=0, columnspan=3,
                               sticky="w", padx=6, pady=4)

    # ------------------------------------------------------------------
    # Mousewheel helper
    # ------------------------------------------------------------------

    def _bind_mousewheel(self, canvas):
        """Bind mousewheel scrolling to the given canvas."""
        self.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

    # ------------------------------------------------------------------
    # Extraction field rows
    # ------------------------------------------------------------------

    def _add_field_row(self, name="", patterns="", required=False,
                       ref_role=""):
        """Add a new extraction field row to the form."""
        row_frame = tk.Frame(self._fields_container)
        row_frame.pack(fill=tk.X, pady=2)

        name_var = tk.StringVar(value=name)
        tk.Label(row_frame, text="Field:", font=("Courier", 8)).pack(
            side=tk.LEFT, padx=(0, 2))
        tk.Entry(row_frame, textvariable=name_var, width=14).pack(
            side=tk.LEFT, padx=(0, 4))

        patterns_var = tk.StringVar(value=patterns)
        tk.Label(row_frame, text="Patterns:", font=("Courier", 8)).pack(
            side=tk.LEFT, padx=(0, 2))
        tk.Entry(row_frame, textvariable=patterns_var, width=20).pack(
            side=tk.LEFT, padx=(0, 4))

        req_var = tk.BooleanVar(value=required)
        tk.Checkbutton(row_frame, text="Req", variable=req_var).pack(
            side=tk.LEFT, padx=(0, 4))

        ref_var = tk.StringVar(value=ref_role)
        tk.Label(row_frame, text="Ref role:", font=("Courier", 8)).pack(
            side=tk.LEFT, padx=(0, 2))
        tk.Entry(row_frame, textvariable=ref_var, width=10).pack(
            side=tk.LEFT, padx=(0, 4))

        row_data = {
            "frame": row_frame,
            "name": name_var,
            "patterns": patterns_var,
            "required": req_var,
            "ref_role": ref_var,
        }
        self._field_rows.append(row_data)

        tk.Button(
            row_frame, text="-", width=2,
            command=lambda: self._remove_field_row(row_data),
        ).pack(side=tk.LEFT, padx=2)

        # Update staging field dropdowns
        self._refresh_staging_combos()

        # Bind name changes to refresh staging combos
        name_var.trace_add("write", lambda *_: self._refresh_staging_combos())

    def _remove_field_row(self, row_data):
        row_data["frame"].destroy()
        self._field_rows.remove(row_data)
        self._refresh_staging_combos()

    def _refresh_staging_combos(self):
        """Update staging mapping comboboxes with current field names."""
        names = [""] + [r["name"].get() for r in self._field_rows
                        if r["name"].get()]
        for slot, (var, combo) in self._staging_vars.items():
            current = var.get()
            combo["values"] = names
            if current not in names:
                var.set("")

    # ------------------------------------------------------------------
    # Collect form data
    # ------------------------------------------------------------------

    def _collect(self) -> tuple[str, dict]:
        """Gather all form inputs into (type_name, type_def)."""
        type_name = self._name_var.get().strip().lower()

        container_formats = [
            s.strip() for s in self._formats_var.get().split(",") if s.strip()
        ]
        mime_types = [
            s.strip() for s in self._mime_var.get().split(",") if s.strip()
        ]
        content_keywords = [
            line.strip()
            for line in self._keywords_text.get("1.0", "end").splitlines()
            if line.strip()
        ]
        content_patterns = [
            line.strip()
            for line in self._patterns_text.get("1.0", "end").splitlines()
            if line.strip()
        ]
        keyword_threshold = self._threshold_var.get()
        dest_subfolder = self._dest_var.get().strip()
        naming_pattern = self._naming_var.get().strip()

        # Build extraction_fields
        extraction_fields = {}
        for row in self._field_rows:
            fname = row["name"].get().strip()
            if not fname:
                continue
            pats = [
                p.strip()
                for p in row["patterns"].get().split(";") if p.strip()
            ]
            field_cfg = {
                "patterns": pats,
                "required": row["required"].get(),
            }
            ref_role = row["ref_role"].get().strip()
            if ref_role:
                field_cfg["reference_lookup"] = {"role": ref_role}
            extraction_fields[fname] = field_cfg

        # Build staging_fields
        staging_fields = {}
        for slot, (var, _) in self._staging_vars.items():
            val = var.get().strip()
            if val:
                staging_fields[slot] = val

        existing = self.config.type_definitions.get("types", {})
        code = next_available_code(existing)

        type_def = build_type_definition(
            type_name=type_name,
            code=code,
            container_formats=container_formats,
            content_keywords=content_keywords,
            destination_subfolder=dest_subfolder,
            naming_pattern=naming_pattern or "{original_name}_{date}",
            mime_types=mime_types,
            content_patterns=content_patterns,
            keyword_threshold=keyword_threshold,
            extraction_fields=extraction_fields,
            staging_fields=staging_fields,
        )

        return type_name, type_def

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _validate(self):
        type_name, type_def = self._collect()
        existing = self.config.type_definitions.get("types", {})
        errors = validate_type_definition(type_name, type_def, existing)
        if errors:
            self._error_label.config(
                text="\n".join(f"  \u2022 {e}" for e in errors), fg="red"
            )
        else:
            self._error_label.config(text="  Valid — ready to save.", fg="green")

    def _save(self):
        type_name, type_def = self._collect()
        existing = self.config.type_definitions.get("types", {})
        errors = validate_type_definition(type_name, type_def, existing)
        if errors:
            self._error_label.config(
                text="\n".join(f"  \u2022 {e}" for e in errors), fg="red"
            )
            return

        try:
            persist_type(
                type_name,
                type_def,
                type_def["destination_subfolder"],
                type_def["naming_pattern"],
                self.config,
            )
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
            return

        self.af_logger.log_new_type(type_name, type_def)
        messagebox.showinfo("Saved", f"Type '{type_name}' created successfully.")

        return_path = self._return_file_path
        self._reset_form()

        if self.on_type_created:
            self.on_type_created(type_name, return_path)

    def _cancel(self):
        return_path = self._return_file_path
        self._reset_form()
        if self.on_type_created and return_path:
            # Return to review without a new type
            self.on_type_created(None, return_path)

    def _reset_form(self):
        """Clear the form back to defaults."""
        self._name_var.set("")
        self._formats_var.set("")
        self._mime_var.set("")
        self._keywords_text.delete("1.0", "end")
        self._patterns_text.delete("1.0", "end")
        self._threshold_var.set(2)
        self._dest_var.set("")
        self._naming_var.set("{original_name}_{date}")
        for row in list(self._field_rows):
            row["frame"].destroy()
        self._field_rows.clear()
        for slot, (var, combo) in self._staging_vars.items():
            var.set("")
        self._error_label.config(text="")
        self._return_file_path = None
        self._extracted_text = None
        self._doc_analysis = None
        self._context_frame.pack_forget()
        self._hide_analysis_pane()
