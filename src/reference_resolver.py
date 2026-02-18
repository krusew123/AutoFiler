# src/reference_resolver.py
"""Resolve vendor and company names against reference files."""

import re
from datetime import datetime

from src.fuzzy_matcher import fuzzy_match


def resolve_company(
    customer_name: str,
    company_reference: dict,
    threshold: float,
) -> tuple[str | None, str | None]:
    """
    Fuzzy-match a customer_name against the company reference.

    Returns:
        (canonical_name, code) on match, or (None, None) on no match.
    """
    companies = company_reference.get("companies", {})
    if not customer_name or not companies:
        return None, None

    matched_key, _ = fuzzy_match(customer_name, companies, threshold)
    if matched_key:
        entry = companies[matched_key]
        return entry["name"], entry.get("code")

    return None, None


def resolve_vendor(
    vendor_name: str,
    vendor_reference: dict,
    threshold: float,
) -> tuple[str | None, str | None]:
    """
    Fuzzy-match a vendor_name against the vendor reference.

    Returns:
        (canonical_name, key) on match, or (None, None) on no match.
    """
    vendors = vendor_reference.get("vendors", {})
    if not vendor_name or not vendors:
        return None, None

    matched_key, _ = fuzzy_match(vendor_name, vendors, threshold)
    if matched_key:
        entry = vendors[matched_key]
        return entry["name"], matched_key

    return None, None


def _extract_vendor_field(pattern: str, text: str) -> str | None:
    """Try to extract a single field from text using a regex pattern."""
    try:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    except re.error:
        pass
    return None


def create_vendor_entry(
    vendor_name: str,
    extracted_text: str,
    vendor_extraction_fields: dict,
    invoice_number: str | None = None,
) -> tuple[str, dict]:
    """
    Build a new vendor reference entry from OCR-extracted text.

    Returns:
        (key, entry_dict) where key is a slug of the vendor name.
    """
    key = re.sub(r"[^a-z0-9]+", "_", vendor_name.lower()).strip("_")

    entry = {
        "name": vendor_name,
        "aliases": [],
        "date_added": datetime.now().strftime("%Y-%m-%d"),
        "added_from_invoice": invoice_number,
    }

    # Try to extract optional vendor fields from the OCR text
    for field_name, field_cfg in vendor_extraction_fields.items():
        patterns = field_cfg.get("patterns", [])
        for pattern in patterns:
            value = _extract_vendor_field(pattern, extracted_text)
            if value:
                entry[field_name] = value
                break

    return key, entry


def add_vendor_to_reference(key: str, entry: dict, config):
    """Add a new vendor entry to the reference and persist to disk."""
    vendor_ref = config.vendor_reference
    vendor_ref.setdefault("vendors", {})[key] = entry
    config.save_vendor_reference(vendor_ref)


def resolve_invoice_fields(
    extracted_fields: dict,
    extracted_text: str,
    config,
    logger=None,
) -> tuple[dict, bool]:
    """
    Resolve vendor and company names for an invoice.

    This is the single entry point used by both pipeline and review session.

    Returns:
        (resolved_fields, company_matched) where resolved_fields is a
        copy of extracted_fields with canonical names substituted, and
        company_matched indicates whether the company was found in the
        company reference.
    """
    resolved = dict(extracted_fields)
    threshold = config.settings.get("fuzzy_match_threshold", 0.80)
    type_defs = config.type_definitions

    # --- Company resolution ---
    customer_name = resolved.get("customer_name", "")
    company_matched = False
    if customer_name:
        canonical_company, code = resolve_company(
            customer_name, config.company_reference, threshold
        )
        if canonical_company:
            resolved["customer_name"] = canonical_company
            company_matched = True
        else:
            if logger:
                logger.log_company_suggestion(customer_name)

    # --- Vendor resolution ---
    vendor_name = resolved.get("vendor_name", "")
    if vendor_name:
        canonical_vendor, _ = resolve_vendor(
            vendor_name, config.vendor_reference, threshold
        )
        if canonical_vendor:
            resolved["vendor_name"] = canonical_vendor
        else:
            # Auto-create vendor entry
            vendor_extraction_fields = (
                type_defs.get("types", {})
                .get("invoice", {})
                .get("vendor_extraction_fields", {})
            )
            invoice_number = resolved.get("invoice_number")
            key, entry = create_vendor_entry(
                vendor_name, extracted_text,
                vendor_extraction_fields, invoice_number,
            )
            add_vendor_to_reference(key, entry, config)
            if logger:
                logger.log_new_vendor(vendor_name, entry)

    return resolved, company_matched
