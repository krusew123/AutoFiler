# src/sidecar.py
"""JSON sidecar generation and file hashing."""

import hashlib
import json
import pathlib
from datetime import datetime


def hash_file(file_path: str) -> str:
    """Return the SHA-256 hex digest of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def generate_sidecar(
    source_file_path: str,
    doc_type: str,
    doc_type_code: str,
    confidence_score: float | None,
    extracted_fields: dict | None,
    modified_fields: dict,
    staging_filename: str,
    vault_path: str,
    extracted_text: str,
    sidecar_path: str,
    file_hash: str,
    resolution_info: dict | None = None,
    review_info: dict | None = None,
) -> str:
    """
    Write a JSON sidecar file alongside a staged document.

    Args:
        source_file_path: Original intake file path.
        doc_type: Classified document type name.
        doc_type_code: 3-digit type code.
        confidence_score: Classification confidence score.
        extracted_fields: Dict of extracted field values (may be None).
        modified_fields: Dict of truncated staging field values.
        staging_filename: The coded staging filename (with extension).
        vault_path: Path to the archived original in the vault.
        extracted_text: Full OCR text.
        sidecar_path: Directory for sidecar files (same as staging dir).
        file_hash: SHA-256 hex digest of the source file.

    Returns:
        The path to the written sidecar JSON file.
    """
    sidecar_dir = pathlib.Path(sidecar_path)
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    staging_stem = pathlib.Path(staging_filename).stem
    sidecar_file = sidecar_dir / f"{staging_stem}.json"

    sidecar_data = {
        "schema_version": "1.2",
        "processing_timestamp": datetime.now().isoformat(),
        "source_file": source_file_path,
        "source_hash": file_hash,
        "vault_file": vault_path,
        "document_type": doc_type,
        "doc_type_code": doc_type_code,
        "confidence_score": confidence_score,
        "extracted_fields": extracted_fields or {},
        "modified_fields": modified_fields,
        "staging_filename": staging_stem,
        "resolution_info": resolution_info or {},
        "ocr_text": extracted_text,
    }

    if review_info is not None:
        sidecar_data["review_info"] = review_info

    sidecar_file.write_text(
        json.dumps(sidecar_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return str(sidecar_file)
