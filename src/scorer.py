# src/scorer.py
"""Calculate confidence scores from classification signals."""


def score_candidates(classification_result: dict, classification_rules: dict) -> dict:
    """
    Score each candidate type based on which signals matched.

    Returns:
        {
            "type_name": {
                "score": float,
                "matched_signals": [...],
                "signal_breakdown": {"format_match": 0.10, ...}
            }
        }
    """
    weights = classification_rules.get("signal_weights", {})
    candidates = classification_result.get("candidates", {})
    scored = {}

    for type_name, data in candidates.items():
        breakdown = {}
        total = 0.0
        for signal in data["matched_signals"]:
            weight = weights.get(signal, 0.0)
            breakdown[signal] = weight
            total += weight
        scored[type_name] = {
            "score": round(total, 4),
            "matched_signals": data["matched_signals"],
            "signal_breakdown": breakdown,
        }

    return scored


def select_best_candidate(
    scored_candidates: dict, min_signals: int = 1
) -> tuple[str | None, dict | None]:
    """
    Return the highest-scoring candidate that meets the minimum signal count.

    Returns:
        (type_name, score_data) or (None, None) if no candidate qualifies.
    """
    best_name = None
    best_data = None

    for type_name, data in scored_candidates.items():
        if len(data["matched_signals"]) < min_signals:
            continue
        if best_data is None or data["score"] > best_data["score"]:
            best_name = type_name
            best_data = data

    return best_name, best_data
