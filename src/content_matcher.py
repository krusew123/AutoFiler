# src/content_matcher.py
"""Match extracted text against document type keyword and pattern definitions."""

import re


def match_keywords(text: str, type_definitions: dict) -> dict:
    """
    Check extracted text for keywords defined in each type.

    Returns:
        {type_name: count_of_matched_keywords} for types
        that meet or exceed their keyword_threshold.
    """
    text_lower = text.lower()
    matches = {}
    for type_name, typedef in type_definitions.get("types", {}).items():
        keywords = typedef.get("content_keywords", [])
        threshold = typedef.get("keyword_threshold", 1)
        count = sum(1 for kw in keywords if kw.lower() in text_lower)
        if count >= threshold:
            matches[type_name] = count
    return matches


def _extract_address_lines(text: str, match: re.Match) -> str:
    """Grab continuation lines after an initial address match.

    Starting from the matched line, collects subsequent lines that look like
    address continuations (not blank, not a new label like ``Word: value``).
    Stops after 4 continuation lines or when a stop condition is hit.
    Returns the full address joined with ", ".
    """
    first_value = match.group(1).strip()
    lines = text.splitlines()
    match_start = match.start()

    # Find which line the match is on
    pos = 0
    start_idx = 0
    for i, line in enumerate(lines):
        end = pos + len(line)
        if pos <= match_start <= end:
            start_idx = i
            break
        pos = end + 1  # +1 for the newline character

    # Label pattern: "Word(s): text" — signals a new field, not continuation
    label_re = re.compile(r"^[A-Za-z][A-Za-z ]{0,30}:\s")

    parts = []
    if first_value:
        parts.append(first_value)

    # Scan continuation lines (up to 4 after the matched line)
    for line in lines[start_idx + 1 : start_idx + 5]:
        stripped = line.strip()
        if not stripped:
            break
        if label_re.match(stripped):
            break
        parts.append(stripped)

    return ", ".join(parts)


def extract_fields(text: str, type_name: str, type_definitions: dict) -> tuple[dict, list]:
    """
    Extract named fields from text using regex patterns defined in a type's
    extraction_fields config.

    Each field has an ordered list of regex patterns (first match wins)
    and a ``required`` flag.

    Returns:
        (extracted_fields_dict, missing_required_fields_list)
    """
    types = type_definitions.get("types", {})
    typedef = types.get(type_name, {})
    field_defs = typedef.get("extraction_fields", {})

    if not field_defs:
        return {}, []

    extracted = {}
    missing = []

    for field_name, field_cfg in field_defs.items():
        patterns = field_cfg.get("patterns", [])
        required = field_cfg.get("required", False)
        field_type = field_cfg.get("field_type", "text")
        value = None

        for pattern in patterns:
            try:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    if field_type == "address":
                        value = _extract_address_lines(text, match)
                    else:
                        value = match.group(1).strip()
                    break
            except (re.error, IndexError):
                continue

        if value:
            extracted[field_name] = value
        elif required:
            missing.append(field_name)

    return extracted, missing


def match_patterns(text: str, type_definitions: dict) -> dict:
    """
    Check extracted text against regex patterns defined in each type.

    Returns:
        {type_name: count_of_matched_patterns}.
    """
    matches = {}
    for type_name, typedef in type_definitions.get("types", {}).items():
        patterns = typedef.get("content_patterns", [])
        count = 0
        for pattern in patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    count += 1
            except re.error:
                continue
        if count > 0:
            matches[type_name] = count
    return matches
