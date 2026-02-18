# src/guards.py
"""Pre-processing guards to catch edge cases before classification."""

import os
import pathlib


class FileGuardError(Exception):
    """Raised when a file fails a pre-processing guard check."""
    pass


def check_file(file_path: str) -> str | None:
    """
    Run all guard checks on a file.
    Returns None if the file is OK, or an error reason string.
    """
    p = pathlib.Path(file_path)

    # File must exist
    if not p.exists():
        return "file_not_found"

    # Must be a file, not a directory
    if not p.is_file():
        return "not_a_file"

    # Zero-byte files cannot be classified
    if p.stat().st_size == 0:
        return "zero_byte_file"

    # Check if file is still being written (can't open exclusively)
    try:
        with open(file_path, "rb") as f:
            f.read(1)
    except (PermissionError, OSError):
        return "file_locked"

    # Skip common temp/system files
    if p.name.startswith(".") or p.name.startswith("~$"):
        return "temp_or_hidden_file"
    if p.suffix.lower() in (".tmp", ".crdownload", ".partial"):
        return "incomplete_download"

    # Check for password-protected PDFs (OCR will fail)
    if p.suffix.lower() == ".pdf":
        try:
            with open(file_path, "rb") as f:
                header = f.read(4096)
                if b"/Encrypt" in header:
                    return "password_protected_pdf"
        except Exception:
            pass

    return None
