import hashlib
import pdfplumber
import logging

from django.contrib.gis.db import models


def sha256_file(django_file) -> str:
    pos = django_file.tell()  # remember current position
    django_file.seek(0)

    h = hashlib.sha256()

    # Use chunks() if available (IMPORTANT for uploaded files)
    if hasattr(django_file, "chunks"):
        for chunk in django_file.chunks():
            if chunk:
                h.update(chunk)
    else:
        # fallback for non-uploaded file objects
        for chunk in iter(lambda: django_file.read(8192), b""):
            h.update(chunk)

    django_file.seek(pos)  # restore pointer
    return h.hexdigest()

log = logging.getLogger(__name__)

def extract_text(file_field) -> str:
    """
    Extract plain text from a pdf file.
    """
    try:
        name = getattr(file_field, "name", "") or ""
        if not name.lower().endswith(".pdf"):
            return ""
        
        # read the file into memory
        file_field.seek(0)
        raw = file_field.read()
        file_field.seek(0) # reset so the file saves correctly

        import io
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except Exception as e:
        log.warning("Text extraction failed for %s: %s", file_field.name, e)
        return ""
    
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks for RAG retrieval

    chunk_size: number of words per chunk
    overlap: words repeated at the start of the next chunk so sentences split accross a 
             boundary are not lost.
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

# class AutoConstraintMeta(type(models.Model)):
#     """
#     Metaclass to automatically generate constraints for choice field validation
#     """
#
#     def __new__(mcs, name, bases, namespace, **kwargs):
#         cls: models.Model = super().__new__(mcs, name, bases, namespace, **kwargs)
#
#         if namespace.get("Meta") and getattr(namespace["Meta"], "abstract", False):
#             return cls
#
#         if not hasattr(cls._meta, "constraints"):
#             cls._meta.constraints = []
#
#         for field in cls._meta.fields:
#             if field.choices and not any(
#                 field.name in str(c.check) for c in cls._meta.constraints
#             ):
#                 constraint = choice_constraint(
#                     field.name,
#                     field.choices,
#                     f"valid_{cls._meta.db_table}_{field.name}",
#                 )
#                 cls._meta.constraints.append(constraint)
#
#         return cls


# class AutoConstrainedModel(ValidatedChoiceModel,):
#     class Meta:
#         abstract = True
