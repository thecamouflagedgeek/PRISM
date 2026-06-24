from pdf2image import convert_from_path
import re

class OCRService:

    def __init__(self):
        self.ocr = None
    def pdf_to_image(self, pdf_path: str):
        pages = convert_from_path(pdf_path)
        return pages[0]  # you can extend for multi-page docs

    def image_to_text(self, image_path: str):

        return "OCR NOT CONFIGURED PROPERLY"

    def extract_text_from_pdf(self, pdf_path: str):
        image = self.pdf_to_image(pdf_path)

        temp_image_path = "temp_page.jpg"
        image.save(temp_image_path, "JPEG")

        text = self.image_to_text(temp_image_path)

        return text

    def clean_text(self, text: str):
        text = re.sub(r"[^\x00-\x7F]+", " ", text)  # remove weird chars
        text = re.sub(r"\n+", "\n", text)
        text = text.strip()

        return text



def get_ocr_engine():
    return OCRService()