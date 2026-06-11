import fitz
doc = fitz.open("/Users/anand/Desktop/LLM from scratch .pdf")
print("PyMuPDF output:")
print(repr(doc[10].get_text("text")[:200]))

import pypdf
reader = pypdf.PdfReader("/Users/anand/Desktop/LLM from scratch .pdf")
print("\npypdf output:")
print(repr(reader.pages[10].extract_text()[:200]))
