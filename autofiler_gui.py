# autofiler_gui.py
"""Desktop GUI launcher for AutoFiler — tabbed interface."""

import tkinter as tk
from tkinter import ttk
from src.config_loader import ConfigLoader
from src.logger import AutoFilerLogger
from src.gui.intake_tab import IntakeTab
from src.gui.review_tab import ReviewTab
from src.gui.define_tab import DefineTab


class AutoFilerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoFiler")
        self.root.geometry("920x650")
        self.root.minsize(800, 550)

        # Shared context
        self.config = ConfigLoader(r"C:\AutoFiler\Config")
        self.af_logger = AutoFilerLogger(self.config.settings["log_path"])
        self.ctx = {
            "root": root,
            "config": self.config,
            "logger": self.af_logger,
        }

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # --- Tabs ---
        self.intake_tab = IntakeTab(self.notebook, self.ctx)
        self.review_tab = ReviewTab(
            self.notebook, self.ctx,
            on_define_new=self._switch_to_define,
        )
        self.define_tab = DefineTab(
            self.notebook, self.ctx,
            on_type_created=self._on_type_created,
        )

        self.notebook.add(self.intake_tab, text="  Intake  ")
        self.notebook.add(self.review_tab, text="  Review  ")
        self.notebook.add(self.define_tab, text="  Define  ")

    def _switch_to_define(self, return_file_path, extracted_text=None):
        """Called by Review tab when user clicks 'Define New Type'."""
        self.define_tab.set_return_context(return_file_path, extracted_text)
        self.notebook.select(self.define_tab)

    def _on_type_created(self, type_name, return_file_path):
        """Called by Define tab after save. Switches back to Review."""
        self.notebook.select(self.review_tab)
        if return_file_path:
            self.review_tab.resume_with_type(type_name, return_file_path)

    def _on_close(self):
        self.intake_tab.shutdown()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoFilerGUI(root)
    root.mainloop()
