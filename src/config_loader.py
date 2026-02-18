# src/config_loader.py
"""Load and cache JSON configuration files."""

import json
import pathlib


class ConfigLoader:
    """Loads config files from the config directory and caches them in memory."""

    def __init__(self, config_path: str):
        self._root = pathlib.Path(config_path)
        self._cache: dict = {}

    def _load(self, relative_path: str) -> dict:
        """Load a JSON file relative to the config root, with caching."""
        if relative_path not in self._cache:
            full = self._root / relative_path
            self._cache[relative_path] = json.loads(
                full.read_text(encoding="utf-8")
            )
        return self._cache[relative_path]

    def _save(self, relative_path: str, data: dict):
        """Write JSON data to a config file and update the cache."""
        full = self._root / relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._cache[relative_path] = data

    def load_reference(self, relative_path: str) -> dict:
        """Load a reference JSON file relative to the config root."""
        return self._load(relative_path)

    def save_reference(self, relative_path: str, data: dict):
        """Persist updated reference data to disk."""
        self._save(relative_path, data)

    def reload(self, relative_path: str | None = None):
        """Clear cache for one file or all files, forcing a fresh read."""
        if relative_path:
            self._cache.pop(relative_path, None)
        else:
            self._cache.clear()

    @property
    def settings(self) -> dict:
        return self._load("settings.json")

    @property
    def type_definitions(self) -> dict:
        return self._load("type_definitions.json")

    @property
    def classification_rules(self) -> dict:
        return self._load("References/classification_rules.json")

    @property
    def folder_mappings(self) -> dict:
        return self._load("References/folder_mappings.json")

    @property
    def naming_conventions(self) -> dict:
        return self._load("References/naming_conventions.json")

    @property
    def company_reference(self) -> dict:
        return self._load("References/company_reference.json")

    @property
    def vendor_reference(self) -> dict:
        return self._load("References/vendor_reference.json")
