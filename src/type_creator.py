# src/type_creator.py
"""Prompt user to define a new file type and persist it."""

import json
import pathlib


def create_new_type(config) -> str | None:
    """
    Walk the user through defining a new file type.
    Persists to type_definitions, folder_mappings, and naming_conventions.
    Returns the new type name, or None if cancelled.
    """
    print("\n--- Create New File Type ---\n")

    # -- Required fields --
    type_name = input("  Type name (e.g., bank_statement): ").strip().lower()
    if not type_name:
        print("  Cancelled -- type name cannot be empty.")
        return None

    # Check for duplicate
    existing = config.type_definitions.get("types", {})
    if type_name in existing:
        print(f"  Type '{type_name}' already exists. Use it instead.")
        return type_name

    container_formats = _prompt_list("  Container formats (e.g., .pdf,.docx): ")
    if not container_formats:
        print("  Cancelled -- at least one container format is required.")
        return None

    content_keywords = _prompt_list("  Content keywords (comma-separated, e.g., Invoice,Amount Due): ")
    if not content_keywords:
        print("  Cancelled -- at least one content keyword is required.")
        return None

    dest_subfolder = input("  Destination subfolder (e.g., Financial\\Invoices): ").strip()
    if not dest_subfolder:
        print("  Cancelled -- destination subfolder is required.")
        return None

    # -- Optional fields --
    print("\n  Optional fields (press Enter to skip):")
    mime_types = _prompt_list("  MIME types (comma-separated): ")
    content_patterns = _prompt_list("  Content patterns (regex, comma-separated): ")

    threshold_input = input("  Keyword threshold [2]: ").strip()
    keyword_threshold = int(threshold_input) if threshold_input.isdigit() else 2

    naming_input = input("  Naming pattern [{original_name}_{date}]: ").strip()
    naming_pattern = naming_input if naming_input else "{original_name}_{date}"

    # -- Auto-assign the next available 3-digit code --
    next_code = _next_available_code(existing)

    # -- Build the type definition --
    new_type = {
        "code": next_code,
        "container_formats": container_formats,
        "mime_types": mime_types,
        "content_keywords": content_keywords,
        "content_patterns": content_patterns,
        "keyword_threshold": keyword_threshold,
        "destination_subfolder": dest_subfolder,
        "naming_pattern": naming_pattern,
    }

    # -- Confirm before saving --
    print(f"\n  New type '{type_name}':")
    print(f"    Code:         {next_code}")
    print(f"    Formats:      {container_formats}")
    print(f"    Keywords:     {content_keywords}")
    print(f"    Patterns:     {content_patterns}")
    print(f"    Threshold:    {keyword_threshold}")
    print(f"    Destination:  {dest_subfolder}")
    print(f"    Naming:       {naming_pattern}")

    confirm = input("\n  Save this type? [Y/n]: ").strip().lower()
    if confirm not in ("", "y", "yes"):
        print("  Cancelled.")
        return None

    # -- Persist to all config files --
    _persist_type(type_name, new_type, dest_subfolder, naming_pattern, config)

    print(f"  Type '{type_name}' saved and ready for use.")
    return type_name


def _next_available_code(existing_types: dict) -> str:
    """Find the next available 3-digit code, skipping '000' (reserved)."""
    used = set()
    for type_def in existing_types.values():
        code = type_def.get("code", "")
        if code.isdigit():
            used.add(int(code))
    # Start at 1 (skip 000 = reserved for unknown/unclassified)
    candidate = 1
    while candidate in used:
        candidate += 1
    return str(candidate).zfill(3)


def _prompt_list(prompt: str) -> list[str]:
    """Prompt for a comma-separated list, return cleaned list."""
    raw = input(prompt).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _persist_type(
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

    # 4. Reload config cache so the new type is immediately available
    config.reload()
