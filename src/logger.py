# src/logger.py
"""Structured JSON-line logger for all AutoFiler actions."""

import json
import pathlib
import logging
from datetime import datetime


class AutoFilerLogger:
    """Writes structured log entries as JSON lines."""

    def __init__(self, log_path: str):
        self._log_path = pathlib.Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        # Also configure Python's logging for console output
        self._py_logger = logging.getLogger("autofiler")
        self._py_logger.setLevel(logging.INFO)
        if not self._py_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("[%(levelname)s] %(message)s")
            )
            self._py_logger.addHandler(handler)

    def _write(self, entry: dict):
        """Append a JSON-line entry to the log file."""
        entry["timestamp"] = datetime.now().isoformat()
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def log_auto_file(self, pipeline_result: dict):
        """Log an automatic filing action."""
        entry = {
            "action": "auto_file",
            "file": pipeline_result["classification"]["file_path"],
            "type": pipeline_result["best_type"],
            "score": pipeline_result["best_score"],
            "destination": pipeline_result["filing"]["destination"]
                if pipeline_result.get("filing") else None,
            "duplicate": pipeline_result["filing"]["duplicate_handled"]
                if pipeline_result.get("filing") else False,
        }
        self._write(entry)
        self._py_logger.info(
            f"Auto-filed: {entry['file']} -> {entry['destination']} "
            f"(type={entry['type']}, score={entry['score']})"
        )

    def log_review_route(self, file_path: str, reason: str, score: float | None):
        """Log a file being routed to review."""
        entry = {
            "action": "route_to_review",
            "file": file_path,
            "reason": reason,
            "score": score,
        }
        self._write(entry)
        self._py_logger.info(
            f"To review: {file_path} (reason={reason}, score={score})"
        )

    def log_manual_file(
        self, file_path: str, type_name: str, destination: str, new_type: bool
    ):
        """Log a file classified and filed during manual review."""
        entry = {
            "action": "manual_file",
            "file": file_path,
            "type": type_name,
            "destination": destination,
            "new_type_created": new_type,
        }
        self._write(entry)
        self._py_logger.info(
            f"Manual filed: {file_path} -> {destination} "
            f"(type={type_name}, new={new_type})"
        )

    def log_skip(self, file_path: str):
        """Log a file skipped during review."""
        entry = {"action": "review_skip", "file": file_path}
        self._write(entry)
        self._py_logger.info(f"Skipped: {file_path}")

    def log_extraction(self, file_path: str, text_length: int, method: str):
        """Log a text extraction event."""
        entry = {
            "action": "text_extraction",
            "file": file_path,
            "text_length": text_length,
            "method": method,
        }
        self._write(entry)
        self._py_logger.info(
            f"Extracted {text_length} chars from {file_path} via {method}"
        )

    def log_error(self, file_path: str, error: str):
        """Log an error during processing."""
        entry = {"action": "error", "file": file_path, "error": error}
        self._write(entry)
        self._py_logger.error(f"Error: {file_path} -- {error}")

    def log_reference_entry(self, field_name: str, raw_value: str, entry: dict):
        """Log automatic creation of a new reference entry."""
        log_entry = {
            "action": "reference_entry_created",
            "field": field_name,
            "raw_value": raw_value,
            "entry": entry,
        }
        self._write(log_entry)
        self._py_logger.info(
            f"New reference entry created for {field_name}: {raw_value}"
        )

    def log_cross_reference_failure(
        self, field_name: str, raw_value: str, reference_file: str
    ):
        """Log an unmatched cross-reference value."""
        entry = {
            "action": "cross_reference_failure",
            "field": field_name,
            "raw_value": raw_value,
            "reference_file": reference_file,
        }
        self._write(entry)
        self._py_logger.warning(
            f"Cross-reference failure for {field_name}: '{raw_value}' "
            f"not found in {reference_file}"
        )

    def log_new_type(self, type_name: str, definition: dict):
        """Log a new file type being created."""
        entry = {
            "action": "type_created",
            "type": type_name,
            "extensions": definition.get("extensions", []),
            "destination": definition.get("destination_subfolder", ""),
        }
        self._write(entry)
        self._py_logger.info(
            f"New type created: {type_name} -> {entry['destination']}"
        )
