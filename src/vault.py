# src/vault.py
"""Archive original files to the vault with a coded prefix."""

import pathlib
import shutil
from datetime import datetime


def archive_to_vault(
    file_path: str,
    doc_type_code: str,
    vault_path: str,
    placeholder: str = "0",
) -> str:
    """
    Copy the original file to the vault directory with a coded prefix.

    Vault filename format: {3-digit code}{1-digit placeholder}{original_filename}
    Example: invoice (code 003) named "Stericycle Invoice.pdf" -> "0030Stericycle Invoice.pdf"

    Args:
        file_path: Path to the original file.
        doc_type_code: 3-digit document type code.
        vault_path: Root directory for vault storage.
        placeholder: Single alphanumeric character (default "0").

    Returns:
        The full path to the archived file in the vault.
    """
    vault_dir = pathlib.Path(vault_path)
    vault_dir.mkdir(parents=True, exist_ok=True)

    original_name = pathlib.Path(file_path).name
    coded_name = f"{doc_type_code}{placeholder}{original_name}"
    dest = vault_dir / coded_name

    # Handle duplicates with timestamp suffix
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        coded_name = f"{stem}_{ts}{suffix}"
        dest = vault_dir / coded_name

    shutil.copy2(file_path, dest)
    return str(dest)
