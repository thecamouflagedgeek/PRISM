import pdfplumber
import fitz

def extract_txt_pdfplumber(pdf_path):
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pgtxt = page.extract_text()
            pages_text.append(pgtxt or "")
    return "\n\f\n".join(pages_text)

def extract_txt_pymupdf(pdf_path):
    pages_text = []
    with fitz.open(pdf_path) as pdf:
        for page in pdf:
            pgtxt = page.get_text()
            pages_text.append(pgtxt or "")
    return "\n\f\n".join(pages_text)

