# review.py
"""Entry point to launch a manual review session."""

from src.config_loader import ConfigLoader
from src.logger import AutoFilerLogger
from src.review_session import run_review_session

if __name__ == "__main__":
    config = ConfigLoader(r"C:\AutoFiler\Config")
    logger = AutoFilerLogger(config.settings["log_path"])
    run_review_session(config, logger)
