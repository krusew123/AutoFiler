# src/gui/define_tab.py
"""Define tab — guided type creation form."""

import tkinter as tk
from tkinter import ttk, messagebox

from src.type_creator_core import (
    next_available_code,
    validate_type_definition,
    build_type_definition,
    persist_type,
)


# Staging slot names in display order
_STAGING_SLOTS = ["vendor", "customer", "date", "reference", "amount"]


class DefineTab(tk.Frame):
    """Scrollable form for creating a new document type."""

    def __init__(self, parent, ctx, on_type_created=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.root = ctx["root"]
        self.config = ctx["config"]
        self.af_logger = ctx["logger"]
        self.on_type_created = on_type_created

        # Return context when linked from Review tab
        self._return_file_path = None

        # Dynamic extraction field rows
        self._field_rows = []

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_return_context(self, file_path):
        """Set context for returning to Review tab after save."""
        self._return_file_path = file_path
        if file_path:
            self._context_banner.config(
                text=f"Defining type for: {file_path}",
            )
            self._context_frame.pack(fill=tk.X, padx=10, pady=(4, 0),
                                     before=self._form_canvas)
        else:
            self._context_frame.pack_forget()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Title
        title = tk.Label(self, text="DEFINE NEW DOCUMENT TYPE",
                         font=("Courier", 12, "bold"))
        title.pack(pady=(10, 4))

        # Context banner (hidden until set_return_context)
        self._context_frame = tk.Frame(self, bg="#fff3cd", padx=8, pady=4)
        self._context_banner = tk.Label(
            self._context_frame, text="", bg="#fff3cd",
            font=("Courier", 9), anchor="w",
        )
        self._context_banner.pack(fill=tk.X)
        # Don't pack _context_frame by default — shown only when linked

        # Scrollable canvas for the form
        self._form_canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical",
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
        self._form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                               padx=(10, 0), pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)

        # Bind mousewheel scrolling
        self._form_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._form_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            ),
        )

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
        sep = ttk.Separator(f, orient="horizontal")
        sep.grid(row=row, column=0, columnspan=3, sticky="ew",
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

        add_btn = tk.Button(f, text="+ Add Field", command=self._add_field_row)
        add_btn.grid(row=row, column=2, sticky="e", padx=6)

        # --- Staging Field Mapping ---
        row = self._next_field_row + 1
        sep2 = ttk.Separator(f, orient="horizontal")
        sep2.grid(row=row, column=0, columnspan=3, sticky="ew",
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
        name_entry = tk.Entry(row_frame, textvariable=name_var, width=14)
        name_entry.pack(side=tk.LEFT, padx=(0, 4))

        patterns_var = tk.StringVar(value=patterns)
        tk.Label(row_frame, text="Patterns:", font=("Courier", 8)).pack(
            side=tk.LEFT, padx=(0, 2))
        pat_entry = tk.Entry(row_frame, textvariable=patterns_var, width=20)
        pat_entry.pack(side=tk.LEFT, padx=(0, 4))

        req_var = tk.BooleanVar(value=required)
        tk.Checkbutton(row_frame, text="Req", variable=req_var).pack(
            side=tk.LEFT, padx=(0, 4))

        ref_var = tk.StringVar(value=ref_role)
        tk.Label(row_frame, text="Ref role:", font=("Courier", 8)).pack(
            side=tk.LEFT, padx=(0, 2))
        ref_entry = tk.Entry(row_frame, textvariable=ref_var, width=10)
        ref_entry.pack(side=tk.LEFT, padx=(0, 4))

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
        self._context_frame.pack_forget()
