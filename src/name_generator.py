# src/name_generator.py
"""Resolve naming convention patterns into actual filenames."""

import pathlib
from datetime import datetime


def generate_name(
    file_path: str,
    type_name: str,
    naming_conventions: dict,
    counter: int = 0,
) -> str:
    """
    Resolve the naming pattern for a given type into a concrete filename.

    Supported placeholders:
        {original_name} - original filename without extension
        {date}          - current date in the configured format
        {type}          - the matched type name
        {counter}       - incrementing counter (for batch operations)

    Returns:
        The generated filename WITHOUT extension.
    """
    patterns = naming_conventions.get("patterns", {})
    date_fmt = naming_conventions.get("date_format", "%Y-%m-%d")
    separator = naming_conventions.get("separator", "_")
    lowercase = naming_conventions.get("lowercase", False)

    pattern = patterns.get(type_name, "{original_name}{separator}{date}")

    original = pathlib.Path(file_path).stem
    date_str = datetime.now().strftime(date_fmt)

    name = pattern.replace("{original_name}", original)
    name = name.replace("{date}", date_str)
    name = name.replace("{type}", type_name)
    name = name.replace("{counter}", str(counter))
    name = name.replace("{separator}", separator)

    if lowercase:
        name = name.lower()

    # Sanitize: remove characters illegal in Windows filenames
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "")

    return name.strip()
