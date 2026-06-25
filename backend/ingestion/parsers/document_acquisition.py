"""
PRISM Document Acquisition Layer
Accepts native PDFs, scanned PDFs, images, and mobile screenshots.
Automatically selects best extraction strategy.
"""

import io
import os
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import pdfplumber
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class AcquiredDocument:
    raw_text: str
    pages: list[str]
    extraction_method: str  # "native" | "ocr"
    page_count: int
    file_type: str  # "pdf" | "image"
    ocr_confidence: Optional[float] = None


class DocumentAcquisitionLayer:
    """
    Entry point for all document uploads.
    Determines extraction strategy automatically — no manual hints needed.
    """

    SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
    SUPPORTED_PDF_EXTENSIONS = {".pdf"}
    # Minimum ratio of extractable chars per page to be considered "native PDF"
    NATIVE_TEXT_THRESHOLD = 50

    def __init__(self, poppler_path: Optional[str] = None, tesseract_cmd: Optional[str] = None):
        self.poppler_path = poppler_path
        if tesseract_cmd:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def acquire(self, file_path: str) -> AcquiredDocument:
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in self.SUPPORTED_PDF_EXTENSIONS:
            return self._acquire_pdf(str(path))
        elif ext in self.SUPPORTED_IMAGE_EXTENSIONS:
            return self._acquire_image(str(path))
        else:
            raise ValueError(f"Unsupported file type: {ext}. Supported: PDF, PNG, JPG, BMP, TIFF, WEBP")

    def acquire_bytes(self, file_bytes: bytes, filename: str) -> AcquiredDocument:
        ext = Path(filename).suffix.lower()
        tmp_path = f"/tmp/prism_doc_{os.getpid()}{ext}"
        with open(tmp_path, "wb") as f:
            f.write(file_bytes)
        try:
            return self.acquire(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------
    # PDF pipeline
    # ------------------------------------------------------------------

    def _acquire_pdf(self, path: str) -> AcquiredDocument:
        native_pages = self._extract_native_text(path)
        total_chars = sum(len(p) for p in native_pages)
        avg_chars_per_page = total_chars / max(len(native_pages), 1)

        if avg_chars_per_page >= self.NATIVE_TEXT_THRESHOLD:
            logger.info("PDF has native text (avg %.0f chars/page). Using pdfplumber.", avg_chars_per_page)
            return AcquiredDocument(
                raw_text="\n\n".join(native_pages),
                pages=native_pages,
                extraction_method="native",
                page_count=len(native_pages),
                file_type="pdf",
            )
        else:
            logger.info(
                "PDF appears scanned (avg %.0f chars/page). Falling back to OCR.", avg_chars_per_page
            )
            return self._ocr_pdf(path)

    def _extract_native_text(self, path: str) -> list[str]:
        pages = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
        except Exception as e:
            logger.warning("pdfplumber failed (%s), trying PyMuPDF fallback", e)
            try:
                doc = fitz.open(path)
                for page in doc:
                    pages.append(page.get_text())
                doc.close()
            except Exception as e2:
                logger.error("PyMuPDF also failed: %s", e2)
                pages = [""]
        return pages if pages else [""]

    def _ocr_pdf(self, path: str) -> AcquiredDocument:
        from ocr.ocr_engine import OCREngine
        engine = OCREngine(poppler_path=self.poppler_path)
        pages, confidence = engine.ocr_pdf(path)
        return AcquiredDocument(
            raw_text="\n\n".join(pages),
            pages=pages,
            extraction_method="ocr",
            page_count=len(pages),
            file_type="pdf",
            ocr_confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Image pipeline
    # ------------------------------------------------------------------

    def _acquire_image(self, path: str) -> AcquiredDocument:
        from ocr.ocr_engine import OCREngine
        engine = OCREngine()
        text, confidence = engine.ocr_image(path)
        return AcquiredDocument(
            raw_text=text,
            pages=[text],
            extraction_method="ocr",
            page_count=1,
            file_type="image",
            ocr_confidence=confidence,
        )
