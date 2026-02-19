# src/gap_analyzer.py
"""Diagnose classification and extraction misses — pure business logic."""

import re
from collections import Counter

# Common English stopwords to filter from keyword suggestions
_STOPWORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her",
    "was", "one", "our", "out", "has", "had", "his", "how", "its", "may",
    "new", "now", "old", "see", "way", "who", "did", "get", "let", "say",
    "she", "too", "use", "from", "that", "this", "with", "have", "been",
    "will", "each", "make", "like", "than", "them", "then", "they", "what",
    "when", "your", "into", "also", "more", "some", "such", "just", "only",
    "over", "very", "page", "date", "name", "total", "number", "amount",
    "please", "thank", "note", "item", "none", "null", "true", "false",
})

# Regex patterns for structured formats commonly found in documents
_STRUCTURE_PATTERNS = [
    # Dates
    (r"\d{1,2}/\d{1,2}/\d{2,4}", r"\d{1,2}/\d{1,2}/\d{2,4}"),
    (r"\d{1,2}-\d{1,2}-\d{2,4}", r"\d{1,2}-\d{1,2}-\d{2,4}"),
    (r"\d{4}-\d{2}-\d{2}", r"\d{4}-\d{2}-\d{2}"),
    (r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}",
     r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}"),
    # Currency
    (r"\$[\d,]+\.\d{2}", r"\$[\d,]+\.\d{2}"),
    # Reference numbers (e.g., INV-12345, #12345)
    (r"[A-Z]{2,5}[-#]\d{3,}", r"[A-Z]{2,5}[-#]\d{3,}"),
    (r"#\d{4,}", r"#\d{4,}"),
    # Phone numbers
    (r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),
    # Email addresses
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
]


def analyze_classification_gap(
    extracted_text: str,
    type_name: str,
    type_definitions: dict,
    scored_candidates: dict,
) -> dict:
    """
    Compare file content against the assigned type's classification signals.

    Returns dict with matched/missed/suggested keywords and patterns.
    """
    types = type_definitions.get("types", {})
    typedef = types.get(type_name, {})
    text_lower = extracted_text.lower()

    # --- Keywords ---
    type_keywords = typedef.get("content_keywords", [])
    matched_keywords = [kw for kw in type_keywords if kw.lower() in text_lower]
    missed_keywords = [kw for kw in type_keywords if kw.lower() not in text_lower]

    # Suggested keywords: distinctive terms found in text but not in config
    suggested_keywords = _suggest_keywords(extracted_text, type_keywords, types)

    # --- Patterns ---
    type_patterns = typedef.get("content_patterns", [])
    matched_patterns = []
    missed_patterns = []
    for pattern in type_patterns:
        try:
            if re.search(pattern, extracted_text, re.IGNORECASE):
                matched_patterns.append(pattern)
            else:
                missed_patterns.append(pattern)
        except re.error:
            missed_patterns.append(pattern)

    suggested_patterns = _suggest_patterns(extracted_text, type_patterns)

    return {
        "matched_keywords": matched_keywords,
        "missed_keywords": missed_keywords,
        "suggested_keywords": suggested_keywords,
        "matched_patterns": matched_patterns,
        "missed_patterns": missed_patterns,
        "suggested_patterns": suggested_patterns,
    }


def analyze_document_for_new_type(extracted_text: str) -> dict:
    """
    Analyze document text to suggest keywords, patterns, and fields
    for creating a new type definition.

    Returns:
        {
            "suggested_keywords": [...],
            "suggested_patterns": [...],
            "detected_fields": [
                {
                    "label": str,
                    "value": str,
                    "field_name": str,
                    "field_type": str,  # date, amount, reference, name, text
                    "line_number": int,
                    "suggested_pattern": str,
                }
            ],
        }
    """
    # Keywords — reuse helper with empty existing lists
    suggested_keywords = _suggest_keywords(extracted_text, [], {})

    # Patterns — reuse helper with empty existing list
    suggested_patterns = _suggest_patterns(extracted_text, [])

    # Fields — detect label:value structures in the text
    detected_fields = _detect_field_candidates(extracted_text)

    return {
        "suggested_keywords": suggested_keywords,
        "suggested_patterns": suggested_patterns,
        "detected_fields": detected_fields,
    }


def analyze_extraction_gap(
    extracted_text: str,
    type_name: str,
    type_definitions: dict,
    extracted_fields: dict,
    missing_fields: list,
) -> dict:
    """
    For each missing field, analyze why extraction failed and find candidate values.

    Returns dict keyed by field_name with existing patterns, pattern results,
    and candidate values.
    """
    types = type_definitions.get("types", {})
    typedef = types.get(type_name, {})
    field_defs = typedef.get("extraction_fields", {})

    result = {}
    for field_name in missing_fields:
        field_cfg = field_defs.get(field_name, {})
        patterns = field_cfg.get("patterns", [])

        # Test each existing pattern against the text
        pattern_results = []
        for pattern in patterns:
            try:
                match = re.search(pattern, extracted_text, re.IGNORECASE | re.MULTILINE)
                pattern_results.append({
                    "pattern": pattern,
                    "matched": bool(match),
                    "match_text": match.group(1).strip() if match else None,
                })
            except (re.error, IndexError):
                pattern_results.append({
                    "pattern": pattern,
                    "matched": False,
                    "match_text": None,
                })

        # Find candidate values in the text
        candidate_values = _find_candidate_values(
            extracted_text, field_name, patterns
        )

        result[field_name] = {
            "existing_patterns": patterns,
            "pattern_results": pattern_results,
            "candidate_values": candidate_values,
        }

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _suggest_keywords(
    text: str,
    existing_keywords: list[str],
    all_types: dict,
) -> list[str]:
    """
    Extract candidate keywords from text that aren't already configured.

    Algorithm:
    1. Split text into lines, identify label lines (contain ':' or all-caps phrases)
    2. Extract label portions and capitalized multi-word phrases
    3. Remove stopwords and phrases already in the type's keyword list
    4. Cross-reference against all types' keywords to find distinctive terms
    5. Return top ~15 candidates ranked by frequency
    """
    existing_lower = {kw.lower() for kw in existing_keywords}

    # Collect all keywords from all types for distinctiveness filtering
    all_keywords_lower = set()
    for typedef in all_types.values():
        for kw in typedef.get("content_keywords", []):
            all_keywords_lower.add(kw.lower())

    candidates = Counter()
    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Extract label portions from lines containing ':'
        if ":" in stripped:
            label = stripped.split(":")[0].strip()
            if 2 <= len(label) <= 50 and not label.isdigit():
                candidates[label] += 1

        # Extract capitalized multi-word phrases (2-3 words)
        cap_phrases = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", stripped)
        for phrase in cap_phrases:
            candidates[phrase] += 1

        # Extract ALL-CAPS phrases (2+ words)
        upper_phrases = re.findall(r"\b([A-Z]{2,}(?:\s+[A-Z]{2,}){1,2})\b", stripped)
        for phrase in upper_phrases:
            candidates[phrase] += 1

    # Filter
    filtered = {}
    for phrase, count in candidates.items():
        phrase_lower = phrase.lower()
        # Skip if already in this type's keywords
        if phrase_lower in existing_lower:
            continue
        # Skip stopwords (single words)
        words = phrase_lower.split()
        if len(words) == 1 and phrase_lower in _STOPWORDS:
            continue
        # Skip very short or very long
        if len(phrase) < 3 or len(phrase) > 50:
            continue
        filtered[phrase] = count

    # Sort by frequency, return top 25 (UI shows 15, keeps rest as backfill)
    ranked = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
    return [phrase for phrase, _ in ranked[:25]]


def _suggest_patterns(text: str, existing_patterns: list[str]) -> list[str]:
    """
    Scan text for structured formats and suggest regex patterns
    not already covered by existing content_patterns.
    """
    suggestions = []

    for search_re, suggest_re in _STRUCTURE_PATTERNS:
        try:
            if re.search(search_re, text, re.IGNORECASE):
                # Check if already covered by existing patterns
                already_covered = False
                for existing in existing_patterns:
                    try:
                        # If existing pattern matches the same structures, skip
                        if re.search(existing, re.search(search_re, text).group(), re.IGNORECASE):
                            already_covered = True
                            break
                    except (re.error, AttributeError):
                        continue
                if not already_covered and suggest_re not in suggestions:
                    suggestions.append(suggest_re)
        except re.error:
            continue

    return suggestions


def _find_candidate_values(
    text: str,
    field_name: str,
    existing_patterns: list[str],
) -> list[dict]:
    """
    Find candidate values in text for a missing field, using field-name-aware heuristics.
    """
    field_lower = field_name.lower()
    candidates = []
    lines = text.splitlines()

    # Determine value type from field name
    if "date" in field_lower:
        candidates = _find_date_candidates(text, lines, existing_patterns)
    elif any(w in field_lower for w in ("number", "num", "id", "ref", "invoice", "po", "order")):
        candidates = _find_reference_candidates(text, lines, field_name, existing_patterns)
    elif any(w in field_lower for w in ("amount", "total", "balance", "price", "cost")):
        candidates = _find_currency_candidates(text, lines, field_name, existing_patterns)
    elif any(w in field_lower for w in ("name", "vendor", "customer", "company", "client")):
        candidates = _find_name_candidates(text, lines, field_name, existing_patterns)
    else:
        # Generic: look for labeled values near the field name
        candidates = _find_labeled_candidates(text, lines, field_name, existing_patterns)

    return candidates[:10]  # Cap at 10 candidates


def _find_date_candidates(text, lines, existing_patterns):
    """Find date-like values in text."""
    candidates = []
    date_patterns = [
        r"(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(\d{1,2}-\d{1,2}-\d{2,4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
    ]
    for i, line in enumerate(lines, 1):
        for dp in date_patterns:
            for m in re.finditer(dp, line, re.IGNORECASE):
                # Build a context-aware regex suggestion
                prefix = line[:m.start()].strip()
                if prefix:
                    # Use the label before the date as context
                    safe_prefix = re.escape(prefix[-30:])
                    suggested = f"{safe_prefix}\\s*({dp.strip('()')})"
                else:
                    suggested = dp
                candidates.append({
                    "text_snippet": m.group(1),
                    "line_number": i,
                    "suggested_pattern": suggested,
                })
    return candidates


def _find_reference_candidates(text, lines, field_name, existing_patterns):
    """Find reference number-like values."""
    candidates = []
    ref_patterns = [
        r"([A-Z]{0,5}[-#]?\d{3,})",
        r"(\d{4,})",
    ]
    # Also look for labeled references
    field_words = re.sub(r"[_-]", " ", field_name).strip()
    label_re = re.compile(
        rf"(?:{re.escape(field_words)}|{field_words.replace(' ', r'\\s+')})"
        r"[:\s#]*([A-Za-z0-9][-A-Za-z0-9]{2,})",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines, 1):
        m = label_re.search(line)
        if m:
            safe_label = re.escape(line[:m.start(1)].strip()[-40:])
            candidates.append({
                "text_snippet": m.group(1),
                "line_number": i,
                "suggested_pattern": f"{safe_label}\\s*([A-Za-z0-9][-A-Za-z0-9]+)",
            })
        else:
            for rp in ref_patterns:
                for m2 in re.finditer(rp, line):
                    prefix = line[:m2.start()].strip()
                    if prefix:
                        safe_prefix = re.escape(prefix[-30:])
                        candidates.append({
                            "text_snippet": m2.group(1),
                            "line_number": i,
                            "suggested_pattern": f"{safe_prefix}\\s*({rp.strip('()')})",
                        })
    return candidates


def _find_currency_candidates(text, lines, field_name, existing_patterns):
    """Find currency/amount values."""
    candidates = []
    currency_re = re.compile(r"\$?([\d,]+\.\d{2})")

    for i, line in enumerate(lines, 1):
        for m in currency_re.finditer(line):
            prefix = line[:m.start()].strip()
            if prefix:
                safe_prefix = re.escape(prefix[-30:])
                candidates.append({
                    "text_snippet": m.group(0),
                    "line_number": i,
                    "suggested_pattern": f"{safe_prefix}\\s*\\$?([\\d,]+\\.\\d{{2}})",
                })
            else:
                candidates.append({
                    "text_snippet": m.group(0),
                    "line_number": i,
                    "suggested_pattern": r"\$?([\d,]+\.\d{2})",
                })
    return candidates


def _find_name_candidates(text, lines, field_name, existing_patterns):
    """Find proper noun / entity name candidates."""
    candidates = []
    # Look for lines with label:value pattern where label relates to field
    field_words = re.sub(r"[_-]", " ", field_name).strip()
    label_re = re.compile(
        rf"(?:{re.escape(field_words)}|{field_words.replace(' ', r'\\s+')})"
        r"[:\s]+(.+)",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines, 1):
        m = label_re.search(line)
        if m:
            value = m.group(1).strip()
            if value and len(value) < 100:
                safe_label = re.escape(line[:m.start(1)].strip())
                candidates.append({
                    "text_snippet": value,
                    "line_number": i,
                    "suggested_pattern": f"{safe_label}\\s*(.+?)\\s*$",
                })
    return candidates


def _find_labeled_candidates(text, lines, field_name, existing_patterns):
    """Generic: look for labeled values near field name keywords."""
    candidates = []
    field_words = re.sub(r"[_-]", " ", field_name).strip()
    label_re = re.compile(
        rf"(?:{re.escape(field_words)}|{field_words.replace(' ', r'\\s+')})"
        r"[:\s]+(.+)",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines, 1):
        m = label_re.search(line)
        if m:
            value = m.group(1).strip()
            if value and len(value) < 100:
                safe_label = re.escape(line[:m.start(1)].strip())
                candidates.append({
                    "text_snippet": value,
                    "line_number": i,
                    "suggested_pattern": f"{safe_label}\\s*(.+?)\\s*$",
                })
    return candidates


def _detect_field_candidates(text: str) -> list[dict]:
    """
    Detect label:value pairs in text that could become extraction fields.

    Scans for lines like "Invoice Date: 01/31/2026" and returns structured
    candidates with suggested field names, types, and extraction patterns.
    """
    candidates = []
    seen_field_names = set()
    lines = text.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue

        parts = stripped.split(":", 1)
        label = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ""

        if not label or not value:
            continue
        if len(label) < 2 or len(label) > 50:
            continue
        if label.isdigit():
            continue
        # Skip lines that look like timestamps or URLs
        if re.match(r"^https?$", label, re.IGNORECASE):
            continue

        # Determine likely field type from value content
        field_type = "text"
        if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", value):
            field_type = "date"
        elif re.search(r"\$?[\d,]+\.\d{2}", value):
            field_type = "amount"
        elif re.match(r"^[A-Z0-9][-A-Z0-9]{2,}$", value):
            field_type = "reference"
        elif re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", value):
            field_type = "name"

        # Generate field name from label
        field_name = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if not field_name or field_name in seen_field_names:
            continue
        seen_field_names.add(field_name)

        # Generate extraction pattern using raw string templates
        safe_label = re.escape(label)
        if field_type == "date":
            pattern = safe_label + r"[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
        elif field_type == "amount":
            pattern = safe_label + r"[:\s]*\$?([\d,]+\.\d{2})"
        elif field_type == "reference":
            pattern = safe_label + r"[:\s]*([A-Za-z0-9][\-A-Za-z0-9]+)"
        else:
            pattern = safe_label + r"[:\s]*(.+?)\s*$"

        candidates.append({
            "label": label,
            "value": value,
            "field_name": field_name,
            "field_type": field_type,
            "line_number": i,
            "suggested_pattern": pattern,
        })

    return candidates
