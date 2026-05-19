import hashlib
import io
import logging

import pdfplumber

from .instrument import instrument

log = logging.getLogger(__name__)


@instrument
def sha256_file(django_file) -> str:
    # Save and restore the file pointer so callers can still read or save the
    # file after hashing — InMemoryUploadedFile does not auto-rewind.
    pos = django_file.tell()
    django_file.seek(0)

    h = hashlib.sha256()

    # Use chunks() if available (important for uploaded files)
    if hasattr(django_file, "chunks"):
        for chunk in django_file.chunks():
            if chunk:
                h.update(chunk)
    else:
        for chunk in iter(lambda: django_file.read(8192), b""):
            h.update(chunk)

    django_file.seek(pos)  # restore pointer
    return h.hexdigest()


@instrument
def extract_text(file_field) -> str:
    """Extract plain text from a PDF or DOCX file field."""
    try:
        name = getattr(file_field, "name", "") or ""
        lower_name = name.lower()

        file_field.seek(0)
        raw = file_field.read()
        file_field.seek(0)  # reset so the file saves correctly

        if lower_name.endswith(".pdf"):
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            return "\n".join(pages)

        if lower_name.endswith(".docx"):
            from docx import Document as DocxDocument

            doc = DocxDocument(io.BytesIO(raw))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)

        return ""

    except Exception as e:
        log.warning("Text extraction failed for %s: %s", getattr(file_field, "name", "unknown"), e)
        return ""


@instrument
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks for RAG retrieval.

    chunk_size: number of words per chunk
    overlap: words repeated at the start of the next chunk so sentences split
             across a boundary are not lost.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap

    return chunks
