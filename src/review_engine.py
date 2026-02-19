# src/review_engine.py
"""Stateless orchestrator for the two-phase review pipeline."""

import pathlib
import shutil

from src.classifier import classify_file
from src.scorer import score_candidates, select_best_candidate
from src.content_matcher import extract_fields
from src.field_resolver import resolve_fields, create_entity, _update_entity_metadata
from src.gap_analyzer import analyze_classification_gap, analyze_extraction_gap
from src.sidecar import generate_sidecar, hash_file
from src.staging_namer import generate_staging_name
from src.vault import archive_to_vault

REF_PATH = "References/fieldname_ref.json"


def classify_review_file(file_path: str, config) -> dict:
    """
    Run classification + scoring on a file already in the review folder.

    Returns:
        {
            "classification": dict,
            "scored_candidates": dict,
            "best_type": str | None,
            "best_score": float | None,
            "extracted_text": str,
        }
    """
    classification = classify_file(file_path, config)
    rules = config.classification_rules
    scored = score_candidates(classification, rules)
    best_type, best_data = select_best_candidate(
        scored, rules.get("min_signals_required", 2)
    )
    best_score = best_data["score"] if best_data else None

    return {
        "classification": classification,
        "scored_candidates": scored,
        "best_type": best_type,
        "best_score": best_score,
        "extracted_text": classification.get("extracted_text", ""),
    }


def diagnose_classification(
    extracted_text: str,
    assigned_type: str,
    type_definitions: dict,
    scored_candidates: dict,
) -> dict:
    """Wrapper around gap_analyzer.analyze_classification_gap."""
    return analyze_classification_gap(
        extracted_text, assigned_type, type_definitions, scored_candidates
    )


def attempt_extraction(
    file_path: str,
    extracted_text: str,
    type_name: str,
    config,
    logger=None,
) -> dict:
    """
    Run extract_fields + resolve_fields for the assigned type.

    Returns:
        {
            "extracted_fields": dict,
            "missing_fields": list,
            "resolution_info": dict,
            "success": bool,
        }
    """
    extracted_fields, missing = extract_fields(
        extracted_text, type_name, config.type_definitions
    )

    extracted_fields, missing, resolution_info = resolve_fields(
        extracted_fields, missing, extracted_text,
        type_name, config, logger,
    )

    return {
        "extracted_fields": extracted_fields,
        "missing_fields": missing,
        "resolution_info": resolution_info,
        "success": len(missing) == 0,
    }


def diagnose_extraction(
    extracted_text: str,
    type_name: str,
    type_definitions: dict,
    extracted_fields: dict,
    missing_fields: list,
) -> dict:
    """Wrapper around gap_analyzer.analyze_extraction_gap."""
    return analyze_extraction_gap(
        extracted_text, type_name, type_definitions,
        extracted_fields, missing_fields,
    )


def stage_file(
    file_path: str,
    type_name: str,
    extracted_fields: dict,
    resolution_info: dict,
    extracted_text: str,
    config,
    logger=None,
    manual_fields: dict | None = None,
    review_info: dict | None = None,
) -> dict:
    """
    Hash -> vault -> staging name -> move -> sidecar.

    Manual name-field values with reference_lookup are auto-added
    to fieldname_ref.json.

    Returns:
        {
            "staging_filename": str,
            "staging_file": str,
            "vault_file": str,
            "sidecar_file": str,
        }
    """
    settings = config.settings

    # Merge manual fields into extracted fields
    merged_fields = dict(extracted_fields)
    if manual_fields:
        merged_fields.update(manual_fields)
        # Auto-add manual name-field values to entity reference
        _auto_add_manual_references(
            manual_fields, type_name, config, logger
        )

    # Get type config
    type_cfg = config.type_definitions.get("types", {}).get(type_name, {})
    doc_type_code = type_cfg.get("code", "000")

    # Hash source file
    file_hash = hash_file(file_path)

    # Archive original to vault
    vault_file = archive_to_vault(
        file_path=file_path,
        doc_type_code=doc_type_code,
        vault_path=settings["vault_path"],
    )

    # Generate staging name + modified fields
    staging_stem, modified_fields = generate_staging_name(
        type_name=type_name,
        type_config=type_cfg,
        extracted_fields=merged_fields,
        file_path=file_path,
    )

    # Move file from review to staging
    staging_path = pathlib.Path(settings["staging_path"])
    staging_path.mkdir(parents=True, exist_ok=True)
    ext = pathlib.Path(file_path).suffix
    staging_filename = f"{staging_stem}{ext}"
    staged_dest = staging_path / staging_filename
    shutil.move(file_path, str(staged_dest))

    # Generate sidecar
    sidecar_file = generate_sidecar(
        source_file_path=file_path,
        doc_type=type_name,
        doc_type_code=doc_type_code,
        confidence_score=None,  # Manual review — no auto confidence
        extracted_fields=merged_fields,
        modified_fields=modified_fields,
        staging_filename=staging_filename,
        vault_path=vault_file,
        extracted_text=extracted_text,
        sidecar_path=settings["staging_path"],
        file_hash=file_hash,
        resolution_info=resolution_info,
        review_info=review_info,
    )

    return {
        "staging_filename": staging_filename,
        "staging_file": str(staged_dest),
        "vault_file": vault_file,
        "sidecar_file": sidecar_file,
    }


def _auto_add_manual_references(
    manual_fields: dict,
    type_name: str,
    config,
    logger=None,
):
    """
    For manual name-field values that have reference_lookup,
    auto-add them to fieldname_ref.json.
    """
    types = config.type_definitions.get("types", {})
    typedef = types.get(type_name, {})
    field_defs = typedef.get("extraction_fields", {})
    doc_type_code = typedef.get("code", "000")

    reference_entries = config.load_reference(REF_PATH)
    ref_changed = False

    for field_name, value in manual_fields.items():
        if not value:
            continue
        field_cfg = field_defs.get(field_name, {})
        lookup = field_cfg.get("reference_lookup")
        if not lookup:
            continue

        role = lookup["role"]

        # Check if entity already exists
        from src.fuzzy_matcher import fuzzy_match
        matched_key, ratio = fuzzy_match(
            value, reference_entries, threshold=0.80
        )

        if matched_key:
            _update_entity_metadata(
                reference_entries[matched_key], role, doc_type_code
            )
            ref_changed = True
        else:
            entity_key, entity_dict = create_entity(
                value, role, doc_type_code, reference_entries
            )
            reference_entries[entity_key] = entity_dict
            ref_changed = True
            if logger:
                logger.log_reference_entry(field_name, value, entity_dict)

    if ref_changed:
        config.save_reference(REF_PATH, reference_entries)
