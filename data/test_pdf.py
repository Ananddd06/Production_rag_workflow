import sys
import pdfplumber

def test_plumber():
    try:
        with pdfplumber.open("/app/data/LLM from scratch .pdf") as pdf:
            page = pdf.pages[10]
            print("pdfplumber output:")
            print(repr(page.extract_text()[:200]))
    except Exception as e:
        print("Error:", e)

test_plumber()
