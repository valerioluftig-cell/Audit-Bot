import pdfplumber, pathlib, sys
sys.path.insert(0, r'C:\Users\valer\Downloads\audit_project\pipeline')
from extractor import find_statement_pages

for parish, pdf_path in [
    ('LaSalle',    r'C:\Users\valer\Downloads\audit_project\runs\e44ac3c9\pdfs\LaSalle.pdf'),
    ('St. Martin', r'C:\Users\valer\Downloads\audit_project\runs\e44ac3c9\pdfs\St. Martin.pdf'),
]:
    print(f'\n=== {parish} ===')
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        print(f'  Pages: {n}')
        text_pages = 0
        image_pages = 0
        for i, page in enumerate(pdf.pages):
            t = page.extract_text() or ''
            imgs = page.images
            if t.strip():
                text_pages += 1
                if i < 3:
                    print(f'  Page {i+1} (text): {repr(t[:120])}')
            else:
                image_pages += 1
        print(f'  Text pages: {text_pages}  /  Image-only pages: {image_pages}')
        pages = find_statement_pages(pdf_path)
        print(f'  Detected stmt pages: {pages}')
