# src/filer.py
"""Move classified files to their destination with proper naming."""

import shutil
import pathlib
from datetime import datetime


def resolve_destination(
    type_name: str,
    destination_root: str,
    folder_mappings: dict,
    extracted_fields: dict | None = None,
) -> pathlib.Path:
    """
    Return the full destination directory for a given type.
    Replaces {field_name} placeholders in the subfolder using extracted_fields.
    Creates the directory if it does not exist.
    """
    subfolder = folder_mappings.get(type_name)
    if subfolder is None:
        raise ValueError(f"No folder mapping found for type: {type_name}")

    # Replace extracted field placeholders in subfolder path
    if extracted_fields:
        for field_name, field_value in extracted_fields.items():
            # Sanitize field value for use in directory names
            safe_value = field_value
            for ch in '<>:"/|?*':
                safe_value = safe_value.replace(ch, "")
            subfolder = subfolder.replace(f"{{{field_name}}}", safe_value.strip())

    dest = pathlib.Path(destination_root) / subfolder
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def resolve_duplicate(target: pathlib.Path) -> pathlib.Path:
    """
    If the target path already exists, append a timestamp suffix
    to make the filename unique.
    """
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_target = target.parent / f"{stem}_{timestamp}{suffix}"

    # Extremely rare: same-second collision
    counter = 1
    while new_target.exists():
        new_target = target.parent / f"{stem}_{timestamp}_{counter}{suffix}"
        counter += 1

    return new_target


def file_to_destination(
    file_path: str,
    generated_name: str,
    type_name: str,
    destination_root: str,
    folder_mappings: dict,
    extracted_fields: dict | None = None,
) -> dict:
    """
    Move a file to its type-specific destination with the generated name.

    Returns:
        {
            "source": str,
            "destination": str,
            "type_name": str,
            "duplicate_handled": bool
        }
    """
    dest_dir = resolve_destination(type_name, destination_root, folder_mappings, extracted_fields)
    extension = pathlib.Path(file_path).suffix
    target = dest_dir / f"{generated_name}{extension}"

    duplicate = target.exists()
    target = resolve_duplicate(target)

    shutil.move(file_path, str(target))

    return {
        "source": file_path,
        "destination": str(target),
        "type_name": type_name,
        "duplicate_handled": duplicate,
    }
