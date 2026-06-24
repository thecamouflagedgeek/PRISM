import fitz
import pdfplumber


def extract_txt_pdfplumber(file_path):

    text = ""

    try:

        with pdfplumber.open(file_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:

                    text += page_text + "\n"

    except Exception:

        pass

    return text


def extract_txt_pymupdf(file_path):

    text = ""

    try:

        doc = fitz.open(file_path)

        for page in doc:

            text += page.get_text()

        doc.close()

    except Exception:

        pass

    return text