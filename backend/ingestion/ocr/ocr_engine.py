"""
PRISM OCR Engine
Tesseract-based OCR with image enhancement pipeline.
Only invoked when native text extraction fails.
"""

import logging
from typing import Optional

import cv2
import numpy as np
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


class OCREngine:
    """
    Wraps Tesseract pytesseract with image pre-processing.
    Applies enhancement → OCR → confidence check → re-enhance if needed.
    """

    # Tesseract config optimised for financial documents (digits + text)
    TESS_CONFIG = "--oem 3 --psm 6"
    TESS_LANG = "eng"
    MIN_CONFIDENCE = 60  # out of 100

    def __init__(self, poppler_path: Optional[str] = None):
        self.poppler_path = poppler_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ocr_pdf(self, path: str) -> tuple[list[str], float]:
        """Convert all pages of a PDF to text via OCR. Returns (pages, avg_confidence)."""
        from pdf2image import convert_from_path
        kwargs = {}
        if self.poppler_path:
            kwargs["poppler_path"] = self.poppler_path

        try:
            images = convert_from_path(path, dpi=300, **kwargs)
        except Exception as e:
            logger.error("pdf2image conversion failed: %s", e)
            return [""], 0.0

        pages = []
        confidences = []
        for i, img in enumerate(images):
            text, conf = self.ocr_image_pil(img)
            if conf < self.MIN_CONFIDENCE:
                logger.info("Page %d low confidence (%.1f). Applying aggressive enhancement.", i + 1, conf)
                enhanced = self._enhance_aggressive(np.array(img))
                text2, conf2 = self._run_tesseract(Image.fromarray(enhanced))
                if conf2 > conf:
                    text, conf = text2, conf2
            pages.append(text)
            confidences.append(conf)

        avg_conf = sum(confidences) / max(len(confidences), 1)
        logger.info("OCR complete. Avg confidence: %.1f%%", avg_conf)
        return pages, avg_conf / 100.0

    def ocr_image(self, path: str) -> tuple[str, float]:
        """OCR a single image file. Returns (text, confidence 0-1)."""
        img = Image.open(path).convert("RGB")
        text, conf = self.ocr_image_pil(img)
        if conf < self.MIN_CONFIDENCE:
            enhanced = self._enhance_aggressive(np.array(img))
            text2, conf2 = self._run_tesseract(Image.fromarray(enhanced))
            if conf2 > conf:
                text, conf = text2, conf2
        return text, conf / 100.0

    def ocr_image_pil(self, img: Image.Image) -> tuple[str, float]:
        """OCR a PIL image with standard enhancement. Returns (text, confidence 0-100)."""
        enhanced = self._enhance_standard(np.array(img))
        return self._run_tesseract(Image.fromarray(enhanced))

    # ------------------------------------------------------------------
    # Tesseract runner
    # ------------------------------------------------------------------

    def _run_tesseract(self, img: Image.Image) -> tuple[str, float]:
        try:
            data = pytesseract.image_to_data(
                img,
                lang=self.TESS_LANG,
                config=self.TESS_CONFIG,
                output_type=pytesseract.Output.DICT,
            )
            # Filter valid words
            words = []
            confs = []
            for i, word in enumerate(data["text"]):
                c = int(data["conf"][i])
                if c > 0 and word.strip():
                    words.append(word)
                    confs.append(c)

            text = pytesseract.image_to_string(img, lang=self.TESS_LANG, config=self.TESS_CONFIG)
            avg_conf = sum(confs) / max(len(confs), 1) if confs else 0.0
            return text, avg_conf
        except Exception as e:
            logger.error("Tesseract error: %s", e)
            return "", 0.0

    # ------------------------------------------------------------------
    # Image enhancement pipelines
    # ------------------------------------------------------------------

    def _enhance_standard(self, img_array: np.ndarray) -> np.ndarray:
        """Standard enhancement: grayscale → denoise → threshold."""
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY) if len(img_array.shape) == 3 else img_array
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def _enhance_aggressive(self, img_array: np.ndarray) -> np.ndarray:
        """Aggressive enhancement for low-quality scans: upscale → CLAHE → morph ops."""
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY) if len(img_array.shape) == 3 else img_array
        # Upscale 2x
        scaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        # CLAHE for contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        clahe_img = clahe.apply(scaled)
        # Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            clahe_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        # Morphological cleanup
        kernel = np.ones((1, 1), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        return cleaned
