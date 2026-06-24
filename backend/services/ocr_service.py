from pdf2image import convert_from_path
from paddleocr import PaddleOCR
import re
import os


class OCRService:

    def __init__(self):

        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en"
        )

    def pdf_to_image(self, pdf_path: str):

        pages = convert_from_path(pdf_path)

        temp_image_path = "temp_page.jpg"

        pages[0].save(
            temp_image_path,
            "JPEG"
        )

        return temp_image_path

    def image_to_text(self, image_path: str):

        result = self.ocr.predict(
            image_path
        )

        text = ""

        for page in result:

            try:
                text += "\n".join(
                    page["rec_texts"]
                )
            except:
                text += str(page)

        return text

    def extract_text_from_pdf(self, pdf_path: str):

        image_path = self.pdf_to_image(
            pdf_path
        )

        text = self.image_to_text(
            image_path
        )

        if os.path.exists(image_path):
            os.remove(image_path)

        return text

    def clean_text(self, text: str):

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