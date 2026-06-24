import io
import pdfplumber
import pytesseract

from pdf2image import convert_from_bytes
from PIL import Image


async def extract_text(file):

    contents = await file.read()
    filename = file.filename.lower()

    # ---------- TXT ----------
    if filename.endswith(".txt"):
        return contents.decode("utf-8", errors="ignore")

    # ---------- PDF ----------
    elif filename.endswith(".pdf"):

        try:
            text = ""

            with pdfplumber.open(io.BytesIO(contents)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()

                    if page_text:
                        text += page_text + "\n"

            # If PDF already contains text
            if text.strip():
                return text

        except Exception:
            pass

        # OCR fallback for scanned PDFs
        pages = convert_from_bytes(contents)

        text = ""

        for page in pages:
            text += pytesseract.image_to_string(page)

        return text

    # ---------- Images ----------
    elif filename.endswith((".png", ".jpg", ".jpeg")):

        image = Image.open(io.BytesIO(contents))

        return pytesseract.image_to_string(image)

    else:
        raise Exception(f"Unsupported file type: {filename}")