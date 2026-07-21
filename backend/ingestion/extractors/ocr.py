"""
OCR Extractor
--------------
Single responsibility: run OCR against a file path that document/inspector.py
has already confirmed is scanned and already decrypted. Does not make the
digital-vs-scanned decision and does not handle passwords itself.
"""

import re


def extract_scanned_text(file_path: str, ocr_engine) -> str:
    if ocr_engine is None:
        raise ValueError("No OCR engine configured — cannot process scanned document.")

    text = ocr_engine.extract_text(file_path)

    # OCR output needs whitespace cleanup but skips the aggressive character
    # stripping used for digital text, since OCR already produces plain text.
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()