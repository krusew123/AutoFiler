# src/pipeline.py
"""Stage 1 pipeline: classify -> score -> route -> extract -> stage."""

import pathlib
import shutil

from src.classifier import classify_file
from src.scorer import score_candidates, select_best_candidate
from src.router import route_file, move_to_review
from src.content_matcher import extract_fields
from src.field_resolver import resolve_fields
from src.guards import check_file
from src.sidecar import generate_sidecar, hash_file
from src.staging_namer import generate_staging_name
from src.vault import archive_to_vault


def process_file(file_path: str, config, logger=None) -> dict:
    """
    Run the Stage 1 pipeline on a single file.

    Returns a result dict with classification, scoring, routing,
    staging, and vault details.
    """
    # 0. Guard check
    guard_reason = check_file(file_path)
    if guard_reason:
        if logger:
            logger.log_error(file_path, f"guard_failed:{guard_reason}")
        return {
            "classification": None,
            "scored_candidates": None,
            "best_type": None,
            "best_score": None,
            "routing": {"decision": "rejected", "reason": guard_reason},
            "staging": None,
            "vault": None,
        }

    settings = config.settings
    rules = config.classification_rules

    try:
        # 1. Classify
        classification = classify_file(file_path, config)

        # 2. Score
        scored = score_candidates(classification, rules)
        best_type, best_data = select_best_candidate(
            scored, rules.get("min_signals_required", 2)
        )
        best_score = best_data["score"] if best_data else None

        # 3. Route
        routing = route_file(
            file_path=file_path,
            best_type=best_type,
            score=best_score,
            threshold=settings["confidence_threshold"],
            review_path=settings["review_path"],
        )

        # 4. Extract fields & stage (only if auto-filed)
        staging = None
        vault = None
        extracted_fields = None
        if routing["decision"] == "auto_file":
            extracted_text = classification.get("extracted_text", "")
            extracted_fields, missing = extract_fields(
                extracted_text, best_type, config.type_definitions
            )

            # Resolve name fields against entity reference
            extracted_fields, missing, resolution_info = resolve_fields(
                extracted_fields, missing, extracted_text,
                best_type, config, logger,
            )

            if missing:
                # Required fields missing — reroute to review
                move_to_review(file_path, settings["review_path"])
                routing = {
                    "decision": "review",
                    "reason": f"missing_extraction_fields:{','.join(missing)}",
                    "type_name": best_type,
                    "score": best_score,
                }
            else:
                # Hash source file
                file_hash = hash_file(file_path)

                # Get type config for staging
                type_cfg = config.type_definitions.get("types", {}).get(best_type, {})
                doc_type_code = type_cfg.get("code", "000")

                # Archive original to vault
                vault_file = archive_to_vault(
                    file_path=file_path,
                    doc_type_code=doc_type_code,
                    vault_path=settings["vault_path"],
                )
                vault = {"vault_file": vault_file, "doc_type_code": doc_type_code}

                # Generate staging name + modified fields
                staging_stem, modified_fields = generate_staging_name(
                    type_name=best_type,
                    type_config=type_cfg,
                    extracted_fields=extracted_fields,
                    file_path=file_path,
                )

                # Move file from intake to staging
                staging_path = pathlib.Path(settings["staging_path"])
                staging_path.mkdir(parents=True, exist_ok=True)
                ext = pathlib.Path(file_path).suffix
                staging_filename = f"{staging_stem}{ext}"
                staged_dest = staging_path / staging_filename
                shutil.move(file_path, staged_dest)

                staging = {
                    "staging_filename": staging_filename,
                    "staging_file": str(staged_dest),
                    "modified_fields": modified_fields,
                }

                # Generate sidecar alongside staged file
                generate_sidecar(
                    source_file_path=file_path,
                    doc_type=best_type,
                    doc_type_code=doc_type_code,
                    confidence_score=best_score,
                    extracted_fields=extracted_fields,
                    modified_fields=modified_fields,
                    staging_filename=staging_filename,
                    vault_path=vault_file,
                    extracted_text=extracted_text,
                    sidecar_path=settings["staging_path"],
                    file_hash=file_hash,
                    resolution_info=resolution_info,
                )

        result = {
            "classification": classification,
            "scored_candidates": scored,
            "best_type": best_type,
            "best_score": best_score,
            "routing": routing,
            "staging": staging,
            "vault": vault,
            "extracted_fields": extracted_fields,
        }

        # 5. Log the outcome
        if logger:
            if routing["decision"] == "auto_file":
                logger.log_auto_file(result)
            else:
                logger.log_review_route(
                    file_path, routing["reason"], best_score
                )

        return result

    except Exception as e:
        if logger:
            logger.log_error(file_path, str(e))
        raise
