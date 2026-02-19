# src/field_resolver.py
"""Resolve extracted name fields against a unified entity reference file."""

import re
from datetime import date

from src.fuzzy_matcher import fuzzy_match

REF_PATH = "References/fieldname_ref.json"


def resolve_fields(
    extracted_fields: dict,
    missing_fields: list,
    extracted_text: str,
    type_name: str,
    config,
    logger=None,
) -> tuple[dict, list, dict]:
    """
    Resolve name fields against the entity reference file.

    For each extraction field that has a ``reference_lookup`` config:
      - Scenario A (regex got a value): fuzzy-match against ref file.
        Match → use canonical name. No match → auto-create new entity.
      - Scenario B (regex missed): scan OCR text for known entity names.
        Found → fill in the field. Not found → field stays missing.

    Returns:
        (resolved_fields, still_missing, resolution_info)
    """
    types = config.type_definitions.get("types", {})
    typedef = types.get(type_name, {})
    field_defs = typedef.get("extraction_fields", {})
    doc_type_code = typedef.get("code", "000")

    reference_entries = config.load_reference(REF_PATH)
    resolved_fields = dict(extracted_fields)
    still_missing = list(missing_fields)
    resolution_info: dict = {}
    ref_changed = False

    for field_name, field_cfg in field_defs.items():
        lookup = field_cfg.get("reference_lookup")
        if not lookup:
            continue

        role = lookup["role"]

        # Pre-filter entries by role for this field
        if role:
            role_filtered = {
                k: v for k, v in reference_entries.items()
                if role in v.get("roles", [])
            }
        else:
            role_filtered = reference_entries

        if field_name in extracted_fields:
            # Scenario A — regex got a value
            raw_value = extracted_fields[field_name]
            matched_key, ratio = fuzzy_match(
                raw_value, role_filtered, threshold=0.80
            )

            if matched_key:
                canonical = reference_entries[matched_key]["name"]
                resolved_fields[field_name] = canonical
                _update_entity_metadata(
                    reference_entries[matched_key], role, doc_type_code
                )
                ref_changed = True
                resolution_info[field_name] = {
                    "method": "fuzzy_match",
                    "raw_value": raw_value,
                    "resolved_value": canonical,
                    "entity_key": matched_key,
                    "ratio": round(ratio, 4),
                }
                if logger:
                    logger.log_field_resolved(
                        field_name, "fuzzy_match", raw_value, canonical, ratio
                    )
            else:
                # Auto-create new entity
                entity_key, entity_dict = create_entity(
                    raw_value, role, doc_type_code, reference_entries
                )
                reference_entries[entity_key] = entity_dict
                ref_changed = True
                resolution_info[field_name] = {
                    "method": "auto_created",
                    "raw_value": raw_value,
                    "resolved_value": raw_value,
                    "entity_key": entity_key,
                    "ratio": 1.0,
                }
                if logger:
                    logger.log_field_resolved(
                        field_name, "auto_created", raw_value, raw_value, 1.0
                    )

        elif field_name in missing_fields:
            # Scenario B — regex missed, scan OCR text (role-filtered)
            matched_key, canonical, confidence = scan_text_for_entities(
                extracted_text, reference_entries, threshold=0.95,
                role=role,
            )

            if matched_key:
                resolved_fields[field_name] = canonical
                still_missing.remove(field_name)
                _update_entity_metadata(
                    reference_entries[matched_key], role, doc_type_code
                )
                ref_changed = True
                resolution_info[field_name] = {
                    "method": "text_scan",
                    "raw_value": None,
                    "resolved_value": canonical,
                    "entity_key": matched_key,
                    "ratio": round(confidence, 4),
                }
                if logger:
                    logger.log_field_resolved(
                        field_name, "text_scan", "", canonical, confidence
                    )
            else:
                resolution_info[field_name] = {
                    "method": "unresolved",
                    "raw_value": None,
                    "resolved_value": None,
                    "entity_key": None,
                    "ratio": 0.0,
                }
                if logger:
                    logger.log_field_unresolved(field_name, type_name)

    if ref_changed:
        config.save_reference(REF_PATH, reference_entries)

    return resolved_fields, still_missing, resolution_info


def scan_text_for_entities(
    text: str,
    reference_entries: dict,
    threshold: float = 0.95,
    role: str | None = None,
) -> tuple[str | None, str | None, float]:
    """
    Two-pass scan of OCR text for known entity names/aliases.

    Pass 1 — substring: check if any canonical name or alias appears in text.
    Pass 2 — fuzzy line match: compare each text line against entity names.

    When *role* is provided, only entities whose ``roles`` list contains
    that role are considered.  This prevents a customer entity from being
    matched when scanning for a vendor field (and vice-versa).

    Returns:
        (matched_key, canonical_name, confidence) or (None, None, 0.0)
    """
    if not text or not reference_entries:
        return None, None, 0.0

    # Pre-filter entries by role when specified
    if role:
        filtered = {
            k: v for k, v in reference_entries.items()
            if role in v.get("roles", [])
        }
    else:
        filtered = reference_entries

    if not filtered:
        return None, None, 0.0

    text_lower = text.lower()

    # Pass 1 — substring search (case-insensitive)
    for key, entry in filtered.items():
        candidates = [entry.get("name", "")]
        candidates.extend(entry.get("aliases", []))

        for candidate in candidates:
            if not candidate:
                continue
            if candidate.lower() in text_lower:
                return key, entry["name"], 1.0

    # Pass 2 — fuzzy line match
    lines = text.splitlines()
    best_key = None
    best_name = None
    best_ratio = 0.0

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        matched_key, ratio = fuzzy_match(
            line_stripped, filtered, threshold=threshold
        )
        if matched_key and ratio > best_ratio:
            best_key = matched_key
            best_name = filtered[matched_key]["name"]
            best_ratio = ratio

    if best_key:
        return best_key, best_name, best_ratio

    return None, None, 0.0


def create_entity(
    raw_value: str,
    role: str,
    doc_type_code: str,
    reference_entries: dict,
) -> tuple[str, dict]:
    """
    Create a new entity entry from a raw extracted value.

    Returns:
        (entity_key, entity_dict)
    """
    base_key = _generate_entity_key(raw_value)
    entity_key = base_key

    # Handle key collisions
    suffix = 2
    while entity_key in reference_entries:
        entity_key = f"{base_key}_{suffix}"
        suffix += 1

    entity_dict = {
        "name": raw_value,
        "aliases": [],
        "roles": [role],
        "doc_types": [doc_type_code],
        "date_added": date.today().isoformat(),
    }

    return entity_key, entity_dict


def _generate_entity_key(name: str) -> str:
    """Slugify a name to a reference key.

    "William Kruse & Company LLC" -> "william_kruse_company_llc"
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def _update_entity_metadata(entity: dict, role: str, doc_type_code: str):
    """Idempotent append to roles and doc_types lists."""
    if role not in entity.get("roles", []):
        entity.setdefault("roles", []).append(role)
    if doc_type_code not in entity.get("doc_types", []):
        entity.setdefault("doc_types", []).append(doc_type_code)
