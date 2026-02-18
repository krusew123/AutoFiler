# src/detectors.py
"""Format detection functions for file classification."""

import os
import pathlib
import magic
from datetime import datetime


def detect_extension(file_path: str) -> str:
    """Return the lowercase file extension including the dot, e.g. '.pdf'."""
    return pathlib.Path(file_path).suffix.lower()


def detect_mime(file_path: str) -> str:
    """Return the MIME type string detected from file content bytes."""
    return magic.from_file(file_path, mime=True)


def match_extension(extension: str, type_definitions: dict) -> list[str]:
    """Return a list of type names whose container_formats list contains the given extension."""
    matches = []
    for type_name, typedef in type_definitions.get("types", {}).items():
        if extension in typedef.get("container_formats", []):
            matches.append(type_name)
    return matches


def match_mime(mime_type: str, type_definitions: dict) -> list[str]:
    """Return a list of type names whose mime_types list contains the given MIME type."""
    matches = []
    for type_name, typedef in type_definitions.get("types", {}).items():
        if mime_type in typedef.get("mime_types", []):
            matches.append(type_name)
    return matches


def get_file_metadata(file_path: str) -> dict:
    """Return a dict of file metadata: size, created, modified."""
    stat = os.stat(file_path)
    return {
        "file_size": stat.st_size,
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }
