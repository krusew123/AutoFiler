# src/classifier.py
"""Orchestrate format detection, content extraction, and content classification."""

from src.detectors import (
    detect_extension,
    detect_mime,
    match_extension,
    match_mime,
    get_file_metadata,
)
from src.content_extractor import extract_text
from src.content_matcher import match_keywords, match_patterns


def classify_file(file_path: str, config) -> dict:
    """
    Run all detection and content signals against a file.

    Pipeline: Format Detection -> Text Extraction -> Content Classification

    Returns:
        {
            "file_path": str,
            "extension": str,
            "mime_type": str,
            "metadata": dict,
            "extracted_text": str,
            "signals": {
                "format_matches": [...],
                "keyword_matches": {type: count, ...},
                "pattern_matches": {type: count, ...}
            },
            "candidates": {
                "type_name": {
                    "matched_signals": ["format_match", ...]
                }
            }
        }
    """
    types = config.type_definitions
    settings = config.settings

    # Stage 1: Format Detection
    extension = detect_extension(file_path)
    mime_type = detect_mime(file_path)
    metadata = get_file_metadata(file_path)

    ext_matches = match_extension(extension, types)
    mime_matches = match_mime(mime_type, types)
    format_matches = list(set(ext_matches + mime_matches))

    # Stage 2: Content Extraction (OCR)
    extracted_text = extract_text(file_path, settings)

    # Stage 3: Content Classification
    keyword_matches = match_keywords(extracted_text, types)
    pattern_matches = match_patterns(extracted_text, types)

    # Build candidate map
    all_candidates = (
        set(format_matches)
        | set(keyword_matches.keys())
        | set(pattern_matches.keys())
    )
    candidates = {}
    for type_name in all_candidates:
        matched = []
        if type_name in format_matches:
            matched.append("format_match")
        if type_name in keyword_matches:
            matched.append("keyword_match")
        if type_name in pattern_matches:
            matched.append("pattern_match")
        # Reference match: type has folder mapping + naming convention
        fm = config.folder_mappings
        nc = config.naming_conventions.get("patterns", {})
        if type_name in fm and type_name in nc:
            matched.append("reference_match")
        candidates[type_name] = {"matched_signals": matched}

    return {
        "file_path": file_path,
        "extension": extension,
        "mime_type": mime_type,
        "metadata": metadata,
        "extracted_text": extracted_text,
        "signals": {
            "format_matches": format_matches,
            "keyword_matches": keyword_matches,
            "pattern_matches": pattern_matches,
        },
        "candidates": candidates,
    }
