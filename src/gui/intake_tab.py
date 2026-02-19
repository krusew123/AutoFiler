# src/gui/intake_tab.py
"""Intake watcher tab — extracted from autofiler_gui.py."""

import os
import tkinter as tk
from tkinter import scrolledtext
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.pipeline import process_file

# Minimum seconds between processing the same file path
_DEDUP_WINDOW = 5


class IntakeHandler(FileSystemEventHandler):
    """Handle new files arriving in the intake folder."""

    def __init__(self, config, logger, log_callback):
        self.config = config
        self.logger = logger
        self.log_callback = log_callback
        self._recently_processed: dict[str, float] = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = os.path.normpath(event.src_path)

        # Deduplicate: skip if this path was processed within the window
        with self._lock:
            now = time.monotonic()
            last = self._recently_processed.get(file_path, 0)
            if now - last < _DEDUP_WINDOW:
                return
            self._recently_processed[file_path] = now

            # Prune old entries
            cutoff = now - _DEDUP_WINDOW * 2
            self._recently_processed = {
                k: v for k, v in self._recently_processed.items()
                if v > cutoff
            }

        self.log_callback(f"Detected: {file_path}")
        time.sleep(1)

        # Verify the file still exists (may have been moved by a prior event)
        if not os.path.isfile(file_path):
            self.log_callback(f"  Skipped (already moved): {file_path}")
            return

        try:
            self.config.reload()
            result = process_file(file_path, self.config, self.logger)
            decision = result.get("routing", {}).get("decision", "unknown")
            best = result.get("best_type", "none")
            self.log_callback(f"  Processed: {decision} | type={best}")
        except Exception as e:
            # pipeline.py already logs errors before re-raising
            self.log_callback(f"  ERROR: {e}")


class IntakeTab(tk.Frame):
    """Watcher service UI in a tab frame."""

    def __init__(self, parent, ctx, **kwargs):
        super().__init__(parent, **kwargs)
        self.root = ctx["root"]
        self.config = ctx["config"]
        self.af_logger = ctx["logger"]
        self.intake = self.config.settings["intake_path"]

        self.observer = None
        self.running = False

        self._build_ui()

    def _build_ui(self):
        # -- Top frame: status and path --
        top = tk.Frame(self, padx=10, pady=8)
        top.pack(fill=tk.X)

        self.status_dot = tk.Label(top, text="\u25cf", fg="gray",
                                   font=("Arial", 14))
        self.status_dot.pack(side=tk.LEFT)

        self.status_label = tk.Label(top, text="Stopped",
                                     font=("Courier", 11, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=(6, 0))

        # -- Path display --
        path_frame = tk.Frame(self, padx=10)
        path_frame.pack(fill=tk.X)
        tk.Label(path_frame, text="Watching:",
                 font=("Courier", 9)).pack(side=tk.LEFT)
        tk.Label(path_frame, text=self.intake,
                 font=("Courier", 9, "bold")).pack(side=tk.LEFT, padx=(4, 0))

        # -- Buttons --
        btn_frame = tk.Frame(self, padx=10, pady=8)
        btn_frame.pack(fill=tk.X)

        self.start_btn = tk.Button(btn_frame, text="Start",
                                   width=12, command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = tk.Button(btn_frame, text="Stop",
                                  width=12, command=self.stop,
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        # -- Log area --
        log_frame = tk.LabelFrame(self, text="Activity Log",
                                  padx=6, pady=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log_area = scrolledtext.ScrolledText(
            log_frame, height=14, state=tk.DISABLED,
            font=("Courier", 9), wrap=tk.WORD
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _log(self, message):
        """Thread-safe append to the log widget."""
        def _append():
            self.log_area.config(state=tk.NORMAL)
            ts = time.strftime("%H:%M:%S")
            self.log_area.insert(tk.END, f"[{ts}] {message}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)
        self.root.after(0, _append)

    def start(self):
        if self.running:
            return
        self.running = True

        handler = IntakeHandler(self.config, self.af_logger, self._log)
        self.observer = Observer()
        self.observer.schedule(handler, self.intake, recursive=False)
        self.observer.start()

        self.status_dot.config(fg="#22c55e")
        self.status_label.config(text="Running")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._log("Watcher started.")

    def stop(self):
        if not self.running:
            return
        self.running = False

        if self.observer:
            self.observer.stop()
            threading.Thread(target=self.observer.join, daemon=True).start()
            self.observer = None

        self.status_dot.config(fg="gray")
        self.status_label.config(text="Stopped")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._log("Watcher stopped.")

    def shutdown(self):
        """Gracefully stop the watcher (called on app close)."""
        self.stop()
