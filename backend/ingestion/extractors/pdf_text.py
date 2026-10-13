"""
Digital PDF Text Extractor
----------------------------
Single responsibility: extract raw text from a PDF that has already been
confirmed digital (and already decrypted, if it was encrypted) by
document/inspector.py. Does not handle passwords or scanned documents.
"""

import pdfplumber
import fitz  # PyMuPDF


def extract_txt_pdfplumber(file_path: str) -> str:
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def extract_txt_pymupdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


def extract_digital_text(file_path: str) -> str:
    """Tries pdfplumber first (better for tabular layouts), falls back to PyMuPDF."""
    text = ""
    try:
        text = extract_txt_pdfplumber(file_path)
    except Exception:
        pass

    if len(text.strip()) < 50:
        try:
            text = extract_txt_pymupdf(file_path)
        except Exception:
            pass

    return text