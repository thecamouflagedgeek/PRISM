import pdfplumber
import fitz

def extract_txt_pdfplumbr(pdf_path):
    text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pgtxt = page.extract_text()
            if pgtxt:
                text += "\n" + pgtxt
    return text

def extract_txt_pymupdf(pdf_path):
    text = ""

    with fitz.open(pdf_path) as pdf:
        for page in pdf:
            pgtxt = page.get_text()
            if pgtxt:
                text += "\n" + pgtxt
    return text

