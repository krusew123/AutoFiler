# src/router.py
"""Route files to auto-file or review based on confidence threshold."""

import shutil
import pathlib


def route_file(
    file_path: str,
    best_type: str | None,
    score: float | None,
    threshold: float,
    review_path: str,
) -> dict:
    """
    Decide whether to auto-file or route to review.

    Returns:
        {
            "decision": "auto_file" | "review",
            "reason": str,
            "type_name": str | None,
            "score": float | None
        }
    """
    # No candidate found at all
    if best_type is None or score is None:
        move_to_review(file_path, review_path)
        return {
            "decision": "review",
            "reason": "no_candidate",
            "type_name": None,
            "score": None,
        }

    # Score below threshold
    if score < threshold:
        move_to_review(file_path, review_path)
        return {
            "decision": "review",
            "reason": f"score_{score}_below_threshold_{threshold}",
            "type_name": best_type,
            "score": score,
        }

    # Score meets or exceeds threshold -> auto-file
    return {
        "decision": "auto_file",
        "reason": f"score_{score}_meets_threshold_{threshold}",
        "type_name": best_type,
        "score": score,
    }


def move_to_review(file_path: str, review_path: str):
    """Move a file to the review folder, preserving its original name."""
    dest = pathlib.Path(review_path)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / pathlib.Path(file_path).name

    # Handle name collision in review folder
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while target.exists():
            target = dest / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(file_path, str(target))
