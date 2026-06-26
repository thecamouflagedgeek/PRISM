import os
import re
import pdfplumber
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

from pdf2image import convert_from_path


class OCRService:

    def extract_text(self, pdf_path: str):

        text = self.extract_text_from_pdfplumber(
            pdf_path
        )

        if len(text.strip()) > 100:
            return self.clean_text(text)

        text = self.extract_using_tesseract(
            pdf_path
        )

        return self.clean_text(text)

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
            pdf_path
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