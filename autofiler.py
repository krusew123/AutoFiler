# autofiler.py
"""Entry point to start the AutoFiler watcher service."""

import os
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.config_loader import ConfigLoader
from src.logger import AutoFilerLogger
from src.pipeline import process_file

# Minimum seconds between processing the same file path
_DEDUP_WINDOW = 5


class IntakeHandler(FileSystemEventHandler):
    """Handle new files arriving in the intake folder."""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
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

        # Small delay to let file writes finish
        time.sleep(1)

        # Verify the file still exists (may have been moved by a prior event)
        if not os.path.isfile(file_path):
            return

        try:
            self.config.reload()
            process_file(file_path, self.config, self.logger)
        except Exception:
            pass  # pipeline.py already logs errors before re-raising


if __name__ == "__main__":
    config = ConfigLoader(r"C:\AutoFiler\Config")
    logger = AutoFilerLogger(config.settings["log_path"])
    settings = config.settings

    handler = IntakeHandler(config, logger)
    observer = Observer()
    observer.schedule(handler, settings["intake_path"], recursive=False)
    observer.start()

    print(f"AutoFiler watching: {settings['intake_path']}")
    print(f"Threshold: {settings['confidence_threshold']}")
    print(f"Log: {settings['log_path']}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(settings.get("polling_interval", 5))
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    print("\nAutoFiler stopped.")
