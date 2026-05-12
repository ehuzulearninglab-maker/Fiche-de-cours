"""
PDF text extraction module.
"""
import fitz
import os


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    page_count = doc.page_count
    doc.close()
    return text, page_count


def extract_text_from_uploaded(file_storage, upload_dir: str) -> tuple:
    """Save uploaded file and extract text. Returns (text, filepath)."""
    filename = file_storage.filename
    filepath = os.path.join(upload_dir, filename)
    file_storage.save(filepath)
    text, page_count = extract_text_from_pdf(filepath)
    return text, filepath, page_count
