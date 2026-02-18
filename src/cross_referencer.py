# src/cross_referencer.py
"""Generic, config-driven field cross-referencing."""

import re
from datetime import datetime

from src.fuzzy_matcher import fuzzy_match_with_support


def _build_new_entry(
    raw_value: str,
    extracted_fields: dict,
    field_cfg: dict,
    type_defs_fields: dict,
) -> tuple[str, dict]:
    """
    Build a new reference entry from extracted fields.

    Stores all non-cross-reference fields as metadata on the entry
    (generalises the old create_vendor_entry logic).

    Returns:
        (key, entry_dict) where key is a slug of the raw value.
    """
    key = re.sub(r"[^a-z0-9]+", "_", raw_value.lower()).strip("_")

    entry = {
        "name": raw_value,
        "aliases": [],
        "date_added": datetime.now().strftime("%Y-%m-%d"),
    }

    # Attach values from all non-cross-reference extracted fields
    for other_name, other_value in extracted_fields.items():
        other_cfg = type_defs_fields.get(other_name, {})
        if other_cfg.get("cross_reference"):
            continue
        if other_value:
            entry[other_name] = other_value

    return key, entry


def cross_reference_fields(
    extracted_fields: dict,
    extracted_text: str,
    type_name: str,
    config,
    logger=None,
) -> tuple[dict, list]:
    """
    Cross-reference extracted fields against their configured reference files.

    For each field that has a ``cross_reference`` config key:
    1. Load the reference file via config.load_reference()
    2. Build supporting values from other extracted fields
    3. Call fuzzy_match_with_support() with the layered lookup
    4. Match found -> substitute canonical value
    5. No match + create_if_missing -> create new entry, save, log
    6. No match + not create_if_missing -> add to unresolved, log failure

    Args:
        extracted_fields: Dict of {field_name: extracted_value}.
        extracted_text: Full OCR text (used for building new entries).
        type_name: The document type name.
        config: ConfigLoader instance.
        logger: Optional AutoFilerLogger instance.

    Returns:
        (resolved_fields, unresolved_fields_list)
    """
    type_defs = config.type_definitions
    type_cfg = type_defs.get("types", {}).get(type_name, {})
    all_field_defs = type_cfg.get("extraction_fields", {})
    threshold = config.settings.get("fuzzy_match_threshold", 0.80)

    resolved = dict(extracted_fields)
    unresolved = []

    for field_name, field_cfg in all_field_defs.items():
        ref_path = field_cfg.get("cross_reference")
        if not ref_path:
            continue

        raw_value = resolved.get(field_name, "")
        if not raw_value:
            continue

        ref_key = field_cfg.get("reference_key", "entries")
        supporting_field_names = field_cfg.get("supporting_fields", [])
        create_if_missing = field_cfg.get("create_if_missing", False)

        # 1. Load reference
        ref_data = config.load_reference(ref_path)
        entries = ref_data.get(ref_key, {})

        # 2. Build supporting values
        supporting_values = {}
        for sf in supporting_field_names:
            val = extracted_fields.get(sf)
            if val:
                supporting_values[sf] = val

        # 3. Fuzzy match with support
        matched_key, _ = fuzzy_match_with_support(
            raw_value, entries, threshold, supporting_values
        )

        if matched_key:
            # 4. Substitute canonical value
            resolved[field_name] = entries[matched_key]["name"]
        elif create_if_missing:
            # 5. Auto-create new entry
            new_key, new_entry = _build_new_entry(
                raw_value, extracted_fields, field_cfg, all_field_defs
            )
            ref_data.setdefault(ref_key, {})[new_key] = new_entry
            config.save_reference(ref_path, ref_data)
            if logger:
                logger.log_reference_entry(field_name, raw_value, new_entry)
        else:
            # 6. Unresolved
            unresolved.append(field_name)
            if logger:
                logger.log_cross_reference_failure(
                    field_name, raw_value, ref_path
                )

    return resolved, unresolved
