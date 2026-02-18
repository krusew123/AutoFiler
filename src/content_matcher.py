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
