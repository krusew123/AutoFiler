# src/fuzzy_matcher.py
"""Reusable fuzzy string matching using difflib.SequenceMatcher."""

from difflib import SequenceMatcher


def _normalize(text: str) -> str:
    """Lowercase and strip whitespace for comparison."""
    return text.lower().strip()


def fuzzy_match(
    query: str,
    reference_entries: dict,
    threshold: float = 0.80,
) -> tuple[str | None, float]:
    """
    Match a query string against reference entries using fuzzy matching.

    Each entry in reference_entries is expected to have a "name" field
    and optionally an "aliases" list.  The query is compared against
    the canonical name and every alias.

    Returns:
        (matched_key, best_ratio) — matched_key is the dict key of the
        best match, or None if no match meets the threshold.
    """
    query_norm = _normalize(query)
    if not query_norm:
        return None, 0.0

    best_key = None
    best_ratio = 0.0

    for key, entry in reference_entries.items():
        candidates = [entry.get("name", "")]
        candidates.extend(entry.get("aliases", []))

        for candidate in candidates:
            candidate_norm = _normalize(candidate)
            if not candidate_norm:
                continue

            # Exact match short-circuit
            if query_norm == candidate_norm:
                return key, 1.0

            ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key = key

    if best_ratio >= threshold:
        return best_key, best_ratio

    return None, best_ratio
