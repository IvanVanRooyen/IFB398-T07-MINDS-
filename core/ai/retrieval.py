from __future__ import annotations

from django.db.models import Q

from ..models import DocumentChunk, Process

# mirrrors the hierarchy used in UserProfile.can_access_document and report_service.py
_CLEARANCE_LEVELS = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "JORC_APPROVED": 3,
}

_CONFIDENTIALITY_MAP = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "jorc_restricted": 3,
}


def query_chunks(
    query: str,
    process: Process | None = None,
    doc_type: str | None = None,
    date_from=None,
    date_to=None,
    max_chunks: int = 10,
    clearance_level: str = "INTERNAL",
) -> list[DocumentChunk]:
    """
    Retrieve relevant chunks using metadata filtering and keyword matching.

    Metadata filters narrow the candidate set first, then keyword search finds
    the most relevant chunks within that set.  Only chunks whose parent document
    falls within the caller's clearance level are returned.
    """

    qs = DocumentChunk.objects.select_related("document", "process")

    # clearance filter, only surface chunks from documents that caller can see
    user_level = _CLEARANCE_LEVELS.get(clearance_level, 1)
    accessible_confidentiality = [
        conf for conf, level in _CONFIDENTIALITY_MAP.items() if level <= user_level
    ]
    qs = qs.filter(document__confidentiality__in=accessible_confidentiality)

    # Metadata filters
    if process:
        qs = qs.filter(process=process)
    if doc_type:
        qs = qs.filter(doc_type__iexact=doc_type)
    if date_from:
        qs = qs.filter(timestamp__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__lte=date_to)

    # Keyword match
    if query and query.strip():
        words = query.strip().split()
        q_filter = Q()
        for word in words:
            q_filter |= Q(text__icontains=word)
        qs = qs.filter(q_filter)

    return list(qs[:max_chunks])


def format_chunks_for_prompt(chunks: list[DocumentChunk]) -> str:
    """
    Format retrieved chunks into a text block for an LLM prompt.
    Each chunk is labelled with its source document.
    """
    if not chunks:
        return "No relevant document content found."

    lines = []
    current_doc = None

    for chunk in chunks:
        if chunk.document_id != current_doc:
            current_doc = chunk.document_id
            doc = chunk.document
            lines.append(
                f"\n--- SOURCE: {doc.title} "
                f"| type: {doc.doc_type or 'unknown'}"
                f"| date: {doc.timestamp or 'unknown'} ---"
            )
        lines.append(chunk.text)

    return "\n".join(lines)


def retrieve_context(
    query: str,
    process: Process | None = None,
    clearance_level: str = "INTERNAL",
    **kwargs,
) -> str:
    """
    Convenience wrapper - retrieve chunks and format in one call.
    Used in report_service.py.
    """
    chunks = query_chunks(
        query, process=process, clearance_level=clearance_level, **kwargs
    )

    return format_chunks_for_prompt(chunks)

