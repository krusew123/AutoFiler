# src/config_learner.py
"""Persist user-approved learning to type_definitions.json."""

import json
import pathlib
import re
import threading


_config_lock = threading.Lock()


def _read_modify_write(config, mutator):
    """
    Thread-safe read-modify-write of type_definitions.json.

    *mutator* receives the parsed dict and returns it after modification.
    After writing, the config cache is reloaded.
    """
    with _config_lock:
        config_root = pathlib.Path(config.settings["config_path"])
        td_path = config_root / "type_definitions.json"
        td = json.loads(td_path.read_text(encoding="utf-8"))
        td = mutator(td)
        td_path.write_text(json.dumps(td, indent=2), encoding="utf-8")
        config.reload("type_definitions.json")
    return td


def add_keywords_to_type(
    type_name: str,
    new_keywords: list[str],
    config,
) -> int:
    """
    Add keywords to a type's content_keywords list (deduplicated).

    Returns the count of keywords actually added.
    """
    added = 0

    def mutator(td):
        nonlocal added
        typedef = td["types"].get(type_name)
        if not typedef:
            return td
        existing = set(kw.lower() for kw in typedef.get("content_keywords", []))
        for kw in new_keywords:
            if kw.lower() not in existing:
                typedef.setdefault("content_keywords", []).append(kw)
                existing.add(kw.lower())
                added += 1
        return td

    _read_modify_write(config, mutator)
    return added


def add_patterns_to_type(
    type_name: str,
    new_patterns: list[str],
    config,
) -> int:
    """
    Add content_patterns to a type (deduplicated, regex-validated).

    Returns the count of patterns actually added.
    """
    added = 0

    def mutator(td):
        nonlocal added
        typedef = td["types"].get(type_name)
        if not typedef:
            return td
        existing = set(typedef.get("content_patterns", []))
        for pattern in new_patterns:
            # Validate regex
            try:
                re.compile(pattern)
            except re.error:
                continue
            if pattern not in existing:
                typedef.setdefault("content_patterns", []).append(pattern)
                existing.add(pattern)
                added += 1
        return td

    _read_modify_write(config, mutator)
    return added


def add_extraction_patterns(
    type_name: str,
    field_name: str,
    new_patterns: list[str],
    config,
) -> int:
    """
    Add extraction patterns to a specific field (deduplicated, regex-validated).

    Returns the count of patterns actually added.
    """
    added = 0

    def mutator(td):
        nonlocal added
        typedef = td["types"].get(type_name)
        if not typedef:
            return td
        field_defs = typedef.setdefault("extraction_fields", {})
        field_cfg = field_defs.get(field_name)
        if not field_cfg:
            return td
        existing = set(field_cfg.get("patterns", []))
        for pattern in new_patterns:
            try:
                re.compile(pattern)
            except re.error:
                continue
            if pattern not in existing:
                field_cfg.setdefault("patterns", []).append(pattern)
                existing.add(pattern)
                added += 1
        return td

    _read_modify_write(config, mutator)
    return added


def add_extraction_field(
    type_name: str,
    field_name: str,
    field_config: dict,
    config,
):
    """
    Add a new extraction field definition to a type.

    field_config example:
        {"patterns": [...], "required": True, "reference_lookup": {"role": "vendor"}}
    """
    def mutator(td):
        typedef = td["types"].get(type_name)
        if not typedef:
            return td
        field_defs = typedef.setdefault("extraction_fields", {})
        if field_name not in field_defs:
            field_defs[field_name] = field_config
        return td

    _read_modify_write(config, mutator)
