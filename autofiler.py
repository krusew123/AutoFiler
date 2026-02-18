# autofiler.py
"""Entry point to start the AutoFiler watcher service."""

import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from src.config_loader import ConfigLoader
from src.logger import AutoFilerLogger
from src.pipeline import process_file


class IntakeHandler(FileSystemEventHandler):
    """Handle new files arriving in the intake folder."""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def on_created(self, event):
        if event.is_directory:
            return
        # Small delay to let file writes finish
        time.sleep(1)
        try:
            self.config.reload()
            process_file(event.src_path, self.config, self.logger)
        except Exception as e:
            self.logger.log_error(event.src_path, str(e))


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
