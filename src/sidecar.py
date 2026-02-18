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
    filing_result: dict,
    doc_type: str,
    confidence_score: float | None,
    extracted_fields: dict | None,
    extracted_text: str,
    sidecar_path: str,
    file_hash: str,
) -> str:
    """
    Write a JSON sidecar file for a filed document.

    Args:
        source_file_path: Original intake file path.
        filing_result: Dict returned by filer.file_to_destination().
        doc_type: Classified document type name.
        confidence_score: Classification confidence score.
        extracted_fields: Dict of extracted field values (may be None).
        extracted_text: Full OCR text.
        sidecar_path: Root directory for sidecar files.
        file_hash: SHA-256 hex digest of the source file.

    Returns:
        The path to the written sidecar JSON file.
    """
    sidecar_dir = pathlib.Path(sidecar_path)
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    source_name = pathlib.Path(source_file_path).stem
    sidecar_file = sidecar_dir / f"{source_name}.json"

    sidecar_data = {
        "schema_version": "1.0",
        "processing_timestamp": datetime.now().isoformat(),
        "source_file": source_file_path,
        "source_hash": file_hash,
        "document_type": doc_type,
        "confidence_score": confidence_score,
        "extracted_fields": extracted_fields or {},
        "destination": filing_result.get("destination"),
        "ocr_text": extracted_text,
    }

    sidecar_file.write_text(
        json.dumps(sidecar_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return str(sidecar_file)
