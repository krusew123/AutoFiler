# src/content_extractor.py
"""Extract text content from files using OCR and document parsing."""

import pathlib
import pytesseract
from pdf2image import convert_from_path
from PIL import Image


def extract_text(file_path: str, settings: dict) -> str:
    """Dispatch to the appropriate text extractor based on file extension."""
    ext = pathlib.Path(file_path).suffix.lower()
    tesseract_path = settings.get("tesseract_path", "")
    poppler_path = settings.get("poppler_path", "")

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    if ext == ".pdf":
        return extract_pdf_text(file_path, poppler_path)
    elif ext == ".docx":
        return extract_docx_text(file_path)
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
        return extract_image_text(file_path)
    else:
        return ""


def extract_pdf_text(file_path: str, poppler_path: str) -> str:
    """Convert PDF pages to images at 300 DPI, then OCR each page."""
    try:
        kwargs = {"dpi": 300}
        if poppler_path:
            kwargs["poppler_path"] = poppler_path
        images = convert_from_path(file_path, **kwargs)
        text_parts = []
        for page_img in images:
            text_parts.append(pytesseract.image_to_string(page_img))
        return "\n".join(text_parts)
    except Exception:
        return ""


def extract_docx_text(file_path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return ""


def extract_image_text(file_path: str) -> str:
    """OCR an image file directly using pytesseract."""
    try:
        img = Image.open(file_path)
        return pytesseract.image_to_string(img)
    except Exception:
        return ""
