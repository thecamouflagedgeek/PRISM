import os
import shutil
import tempfile
import pikepdf
import re
import shutil
import tempfile
import pikepdf
import pdfplumber
import pytesseract

_TESSERACT_CANDIDATES = (
    os.getenv("TESSERACT_CMD"),
    shutil.which("tesseract"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)
_TESSERACT_PATH = next((p for p in _TESSERACT_CANDIDATES if p and os.path.isfile(p)), None)
if _TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH

from pdf2image import convert_from_path


class OCRService:

    def _decrypt_if_needed(self, pdf_path: str, password: str = None):
        if password is None:
            return pdf_path, False
        try:
            with pikepdf.open(pdf_path, password=password) as pdf:
                if not pdf.is_encrypted:
                    return pdf_path, False
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                tmp.close()
                pdf.save(tmp.name)
                return tmp.name, True
        except pikepdf.PasswordError as exc:
            raise ValueError("Incorrect password for encrypted PDF") from exc

    def extract_text(self, pdf_path: str, password: str = None):
        return self.extract_text_with_metadata(pdf_path, password=password)[0]

    def extract_text_with_metadata(self, pdf_path: str, password: str = None):
        """Return text plus a 0–1 native/OCR extraction confidence estimate."""
        readable_path, is_temp = self._decrypt_if_needed(pdf_path, password)
        try:
            try:
                text = self.extract_text_from_pdfplumber(readable_path)
            except Exception:
                text = ""

            if len(text.strip()) > 100:
                return self.clean_text(text), 1.0

            poppler_cmd = shutil.which("pdftoppm")
            poppler_dir = os.getenv("POPPLER_PATH") or (os.path.dirname(poppler_cmd) if poppler_cmd else None)
            pages = convert_from_path(readable_path, poppler_path=poppler_dir)
            texts, confidences = [], []
            for page in pages:
                data = pytesseract.image_to_data(page, output_type=pytesseract.Output.DICT)
                texts.append(pytesseract.image_to_string(page))
                for value in data.get("conf", []):
                    try:
                        numeric_confidence = float(value)
                    except (TypeError, ValueError):
                        continue
                    if numeric_confidence >= 0:
                        confidences.append(numeric_confidence)
            text = self.clean_text("\n\f\n".join(texts))
            confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
            return text, confidence
        finally:
            if is_temp:
                try:
                    os.remove(readable_path)
                except OSError:
                    pass

    def extract_text_from_pdf(self, pdf_path: str, password: str = None):
        """Compatibility interface used by the shared ingestion pipeline."""
        return self.extract_text(pdf_path, password=password)

    def extract_text_from_pdfplumber(
        self,
        pdf_path: str
    ):

        text = ""

        with pdfplumber.open(pdf_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

        return text

    def extract_using_tesseract(
        self,
        pdf_path: str
    ):

        pages = convert_from_path(
    pdf_path,
    poppler_path=r"C:\poppler-26.02.0\Library\bin"
)

        text = ""

        for page in pages:

            text += pytesseract.image_to_string(
                page
            )

            text += "\n"

        return text

    def clean_text(
        self,
        text: str
    ):

        text = re.sub(
            r"[^\x00-\x7F]+",
            " ",
            text
        )

        text = re.sub(
            r"\n+",
            "\n",
            text
        )

        return text.strip()


def get_ocr_engine():

    return OCRService()
