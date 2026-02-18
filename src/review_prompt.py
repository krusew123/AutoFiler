# src/review_prompt.py
"""Interactive terminal prompts for manual file review."""

import pathlib
from src.detectors import detect_extension, detect_mime, get_file_metadata


def display_file_info(
    file_path: str,
    scored_candidates: dict | None = None,
    extracted_text: str = "",
):
    """Print a summary of the file to help the user classify it."""
    p = pathlib.Path(file_path)
    meta = get_file_metadata(file_path)
    ext = detect_extension(file_path)
    mime = detect_mime(file_path)

    print("\n" + "=" * 60)
    print(f"  FILE REVIEW")
    print("=" * 60)
    print(f"  Name:      {p.name}")
    print(f"  Extension: {ext}")
    print(f"  MIME type: {mime}")
    print(f"  Size:      {meta['file_size']:,} bytes")
    print(f"  Created:   {meta['created']}")

    if extracted_text:
        preview = extracted_text[:500]
        print(f"\n  Extracted Text Preview:")
        print(f"  {'-' * 40}")
        for line in preview.split("\n"):
            print(f"    {line}")
        if len(extracted_text) > 500:
            print(f"    ... ({len(extracted_text) - 500} more characters)")
        print(f"  {'-' * 40}")

    if scored_candidates:
        print(f"\n  Partial matches found:")
        for name, data in scored_candidates.items():
            signals = ", ".join(data["matched_signals"])
            print(f"    {name}: score {data['score']} ({signals})")

    print("=" * 60)


def prompt_type_selection(type_definitions: dict) -> tuple[str, str]:
    """
    Ask the user to select an existing type or create a new one.

    Returns:
        (action, type_name) where action is 'existing' or 'new'
    """
    existing = list(type_definitions.get("types", {}).keys())

    print("\nOptions:")
    print("  [1] Assign an existing type")
    print("  [2] Create a new type")
    print("  [3] Skip (leave in review)")
    print()

    while True:
        choice = input("Select [1/2/3]: ").strip()
        if choice == "1":
            return _select_existing_type(existing)
        elif choice == "2":
            return ("new", "")
        elif choice == "3":
            return ("skip", "")
        print("  Invalid choice. Enter 1, 2, or 3.")


def _select_existing_type(type_names: list[str]) -> tuple[str, str]:
    """Display numbered list of types and let the user pick one."""
    print("\nExisting types:")
    for i, name in enumerate(type_names, 1):
        print(f"  [{i}] {name}")
    print()

    while True:
        raw = input(f"Enter number (1-{len(type_names)}): ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(type_names):
                return ("existing", type_names[idx])
        except ValueError:
            pass
        print(f"  Invalid. Enter a number between 1 and {len(type_names)}.")
