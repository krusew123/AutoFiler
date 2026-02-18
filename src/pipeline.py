# src/pipeline.py
"""Main processing pipeline: classify -> score -> route -> name -> file."""

from src.classifier import classify_file
from src.scorer import score_candidates, select_best_candidate
from src.router import route_file
from src.name_generator import generate_name
from src.filer import file_to_destination
from src.guards import check_file


def process_file(file_path: str, config, logger=None) -> dict:
    """
    Run the full pipeline on a single file.

    Returns a result dict with classification, scoring, routing,
    and filing details.
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
            "filing": None,
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

        # 4. Name & File (only if auto-filed)
        filing = None
        if routing["decision"] == "auto_file":
            generated_name = generate_name(
                file_path, best_type, config.naming_conventions
            )
            filing = file_to_destination(
                file_path=file_path,
                generated_name=generated_name,
                type_name=best_type,
                destination_root=settings["destination_root"],
                folder_mappings=config.folder_mappings,
            )

        result = {
            "classification": classification,
            "scored_candidates": scored,
            "best_type": best_type,
            "best_score": best_score,
            "routing": routing,
            "filing": filing,
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
