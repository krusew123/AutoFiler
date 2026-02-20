# src/gui/define_tab.py
"""Define tab — two-column type creation form with optional document analysis."""

import pathlib
import re
import tkinter as tk
from tkinter import ttk, messagebox

from src.gap_analyzer import analyze_document_for_new_type
from src.config_learner import (
    add_entity_reference,
    add_alias_to_entity,
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
    """Type creation form with two-column layout.

    Left column (visible only when linked from Review with extracted text):
      - Extracted Text with scrollbar, Population button, search
      - Keyword Population with toggle buttons (kw/ext/skip)

    Right column (always visible):
      - doc_type (metadata)
      - tags (classification keywords)
      - extract (fields with req/opt toggles and name_ref checkbox)
      - Staging Field Mapping

    External API (unchanged):
      DefineTab(parent, ctx, on_type_created=None)
      set_return_context(file_path, extracted_text=None)
      on_type_created callback: (type_name, return_file_path)
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

        # Text preview widget reference
        self._text_preview = None

        # Dynamic extraction field rows
        self._field_rows = []

        # Population rows: [(kw, route_var, row_frame)]
        self._kw_route_rows = []
        self._kw_deleted = set()

        # Track keywords already turned into field rows (prevent dupes on re-Process)
        self._processed_extracts = set()

        # Search state
        self._search_pos = "1.0"

        # Left pane visibility
        self._left_visible = False

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
            self._show_left_pane()
            self._populate_text_preview()
            self._populate_population()
        else:
            self._hide_left_pane()

    # ------------------------------------------------------------------
    # UI construction — main frame
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

        # Horizontal PanedWindow
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Left pane (built but not added until needed)
        self._left_outer = tk.Frame(self._paned)
        self._build_left_pane()

        # Right pane (always visible)
        self._right_outer = tk.Frame(self._paned)
        self._build_right_pane()
        self._paned.add(self._right_outer, weight=1)

        # Buttons at bottom (outside paned window)
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(6, 4))
        tk.Button(btn_frame, text="Validate", width=12,
                  command=self._validate).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Save Type", width=12,
                  command=self._save).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Cancel", width=12,
                  command=self._cancel).pack(side=tk.LEFT, padx=4)

        self._error_label = tk.Label(self, text="", fg="red",
                                     font=("Courier", 9),
                                     wraplength=700, justify="left")
        self._error_label.pack(anchor="w", padx=10, pady=(0, 6))

    # ------------------------------------------------------------------
    # Left pane: Extracted Text + Keyword Population
    # ------------------------------------------------------------------

    def _build_left_pane(self):
        outer = self._left_outer
        canvas = tk.Canvas(outer, highlightthickness=0, width=460)
        scrollbar = ttk.Scrollbar(outer, orient="vertical",
                                  command=canvas.yview)
        self._left_inner = tk.Frame(canvas)
        self._left_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        self._left_win_id = canvas.create_window(
            (0, 0), window=self._left_inner, anchor="nw",
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._left_canvas = canvas

        # Resize inner frame width to match canvas
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(self._left_win_id, width=e.width),
        )
        self._bind_mousewheel(canvas)

        f = self._left_inner

        # Section: Extracted Text
        sec_a = tk.LabelFrame(f, text="Extracted Text", padx=6, pady=4)
        sec_a.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._build_section_text(sec_a)

        # Section: Keyword Population
        sec_b = tk.LabelFrame(f, text="Keyword Population", padx=6, pady=4)
        sec_b.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._build_section_population(sec_b)


    def _show_left_pane(self):
        if not self._left_visible:
            self._paned.insert(0, self._left_outer, weight=0)
            self._left_visible = True

    def _hide_left_pane(self):
        if self._left_visible:
            self._paned.forget(self._left_outer)
            self._left_visible = False

    # ------------------------------------------------------------------
    # Right pane: Doc_Type Fields + Keywords + Fields + Staging
    # ------------------------------------------------------------------

    def _build_right_pane(self):
        outer = self._right_outer
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical",
                                  command=canvas.yview)
        self._right_inner = tk.Frame(canvas)
        self._right_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        self._right_win_id = canvas.create_window(
            (0, 0), window=self._right_inner, anchor="nw",
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._right_canvas = canvas

        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(self._right_win_id, width=e.width),
        )
        self._bind_mousewheel(canvas)

        f = self._right_inner

        # Doc_Type Fields (top of right column)
        sec_e = tk.LabelFrame(f, text="doc_type", padx=6, pady=4)
        sec_e.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._build_section_dtype(sec_e)

        # Keywords to Identify Doc_Type
        sec_c = tk.LabelFrame(f, text="tags",
                               padx=6, pady=4)
        sec_c.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._build_section_keywords(sec_c)

        # Fields to Extract
        sec_d = tk.LabelFrame(f, text="extract", padx=6, pady=4)
        sec_d.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._build_section_fields(sec_d)

        # Staging Field Mapping
        sec_stg = tk.LabelFrame(f, text="Staging Field Mapping", padx=6, pady=4)
        sec_stg.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._build_section_staging(sec_stg)

    # ------------------------------------------------------------------
    # Section: Extracted Text
    # ------------------------------------------------------------------

    def _build_section_text(self, parent):
        # Text widget with its own scrollbar
        text_frame = tk.Frame(parent)
        text_frame.pack(fill=tk.BOTH, expand=True)

        text_sb = ttk.Scrollbar(text_frame, orient="vertical")
        preview = tk.Text(text_frame, height=20, font=("Courier", 8),
                          wrap=tk.WORD, yscrollcommand=text_sb.set)
        text_sb.config(command=preview.yview)
        preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Read-only but selectable
        _nav = {"Left", "Right", "Up", "Down", "Home", "End",
                "Prior", "Next", "Shift_L", "Shift_R", "Control_L", "Control_R"}

        def _readonly_key(e, nav=_nav):
            if e.keysym in nav:
                return None
            if (e.state & 0x4) and e.keysym.lower() in ("a", "c"):
                return None
            if (e.state & 0x1) and e.keysym in (
                "Left", "Right", "Up", "Down", "Home", "End",
            ):
                return None
            return "break"
        preview.bind("<Key>", _readonly_key)

        # Search highlight tag
        preview.tag_configure("search_hl", background="yellow")

        self._text_preview = preview

        # Bottom bar: [Population] button + search field (right-aligned)
        bottom = tk.Frame(parent)
        bottom.pack(fill=tk.X, pady=(4, 0))

        # Pack from right: ▼, ▲, search entry, search label, population button
        self._search_var = tk.StringVar()

        tk.Button(bottom, text="\u25bc", font=("Courier", 8), width=2,
                  command=self._search_next).pack(side=tk.RIGHT, padx=(2, 0))
        tk.Button(bottom, text="\u25b2", font=("Courier", 8), width=2,
                  command=self._search_prev).pack(side=tk.RIGHT, padx=(2, 0))

        search_entry = tk.Entry(bottom, textvariable=self._search_var,
                                width=20, font=("Courier", 8))
        search_entry.pack(side=tk.RIGHT, padx=(4, 0))
        search_entry.bind("<Return>", lambda e: self._search_next())

        tk.Label(bottom, text="Search:", font=("Courier", 8)).pack(
            side=tk.RIGHT)

        tk.Button(bottom, text="Population", font=("Courier", 8),
                  command=self._route_to_population).pack(
            side=tk.RIGHT, padx=(0, 12))

    # ------------------------------------------------------------------
    # Section: Keyword Population
    # ------------------------------------------------------------------

    def _build_section_population(self, parent):
        tk.Label(
            parent,
            text="Select route per keyword, then click Process",
            font=("Courier", 7), fg="gray",
        ).pack(anchor="w", pady=(0, 4))

        # Column headers above radio buttons (centered over each column)
        hdr = tk.Frame(parent)
        hdr.pack(fill=tk.X)
        # Spacer for delete button + keyword label
        tk.Label(hdr, text="", width=3).pack(side=tk.LEFT, padx=(0, 2))
        tk.Label(hdr, text="", width=22).pack(side=tk.LEFT)
        for name in ("tags", "extract", "skip"):
            tk.Label(hdr, text=name, font=("Courier", 7, "bold"),
                     width=7, anchor="center").pack(side=tk.LEFT, padx=1)

        # Container for keyword rows
        self._kw_rows_frame = tk.Frame(parent)
        self._kw_rows_frame.pack(fill=tk.X)

        # Bottom bar: Process + write-in
        bottom = tk.Frame(parent)
        bottom.pack(fill=tk.X, pady=(6, 0))

        tk.Button(bottom, text="Process", font=("Courier", 8, "bold"),
                  command=self._process_population).pack(
            side=tk.LEFT, padx=(0, 12))

        tk.Label(bottom, text="write-in:",
                 font=("Courier", 8)).pack(side=tk.LEFT)
        self._kw_write_in = tk.StringVar()
        tk.Entry(bottom, textvariable=self._kw_write_in,
                 width=20, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
        tk.Button(bottom, text="+", font=("Courier", 8),
                  command=self._add_write_in_population).pack(side=tk.LEFT)

        # Count label
        self._kw_count_label = tk.Label(
            parent, text="Showing 0 keywords",
            font=("Courier", 7), fg="gray",
        )
        self._kw_count_label.pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------------
    # Section: Doc_Type Fields (right column, top)
    # ------------------------------------------------------------------

    def _build_section_dtype(self, parent):
        _hint = ("Courier", 7)
        g = tk.Frame(parent)
        g.pack(fill=tk.X)

        row = 0
        tk.Label(g, text="Type Name: *",
                 font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=4, pady=3)
        self._name_var = tk.StringVar()
        tk.Entry(g, textvariable=self._name_var, width=34).grid(
            row=row, column=1, sticky="w", padx=4, pady=3)
        tk.Label(g, text="(auto-added to keywords)",
                 font=_hint, fg="gray").grid(row=row, column=2, sticky="w")

        row += 1
        tk.Label(g, text="Naming Pattern: *",
                 font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=4, pady=3)
        self._naming_var = tk.StringVar(value="{original_name}_{date}")
        tk.Entry(g, textvariable=self._naming_var, width=34).grid(
            row=row, column=1, sticky="w", padx=4, pady=3)
        tk.Label(g, text="{field_name} tokens",
                 font=_hint, fg="gray").grid(row=row, column=2, sticky="w")

        row += 1
        tk.Label(g, text="Container Formats: *",
                 font=("Courier", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=4, pady=3)
        self._formats_var = tk.StringVar()
        tk.Entry(g, textvariable=self._formats_var, width=34).grid(
            row=row, column=1, sticky="w", padx=4, pady=3)
        tk.Label(g, text="e.g. .pdf,.docx",
                 font=_hint, fg="gray").grid(row=row, column=2, sticky="w")

        row += 1
        tk.Label(g, text="Destination Subfolder:",
                 font=("Courier", 9)).grid(
            row=row, column=0, sticky="w", padx=4, pady=3)
        self._dest_var = tk.StringVar()
        tk.Entry(g, textvariable=self._dest_var, width=34).grid(
            row=row, column=1, sticky="w", padx=4, pady=3)
        tk.Label(g, text="(optional)",
                 font=_hint, fg="gray").grid(row=row, column=2, sticky="w")

        row += 1
        tk.Label(g, text="Content Patterns:",
                 font=("Courier", 9)).grid(
            row=row, column=0, sticky="nw", padx=4, pady=3)
        self._patterns_text = tk.Text(g, width=34, height=3,
                                      font=("Courier", 9))
        self._patterns_text.grid(row=row, column=1, sticky="w", padx=4, pady=3)
        tk.Label(g, text="one regex/line (optional)",
                 font=_hint, fg="gray").grid(row=row, column=2, sticky="nw")

        row += 1
        tk.Label(g, text="MIME Types:",
                 font=("Courier", 9)).grid(
            row=row, column=0, sticky="w", padx=4, pady=3)
        self._mime_var = tk.StringVar()
        tk.Entry(g, textvariable=self._mime_var, width=34).grid(
            row=row, column=1, sticky="w", padx=4, pady=3)
        tk.Label(g, text="comma-sep (optional)",
                 font=_hint, fg="gray").grid(row=row, column=2, sticky="w")

    # ------------------------------------------------------------------
    # Section: Keywords to Identify Doc_Type (right column)
    # ------------------------------------------------------------------

    def _build_section_keywords(self, parent):
        tk.Label(parent,
                 text="These keywords drive doc_type classification scoring",
                 font=("Courier", 7), fg="gray").pack(anchor="w", pady=(0, 4))

        list_frame = tk.Frame(parent)
        list_frame.pack(fill=tk.X)
        sb = ttk.Scrollbar(list_frame, orient="vertical")
        self._kw_listbox = tk.Listbox(
            list_frame, height=6, selectmode=tk.EXTENDED,
            font=("Courier", 9), yscrollcommand=sb.set,
        )
        sb.config(command=self._kw_listbox.yview)
        self._kw_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Minimum hits
        thresh_frame = tk.Frame(parent)
        thresh_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(thresh_frame, text="Minimum hits:",
                 font=("Courier", 8)).pack(side=tk.LEFT)
        self._threshold_var = tk.IntVar(value=2)
        tk.Spinbox(thresh_frame, from_=1, to=20,
                   textvariable=self._threshold_var,
                   width=5).pack(side=tk.LEFT, padx=4)

        # Add + Remove
        ctrl_frame = tk.Frame(parent)
        ctrl_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(ctrl_frame, text="add:",
                 font=("Courier", 8)).pack(side=tk.LEFT)
        self._kw_add_var = tk.StringVar()
        tk.Entry(ctrl_frame, textvariable=self._kw_add_var,
                 width=20, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
        tk.Button(ctrl_frame, text="+", font=("Courier", 8),
                  command=self._add_write_in_keyword).pack(
            side=tk.LEFT, padx=(0, 8))
        tk.Button(ctrl_frame, text="Remove Selected", font=("Courier", 8),
                  command=self._remove_selected_keywords).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Section: Fields to Extract (right column)
    # ------------------------------------------------------------------

    def _build_section_fields(self, parent):
        # Column headers for field rows (right-aligned over controls)
        hdr = tk.Frame(parent)
        hdr.pack(fill=tk.X)
        # Right side labels matching control positions (pack right-to-left)
        tk.Label(hdr, text="", width=4).pack(side=tk.RIGHT)          # delete spacer
        tk.Label(hdr, text="name_ref", font=("Courier", 7, "bold")).pack(
            side=tk.RIGHT, padx=(0, 4))
        tk.Label(hdr, text="opt", font=("Courier", 7, "bold"),
                 width=4).pack(side=tk.RIGHT, padx=1)
        tk.Label(hdr, text="req", font=("Courier", 7, "bold"),
                 width=4).pack(side=tk.RIGHT, padx=1)

        self._fields_container = tk.Frame(parent)
        self._fields_container.pack(fill=tk.X)

        tk.Button(parent, text="+ Add Field", font=("Courier", 8),
                  command=self._add_field_row).pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------------
    # Section: Staging Field Mapping (right column, bottom)
    # ------------------------------------------------------------------

    def _build_section_staging(self, parent):
        tk.Label(parent,
                 text="Maps extraction fields to coded filename slots. "
                      "Dropdown shows keywords + field names; type to enter manually.",
                 font=("Courier", 7), fg="gray", wraplength=400,
                 justify="left").pack(anchor="w", pady=(0, 4))

        staging_frame = tk.Frame(parent)
        staging_frame.pack(fill=tk.X)

        self._staging_vars = {}
        for i, slot in enumerate(_STAGING_SLOTS):
            tk.Label(staging_frame, text=f"{slot}:",
                     font=("Courier", 8)).grid(
                row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            combo = ttk.Combobox(staging_frame, textvariable=var, width=30)
            combo.grid(row=i, column=1, sticky="w", padx=4, pady=2)
            self._staging_vars[slot] = (var, combo)

    # ------------------------------------------------------------------
    # Mousewheel helper
    # ------------------------------------------------------------------

    def _bind_mousewheel(self, canvas):
        """Bind mousewheel scrolling to the given canvas."""
        canvas.bind("<Enter>", lambda e: self.bind_all(
            "<MouseWheel>",
            lambda ev: canvas.yview_scroll(
                int(-1 * (ev.delta / 120)), "units"),
        ))

    # ------------------------------------------------------------------
    # Search in extracted text
    # ------------------------------------------------------------------

    def _collect_search_matches(self, query):
        """Find all match positions for *query* and highlight them."""
        preview = self._text_preview
        preview.tag_remove("search_hl", "1.0", tk.END)
        positions = []
        start = "1.0"
        while True:
            pos = preview.search(query, start, tk.END, nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(query)}c"
            preview.tag_add("search_hl", pos, end)
            positions.append(pos)
            start = end
        return positions

    def _search_next(self):
        """Find next match after current position, wrap at end."""
        query = self._search_var.get().strip()
        if not query or not self._text_preview:
            return
        preview = self._text_preview
        positions = self._collect_search_matches(query)
        if not positions:
            self._search_pos = "1.0"
            return
        # Find first match strictly after current position
        target = None
        for pos in positions:
            if preview.compare(pos, ">=", self._search_pos):
                target = pos
                break
        if target is None:
            target = positions[0]  # wrap to first
        preview.see(target)
        self._search_pos = f"{target}+1c"

    def _search_prev(self):
        """Find previous match before current position, wrap at beginning."""
        query = self._search_var.get().strip()
        if not query or not self._text_preview:
            return
        preview = self._text_preview
        positions = self._collect_search_matches(query)
        if not positions:
            self._search_pos = "1.0"
            return
        # Find last match strictly before current position
        target = None
        for pos in reversed(positions):
            if preview.compare(f"{pos}+1c", "<", self._search_pos):
                target = pos
                break
        if target is None:
            target = positions[-1]  # wrap to last
        preview.see(target)
        self._search_pos = f"{target}+1c"

    # ------------------------------------------------------------------
    # Populate helpers
    # ------------------------------------------------------------------

    def _populate_text_preview(self):
        """Fill extracted text section with document text."""
        self._text_preview.config(state=tk.NORMAL)
        self._text_preview.delete("1.0", tk.END)
        self._text_preview.insert("1.0", (self._extracted_text or "")[:5000])
        self._search_pos = "1.0"

    def _populate_population(self):
        """Fill keyword population with top 20 keywords from analysis."""
        for w in self._kw_rows_frame.winfo_children():
            w.destroy()
        self._kw_route_rows = []
        self._kw_deleted = set()
        self._processed_extracts = set()

        if not self._doc_analysis:
            return

        kw_pool = self._doc_analysis.get("suggested_keywords", [])
        for kw in kw_pool[:20]:
            self._add_kw_to_population(kw)
        self._update_kw_count()

    # ------------------------------------------------------------------
    # Extracted text → routing
    # ------------------------------------------------------------------

    def _get_text_selection(self) -> str | None:
        """Return the currently selected text from the preview, or None."""
        if not self._text_preview:
            return None
        try:
            return self._text_preview.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            return None

    def _route_to_population(self):
        """Add selected text from extracted text to keyword population."""
        sel = self._get_text_selection()
        if not sel:
            return
        self._add_kw_to_population(sel)
        self._update_kw_count()

    # ------------------------------------------------------------------
    # Keyword population row management
    # ------------------------------------------------------------------

    def _add_kw_to_population(self, kw):
        """Add a keyword row with radio buttons to the population."""
        displayed = {r[0].lower() for r in self._kw_route_rows}
        if (kw.lower() in displayed
                or kw.lower() in {d.lower() for d in self._kw_deleted}):
            return

        row_f = tk.Frame(self._kw_rows_frame)
        row_f.pack(fill=tk.X, pady=1)

        # Delete button (trashcan)
        tk.Button(
            row_f, text="\U0001f5d1", font=("Segoe UI Emoji", 8),
            width=3, fg="red",
            command=lambda r=row_f, k=kw: self._remove_kw_from_population(r, k),
        ).pack(side=tk.LEFT, padx=(0, 2))

        # Keyword label
        tk.Label(row_f, text=kw, font=("Courier", 8, "bold"),
                 width=22, anchor="w").pack(side=tk.LEFT)

        # Radio buttons — single-select: tags / extract / skip
        route_var = tk.StringVar(value="skip")
        for val in ("tags", "extract", "skip"):
            tk.Radiobutton(row_f, text="", variable=route_var,
                           value=val, font=("Courier", 7),
                           width=5).pack(side=tk.LEFT, padx=1)

        self._kw_route_rows.append((kw, route_var, row_f))

    def _remove_kw_from_population(self, row_frame, keyword):
        """Delete a keyword row from population and track deletion."""
        self._kw_route_rows = [
            r for r in self._kw_route_rows if r[2] is not row_frame
        ]
        row_frame.destroy()
        self._kw_deleted.add(keyword)
        self._update_kw_count()

    def _update_kw_count(self):
        count = len(self._kw_route_rows)
        self._kw_count_label.config(text=f"Showing {count} keywords")

    def _add_write_in_population(self):
        """Add user-typed keyword to the population."""
        kw = self._kw_write_in.get().strip()
        if not kw:
            return
        self._add_kw_to_population(kw)
        self._kw_write_in.set("")
        self._update_kw_count()

    def _process_population(self):
        """Execute routing for all keywords based on radio selection.

        - skip: remove from population
        - tags: add to classification keywords
        - extract: create extraction field row with keyword prepopulation
        """
        to_remove = []

        for kw, route_var, row_f in self._kw_route_rows:
            route = route_var.get()
            if route == "skip":
                to_remove.append((kw, row_f))
                continue
            if route == "tags":
                self._add_kw_to_keywords(kw)
            elif route == "extract":
                if kw not in self._processed_extracts:
                    _fn, pattern, _role = self._keyword_to_field(kw)
                    self._add_field_row(name=kw, patterns=pattern, keyword=kw)
                    self._processed_extracts.add(kw)

        # Remove skipped rows from population
        for kw, row_f in to_remove:
            self._kw_route_rows = [
                r for r in self._kw_route_rows if r[2] is not row_f
            ]
            row_f.destroy()
            self._kw_deleted.add(kw)

        self._update_kw_count()
        self._refresh_staging_combos()

    # ------------------------------------------------------------------
    # Keyword → field conversion
    # ------------------------------------------------------------------

    def _keyword_to_field(self, keyword):
        """Convert a keyword to (field_name, pattern, ref_role)."""
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

    # ------------------------------------------------------------------
    # Classification keyword management (right column)
    # ------------------------------------------------------------------

    def _add_kw_to_keywords(self, kw):
        """Insert keyword into the classification listbox (deduped)."""
        existing = list(self._kw_listbox.get(0, tk.END))
        if kw.lower() not in {e.lower() for e in existing}:
            self._kw_listbox.insert(tk.END, kw)
            self._refresh_staging_combos()

    def _add_write_in_keyword(self):
        kw = self._kw_add_var.get().strip()
        if not kw:
            return
        self._add_kw_to_keywords(kw)
        self._kw_add_var.set("")

    def _remove_selected_keywords(self):
        sel = list(self._kw_listbox.curselection())
        for idx in reversed(sel):
            self._kw_listbox.delete(idx)
        self._refresh_staging_combos()

    # ------------------------------------------------------------------
    # Extraction field rows (right column)
    # ------------------------------------------------------------------

    def _add_field_row(self, name="", patterns="", required=True,
                       keyword="", **_kwargs):
        """Add a new extraction field row.

        When *keyword* is non-empty the raw keyword text is shown as a bold
        label to the left of the Field entry, and the field name entry is
        prepopulated with the keyword text.
        """
        row_frame = tk.Frame(self._fields_container)
        row_frame.pack(fill=tk.X, pady=2)

        # Keyword origin label (only when routed from population)
        if keyword:
            tk.Label(row_frame, text=keyword, font=("Courier", 8, "bold"),
                     fg="#4a90d9").pack(side=tk.LEFT, padx=(0, 4))

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

        # Delete button (trashcan) — pack right side first
        row_data = {}  # forward-declare so lambda can capture
        tk.Button(
            row_frame, text="\U0001f5d1", font=("Segoe UI Emoji", 8),
            width=3, fg="red",
            command=lambda: self._remove_field_row(row_data),
        ).pack(side=tk.RIGHT, padx=2)

        # name_ref checkbox
        name_ref_var = tk.BooleanVar(value=False)
        tk.Checkbutton(row_frame, text="name_ref", variable=name_ref_var,
                       font=("Courier", 7)).pack(side=tk.RIGHT, padx=(0, 4))

        # req/opt radio buttons
        req_var = tk.StringVar(value="req" if required else "opt")
        tk.Radiobutton(row_frame, text="opt", variable=req_var, value="opt",
                       font=("Courier", 7)).pack(side=tk.RIGHT, padx=1)
        tk.Radiobutton(row_frame, text="req", variable=req_var, value="req",
                       font=("Courier", 7)).pack(side=tk.RIGHT, padx=1)

        row_data.update({
            "frame": row_frame,
            "name": name_var,
            "patterns": patterns_var,
            "required": req_var,
            "name_ref": name_ref_var,
        })
        self._field_rows.append(row_data)

        self._refresh_staging_combos()
        name_var.trace_add("write", lambda *_: self._refresh_staging_combos())

    def _remove_field_row(self, row_data):
        row_data["frame"].destroy()
        self._field_rows.remove(row_data)
        self._refresh_staging_combos()

    # ------------------------------------------------------------------
    # Staging combo refresh
    # ------------------------------------------------------------------

    def _refresh_staging_combos(self):
        """Update staging dropdowns with keywords + field names."""
        # Collect field names
        field_names = [r["name"].get() for r in self._field_rows
                       if r["name"].get()]
        # Collect keywords
        keywords = list(self._kw_listbox.get(0, tk.END))
        # Merge, dedupe, sort
        all_values = sorted(set(field_names + keywords))
        values = [""] + all_values

        for slot, (var, combo) in self._staging_vars.items():
            current = var.get()
            combo["values"] = values
            # Keep current value even if it's manual (combobox is editable)

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

        # Keywords from listbox
        content_keywords = list(self._kw_listbox.get(0, tk.END))

        # Auto-prepend type_name if not already present
        if type_name and type_name.lower() not in {
            kw.lower() for kw in content_keywords
        }:
            content_keywords.insert(0, type_name)

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
                "required": row["required"].get() == "req",
            }
            if row["name_ref"].get():
                field_cfg["reference_lookup"] = {}
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
                text="\n".join(f"  \u2022 {e}" for e in errors), fg="red",
            )
        else:
            self._error_label.config(
                text="  Valid \u2014 ready to save.", fg="green",
            )

    def _save(self):
        type_name, type_def = self._collect()
        existing = self.config.type_definitions.get("types", {})
        errors = validate_type_definition(type_name, type_def, existing)
        if errors:
            self._error_label.config(
                text="\n".join(f"  \u2022 {e}" for e in errors), fg="red",
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
        messagebox.showinfo("Saved",
                            f"Type '{type_name}' created successfully.")

        return_path = self._return_file_path
        self._reset_form()

        if self.on_type_created:
            self.on_type_created(type_name, return_path)

    def _cancel(self):
        return_path = self._return_file_path
        self._reset_form()
        if self.on_type_created and return_path:
            self.on_type_created(None, return_path)

    def _reset_form(self):
        """Clear all sections back to defaults."""
        # Extracted text
        if self._text_preview:
            self._text_preview.config(state=tk.NORMAL)
            self._text_preview.delete("1.0", tk.END)
            self._text_preview.tag_remove("search_hl", "1.0", tk.END)
        self._search_var.set("")
        self._search_pos = "1.0"

        # Keyword population
        for w in self._kw_rows_frame.winfo_children():
            w.destroy()
        self._kw_route_rows = []
        self._kw_deleted = set()
        self._processed_extracts = set()
        self._kw_write_in.set("")
        self._update_kw_count()

        # Keywords listbox
        self._kw_listbox.delete(0, tk.END)
        self._threshold_var.set(2)
        self._kw_add_var.set("")

        # Field rows
        for row in list(self._field_rows):
            row["frame"].destroy()
        self._field_rows.clear()

        # Staging
        for slot, (var, combo) in self._staging_vars.items():
            var.set("")

        # Doc_type fields
        self._name_var.set("")
        self._naming_var.set("{original_name}_{date}")
        self._formats_var.set("")
        self._dest_var.set("")
        self._patterns_text.delete("1.0", tk.END)
        self._mime_var.set("")

        # Error + context
        self._error_label.config(text="")
        self._return_file_path = None
        self._extracted_text = None
        self._doc_analysis = None
        self._context_frame.pack_forget()
        self._hide_left_pane()
