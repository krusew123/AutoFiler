# src/type_creator_core.py
"""GUI-friendly type creation logic — no input()/print()."""

import json
import pathlib
import re


def next_available_code(existing_types: dict) -> str:
    """Find the next available 3-digit code, skipping '000' (reserved)."""
    used = set()
    for type_def in existing_types.values():
        code = type_def.get("code", "")
        if code.isdigit():
            used.add(int(code))
    candidate = 1
    while candidate in used:
        candidate += 1
    return str(candidate).zfill(3)


def validate_type_definition(
    type_name: str,
    type_def: dict,
    existing_types: dict,
) -> list[str]:
    """
    Validate a type definition before persisting.

    Returns a list of error messages (empty = valid).
    """
    errors = []

    # Name checks
    if not type_name:
        errors.append("Type name is required.")
    elif not re.match(r"^[a-z][a-z0-9_]*$", type_name):
        errors.append("Type name must be lowercase letters, digits, and underscores, starting with a letter.")
    if type_name in existing_types:
        errors.append(f"Type '{type_name}' already exists.")

    # Container formats
    formats = type_def.get("container_formats", [])
    if not formats:
        errors.append("At least one container format is required.")
    for fmt in formats:
        if not fmt.startswith("."):
            errors.append(f"Container format '{fmt}' must start with a dot.")

    # Content keywords
    if not type_def.get("content_keywords"):
        errors.append("At least one content keyword is required.")

    # Destination subfolder
    if not type_def.get("destination_subfolder"):
        errors.append("Destination subfolder is required.")

    # Naming pattern
    if not type_def.get("naming_pattern"):
        errors.append("Naming pattern is required.")

    # Content patterns — validate regex compilation
    for pattern in type_def.get("content_patterns", []):
        try:
            re.compile(pattern)
        except re.error as e:
            errors.append(f"Invalid content pattern '{pattern}': {e}")

    # Extraction fields — validate pattern regexes
    for field_name, field_cfg in type_def.get("extraction_fields", {}).items():
        for pattern in field_cfg.get("patterns", []):
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"Invalid extraction pattern for '{field_name}': '{pattern}' — {e}")

    # Keyword threshold
    threshold = type_def.get("keyword_threshold", 2)
    if not isinstance(threshold, int) or threshold < 1:
        errors.append("Keyword threshold must be an integer >= 1.")

    return errors


def build_type_definition(
    type_name: str,
    code: str,
    container_formats: list[str],
    content_keywords: list[str],
    destination_subfolder: str,
    naming_pattern: str,
    mime_types: list[str] | None = None,
    content_patterns: list[str] | None = None,
    keyword_threshold: int = 2,
    extraction_fields: dict | None = None,
    staging_fields: dict | None = None,
) -> dict:
    """
    Build a complete type definition dict ready for persistence.
    """
    return {
        "code": code,
        "container_formats": container_formats,
        "mime_types": mime_types or [],
        "content_keywords": content_keywords,
        "content_patterns": content_patterns or [],
        "keyword_threshold": keyword_threshold,
        "destination_subfolder": destination_subfolder,
        "naming_pattern": naming_pattern,
        "staging_fields": staging_fields or {},
        "extraction_fields": extraction_fields or {},
    }


def persist_type(
    type_name: str,
    type_def: dict,
    dest_subfolder: str,
    naming_pattern: str,
    config,
):
    """Write the new type to all three config files and reload cache."""
    config_root = pathlib.Path(config.settings["config_path"])

    # 1. type_definitions.json
    td_path = config_root / "type_definitions.json"
    td = json.loads(td_path.read_text(encoding="utf-8"))
    td["types"][type_name] = type_def
    td_path.write_text(json.dumps(td, indent=2), encoding="utf-8")

    # 2. folder_mappings.json
    fm_path = config_root / "References" / "folder_mappings.json"
    fm = json.loads(fm_path.read_text(encoding="utf-8"))
    fm[type_name] = dest_subfolder
    fm_path.write_text(json.dumps(fm, indent=2), encoding="utf-8")

    # 3. naming_conventions.json
    nc_path = config_root / "References" / "naming_conventions.json"
    nc = json.loads(nc_path.read_text(encoding="utf-8"))
    nc["patterns"][type_name] = naming_pattern
    nc_path.write_text(json.dumps(nc, indent=2), encoding="utf-8")

    # 4. Reload config cache
    config.reload()
