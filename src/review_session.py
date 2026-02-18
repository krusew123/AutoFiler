# src/review_session.py
"""Run an interactive review session through all pending files."""

from src.review_queue import ReviewQueue
from src.review_prompt import display_file_info, prompt_type_selection
from src.classifier import classify_file
from src.scorer import score_candidates
from src.content_matcher import extract_fields
from src.name_generator import generate_name
from src.filer import file_to_destination
from src.cross_referencer import cross_reference_fields
from src.sidecar import generate_sidecar, hash_file


def run_review_session(config, logger=None):
    """
    Scan the review folder, then present each pending file
    to the user for classification and filing.
    """
    settings = config.settings
    queue = ReviewQueue(settings["review_path"], settings["config_path"])

    pending = queue.scan()
    summary = queue.summary()
    print(f"\nReview queue: {summary['pending']} pending, "
          f"{summary['resolved']} resolved\n")

    if not pending:
        print("No files to review.")
        return

    for i, file_path in enumerate(pending, 1):
        print(f"\n--- File {i} of {len(pending)} ---")
        queue.mark_in_review(file_path)

        # Show what the system knows
        classification = classify_file(file_path, config)
        scored = score_candidates(classification, config.classification_rules)
        extracted_text = classification.get("extracted_text", "")
        display_file_info(file_path, scored if scored else None, extracted_text)

        # Get user decision
        action, type_name = prompt_type_selection(config.type_definitions)

        if action == "skip":
            queue.mark_in_review(file_path)  # reset to pending on next scan
            print("  Skipped.")
            if logger:
                logger.log_skip(file_path)
            continue

        if action == "new":
            # Delegate to type creation (Section 4.2)
            from src.type_creator import create_new_type
            type_name = create_new_type(config)
            if type_name is None:
                print("  Type creation cancelled. File remains in review.")
                continue
            if logger:
                logger.log_new_type(type_name, config.type_definitions["types"][type_name])

        # Extract fields (ignore missing — user is deciding during review)
        extracted_fields, _ = extract_fields(
            extracted_text, type_name, config.type_definitions
        )

        # Cross-reference fields (ignore unresolved — user is deciding)
        if extracted_fields:
            resolved, _ = cross_reference_fields(
                extracted_fields, extracted_text, type_name, config, logger
            )
            extracted_fields = resolved

        # Hash before moving
        file_hash = hash_file(file_path)

        # File it using the selected/created type
        generated_name = generate_name(
            file_path, type_name, config.naming_conventions,
            extracted_fields=extracted_fields,
        )
        result = file_to_destination(
            file_path=file_path,
            generated_name=generated_name,
            type_name=type_name,
            destination_root=settings["destination_root"],
            folder_mappings=config.folder_mappings,
            extracted_fields=extracted_fields,
        )

        # Generate sidecar
        sidecar_path = settings.get("sidecar_path")
        if sidecar_path:
            generate_sidecar(
                source_file_path=file_path,
                filing_result=result,
                doc_type=type_name,
                confidence_score=None,
                extracted_fields=extracted_fields,
                extracted_text=extracted_text,
                sidecar_path=sidecar_path,
                file_hash=file_hash,
            )

        queue.mark_resolved(file_path, type_name)
        print(f"  Filed as '{type_name}' -> {result['destination']}")

        if logger:
            logger.log_manual_file(
                file_path, type_name, result['destination'],
                new_type=(action == "new")
            )

    # Final summary
    final = queue.summary()
    print(f"\nSession complete. Pending: {final['pending']}, "
          f"Resolved: {final['resolved']}")
