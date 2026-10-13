import fitz
import pdfplumber


def extract_txt_pdfplumber(file_path:str,password: str = None) -> str:

    text = ""

    try:

        with pdfplumber.open(file_path,password=password) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:

                    text += page_text + "\n"

    except Exception:

        pass

    return text


def extract_txt_pymupdf(file_path,password: str = None) -> str:
    text = ""
    try:
        doc = fitz.open(file_path)
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                raise ValueError("Incorrect password for PDF file.")
        for page in doc:
            text += page.get_text()
        doc.close()
    except Exception:
        pass
    return text