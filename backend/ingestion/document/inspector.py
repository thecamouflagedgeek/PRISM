"""
Document Inspector
-------------------
Single responsibility: determine whether a PDF is digital, scanned, or hybrid,
and produce a decrypted, readable file path for downstream extractors.

No transaction parsing, no OCR execution, no feature logic belongs here.
"""

import os
import tempfile
import pdfplumber
import pikepdf
from dataclasses import dataclass
from enum import Enum


class LayoutType(Enum):
    DIGITAL = "digital"
    SCANNED = "scanned"
    HYBRID = "hybrid"
    UNREADABLE = "unreadable"


@dataclass
class InspectionResult:
    layout_type: LayoutType
    readable_path: str          # decrypted temp path if the original was encrypted, else original path
    is_decrypted_temp: bool     # True if readable_path is a temp file the caller must clean up
    page_count: int
    digital_text_length: int    # length of text extracted via pdfplumber, used for the digital/scanned decision


class DocumentInspector:
    DIGITAL_TEXT_THRESHOLD = 50  # chars; below this we treat the doc as scanned

    def inspect(self, file_path: str, password: str = None) -> InspectionResult:
        readable_path, is_temp = self._decrypt_if_needed(file_path, password)

        try:
            with pdfplumber.open(readable_path) as pdf:
                page_count = len(pdf.pages)
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
        except Exception:
            return InspectionResult(
                layout_type=LayoutType.UNREADABLE,
                readable_path=readable_path,
                is_decrypted_temp=is_temp,
                page_count=0,
                digital_text_length=0,
            )

        text_length = len(text.strip())

        if text_length >= self.DIGITAL_TEXT_THRESHOLD:
            layout = LayoutType.DIGITAL
        else:
            layout = LayoutType.SCANNED

        return InspectionResult(
            layout_type=layout,
            readable_path=readable_path,
            is_decrypted_temp=is_temp,
            page_count=page_count,
            digital_text_length=text_length,
        )

    def _decrypt_if_needed(self, pdf_path: str, password: str = None) -> tuple[str, bool]:
        """
        Returns (path, is_temp_file). If the PDF is encrypted, decrypts to a
        temp file and returns that path with is_temp_file=True — caller is
        responsible for deleting it once done (see cleanup() below).
        """
        try:
            with pikepdf.open(pdf_path, password=password or "") as pdf:
                if pdf.is_encrypted:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    tmp.close()  # release handle before pikepdf writes — Windows requires this
                    pdf.save(tmp.name)
                    return tmp.name, True
        except pikepdf.PasswordError:
            raise ValueError("Incorrect password for encrypted PDF")
        return pdf_path, False

    def cleanup(self, result: InspectionResult):
        if result.is_decrypted_temp and os.path.exists(result.readable_path):
            try:
                os.remove(result.readable_path)
            except Exception:
                pass