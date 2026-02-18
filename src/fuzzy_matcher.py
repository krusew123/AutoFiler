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


def fuzzy_match_with_support(
    query: str,
    reference_entries: dict,
    threshold: float = 0.90,
    supporting_values: dict | None = None,
) -> tuple[str | None, float]:
    """
    Layered fuzzy matching with supporting field confirmation.

    Matching logic:
    1. Exact match on canonical name or alias -> return immediately
    2. Fuzzy ratio >= threshold + any supporting field confirms -> accept
    3. Fuzzy ratio >= threshold + no supporting values provided -> accept
    4. Otherwise -> no match

    Args:
        query: The value to match.
        reference_entries: Dict of {key: {name, aliases, ...}} entries.
        threshold: Minimum fuzzy ratio required (default 0.90).
        supporting_values: Dict of {field_name: extracted_value} to
            cross-check against reference entry fields.

    Returns:
        (matched_key, best_ratio) or (None, best_ratio).
    """
    query_norm = _normalize(query)
    if not query_norm:
        return None, 0.0

    if supporting_values is None:
        supporting_values = {}

    best_key = None
    best_ratio = 0.0

    for key, entry in reference_entries.items():
        candidates = [entry.get("name", "")]
        candidates.extend(entry.get("aliases", []))

        for candidate in candidates:
            candidate_norm = _normalize(candidate)
            if not candidate_norm:
                continue

            # 1. Exact match short-circuit
            if query_norm == candidate_norm:
                return key, 1.0

            ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key = key

    if best_ratio < threshold or best_key is None:
        return None, best_ratio

    # We have a fuzzy match above threshold — check supporting fields
    if not supporting_values:
        # 3. No supporting values provided -> accept
        return best_key, best_ratio

    # 2. Check if any supporting field confirms
    matched_entry = reference_entries[best_key]
    for field_name, extracted_val in supporting_values.items():
        if not extracted_val:
            continue
        ref_val = matched_entry.get(field_name, "")
        if not ref_val:
            continue
        if _normalize(extracted_val) == _normalize(ref_val):
            return best_key, best_ratio

    # 4. Supporting values provided but none confirmed -> no match
    return None, best_ratio
