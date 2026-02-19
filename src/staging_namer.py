# src/staging_namer.py
"""Generate coded staging filenames from document type and extracted fields."""

import os
import re
from datetime import datetime


# Date formats to attempt when parsing extracted date strings
_DATE_FORMATS = [
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
]

_FALLBACK = "000"


def _sanitize(text: str) -> str:
    """Remove characters that are illegal in Windows filenames."""
    return re.sub(r'[<>:"/\\|?*]', "", text).strip()


def _truncate_left(value: str, max_len: int) -> str:
    """Return the leftmost *max_len* characters."""
    return value[:max_len].strip()


def _truncate_right(value: str, max_len: int) -> str:
    """Return the rightmost *max_len* characters."""
    return value[-max_len:].strip() if len(value) > max_len else value.strip()


def _parse_date(raw: str, file_path: str | None = None) -> str:
    """
    Convert a raw date string to YYYYMMDD.

    Falls back to the file's modified date, then to "000".
    """
    if raw:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(raw.strip(), fmt).strftime("%Y%m%d")
            except ValueError:
                continue

    # Fallback: file modified date
    if file_path:
        try:
            mtime = os.path.getmtime(file_path)
            return datetime.fromtimestamp(mtime).strftime("%Y%m%d")
        except OSError:
            pass

    return _FALLBACK


def generate_staging_name(
    type_name: str,
    type_config: dict,
    extracted_fields: dict,
    file_path: str,
) -> tuple[str, dict]:
    """
    Build a staging filename and a dict of modified (truncated) field values.

    Format: {code}_{vendor}_{customer}_{date}_{reference}_{amount}

    Args:
        type_name: The classified document type name.
        type_config: The type's config dict (from type_definitions).
        extracted_fields: Dict of extracted field values.
        file_path: Path to the source file (used for date fallback).

    Returns:
        (staging_stem, modified_fields) — stem has no extension.
    """
    code = type_config.get("code", _FALLBACK).zfill(3)
    staging_map = type_config.get("staging_fields", {})

    def _resolve(slot: str) -> str:
        field_name = staging_map.get(slot)
        if not field_name:
            return ""
        return (extracted_fields or {}).get(field_name, "") or ""

    raw_vendor = _resolve("vendor")
    raw_customer = _resolve("customer")
    raw_date = _resolve("date")
    raw_reference = _resolve("reference")
    raw_amount = _resolve("amount")

    mod_vendor = _truncate_left(raw_vendor, 15) if raw_vendor else _FALLBACK
    mod_customer = _truncate_left(raw_customer, 15) if raw_customer else _FALLBACK
    mod_date = _parse_date(raw_date, file_path)
    mod_reference = _truncate_right(raw_reference, 15) if raw_reference else _FALLBACK
    mod_amount = _truncate_right(raw_amount, 9) if raw_amount else _FALLBACK

    modified_fields = {
        "vendor": mod_vendor,
        "customer": mod_customer,
        "date": mod_date,
        "reference": mod_reference,
        "amount": mod_amount,
    }

    stem = f"{code}_{mod_vendor}_{mod_customer}_{mod_date}_{mod_reference}_{mod_amount}"
    stem = _sanitize(stem)

    return stem, modified_fields
