import pikepdf
import tempfile
import os
import pdfplumber
import re
class OCRService:

    def _decrypt_if_needed(self, pdf_path: str, password: str = None) -> str:
        try:
            with pikepdf.open(pdf_path, password=password or "") as pdf:
                if pdf.is_encrypted:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    tmp.close()          
                    pdf.save(tmp.name)
                    return tmp.name
        except pikepdf.PasswordError:
            raise ValueError("Incorrect password for encrypted PDF")
        return pdf_path

    def extract_text(self, pdf_path: str, password: str = None):
        decrypted_path = self._decrypt_if_needed(pdf_path, password)
        is_temp_file = decrypted_path != pdf_path
        try:
            text = self.extract_text_from_pdfplumber(decrypted_path)
            if len(text.strip()) > 100:
                return self.clean_text(text)

            text = self.extract_using_tesseract(pdf_path)
            return self.clean_text(text)
        finally:
            if is_temp_file:
                try:
                    os.remove(decrypted_path)
                except Exception:
                    pass

    def extract_text_from_pdfplumber(self, pdf_path: str):
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def extract_using_tesseract(self, pdf_path: str):
        pages = convert_from_path(pdf_path)
        text = ""
        for page in pages:
            text += pytesseract.image_to_string(page)
            text += "\n"
        return text

    def clean_text(self, text: str):
        text = re.sub(r"[^\x00-\x7F]+", " ", text)
        text = re.sub(r"\n+", "\n", text)
        return text.strip()


def get_ocr_engine():
    return OCRService()
