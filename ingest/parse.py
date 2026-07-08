from pathlib import Path
import pdfplumber

def extract_pages(pdf_path: Path) -> list[dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            pages.append({"page": i, "text": page.extract_text() or ""})
    return pages
