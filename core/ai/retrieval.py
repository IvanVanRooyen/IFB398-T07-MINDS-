from __future__ import annotations
from django.db.models import Q
from ..models import DocumentChunk, Process

def query_chunks(
    query: str,
    process: Process | None = None,
    doc_type: str | None = None,
    date_from=None,
    date_to=None,
    max_chunks: int = 10,
)-> list[DocumentChunk]:
    """
    Retrieve relevant chunks using metadata filtering and keyword matching.

    Metadata filters narrow the candidate set first, then keyword search finds
    the most relevant chunks withing that set
    """

    qs = DocumentChunk.objects.select_related("document", "process")

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

def format_chunks_for_prompt(chunks: list[DocumnentChunk]) -> str:
    """
    Format retrieved chunks into a text block for an LLM prompt.
    Each chunk is labelled with its source document.
    """
    if not chunks:
        return "No relevant deocument content found."
    
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
    **kwargs,
) -> str:
    """
    Convenience wrapper - retreive chunks and format in one call.
    Used in report_service.py
    """
    chunks = query_chunks(query, process=process, **kwargs)
    return format_chunks_for_prompt(chunks)