# src/review_queue.py
"""Manage the queue of files awaiting manual review."""

import json
import pathlib
from datetime import datetime


class ReviewQueue:
    """Tracks review files and their statuses."""

    STATUSES = ("pending", "in_review", "resolved")

    def __init__(self, review_path: str, config_path: str):
        self._review_dir = pathlib.Path(review_path)
        self._state_file = pathlib.Path(config_path) / "review_state.json"
        self._state: dict = self._load_state()

    # -- State persistence --

    def _load_state(self) -> dict:
        if self._state_file.exists():
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        return {"files": {}}

    def _save_state(self):
        self._state_file.write_text(
            json.dumps(self._state, indent=2), encoding="utf-8"
        )

    # -- Queue operations --

    def scan(self) -> list[str]:
        """
        Scan the review folder and register any new files as pending.
        Returns the list of pending file paths sorted by modified time.
        """
        for item in self._review_dir.iterdir():
            if item.is_file():
                key = item.name
                if key not in self._state["files"]:
                    self._state["files"][key] = {
                        "status": "pending",
                        "added": datetime.now().isoformat(),
                        "resolved_as": None,
                    }
        self._save_state()
        return self.pending()

    def pending(self) -> list[str]:
        """Return file paths with status 'pending', oldest first."""
        names = [
            name
            for name, info in self._state["files"].items()
            if info["status"] == "pending"
        ]
        # Sort by modified time (oldest first)
        names.sort(
            key=lambda n: (self._review_dir / n).stat().st_mtime
            if (self._review_dir / n).exists()
            else 0
        )
        return [str(self._review_dir / n) for n in names]

    def mark_in_review(self, file_path: str):
        name = pathlib.Path(file_path).name
        if name in self._state["files"]:
            self._state["files"][name]["status"] = "in_review"
            self._save_state()

    def mark_resolved(self, file_path: str, resolved_as: str):
        name = pathlib.Path(file_path).name
        if name in self._state["files"]:
            self._state["files"][name]["status"] = "resolved"
            self._state["files"][name]["resolved_as"] = resolved_as
            self._state["files"][name]["resolved_at"] = datetime.now().isoformat()
            self._save_state()

    def summary(self) -> dict:
        """Return counts by status."""
        counts = {"pending": 0, "in_review": 0, "resolved": 0}
        for info in self._state["files"].values():
            counts[info["status"]] = counts.get(info["status"], 0) + 1
        return counts
