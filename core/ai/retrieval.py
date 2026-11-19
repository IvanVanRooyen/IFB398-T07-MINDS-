from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q

from ..instrument import instrument
from ..models import DocumentChunk, Process
from .passages import terms

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


@instrument
def query_chunks(
    query: str,
    process: Process | None = None,
    doc_type: str | None = None,
    date_from=None,
    date_to=None,
    max_chunks: int = 10,
    clearance_level: str = "INTERNAL",
    document_ids=None,
) -> list[DocumentChunk]:
    """
    Retrieve relevant chunks using metadata filtering and keyword matching.

    Metadata filters narrow the candidate set first, then keyword search finds
    the most relevant chunks within that set.  Only chunks whose parent document
    falls within the caller's clearance level are returned.
    """

    if not isinstance(max_chunks, int) or max_chunks <= 0:
        return []
    max_chunks = min(max_chunks, 50)
    qs = DocumentChunk.objects.select_related("document", "process")

    # clearance filter, only surface chunks from documents that caller can see
    user_level = _CLEARANCE_LEVELS.get(clearance_level, -1)
    accessible_confidentiality = [
        conf for conf, level in _CONFIDENTIALITY_MAP.items() if level <= user_level
    ]
    qs = qs.filter(document__confidentiality__in=accessible_confidentiality)

    # Metadata filters
    if process:
        qs = qs.filter(
            process=process,
            document__process=process,
            document__organisation=process.organisation,
            document__is_latest=True,
        )
    else:
        # There is no caller/organisation context for an unscoped retrieval.
        return []
    qs = qs.filter(
        Q(document__tenement__isnull=True)
        | Q(document__tenement__organisation=process.organisation)
    )
    if doc_type:
        qs = qs.filter(document__doc_type__iexact=doc_type)
    if date_from:
        qs = qs.filter(document__timestamp__gte=date_from)
    if date_to:
        qs = qs.filter(document__timestamp__lte=date_to)

    if document_ids is not None:
        if not document_ids:
            return []
        qs = qs.filter(document_id__in=document_ids)
    words = list(dict.fromkeys(terms(query or "")))[:64]
    if words:
        search = SearchQuery(words[0], config="english")
        for word in words[1:]:
            search |= SearchQuery(word, config="english")
        qs = qs.annotate(search_vector=SearchVector("text", config="english"))
        qs = qs.filter(search_vector=search).annotate(relevance=SearchRank("search_vector", search))
        qs = qs.order_by("-relevance", "document_id", "chunk_index", "pk")
    elif query and query.strip():
        return []
    else:
        qs = qs.order_by("document_id", "chunk_index", "pk")
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
    Convenience wrapper — retrieve chunks and format in one call.
    Used in report_service.py.
    """
    return retrieve_evidence(query, process=process, clearance_level=clearance_level, **kwargs)[0]


def retrieve_evidence(query, process=None, clearance_level="INTERNAL", **kwargs):
    """Return text and the exact parent-document IDs of the supplied excerpts."""
    chunks = query_chunks(query, process=process, clearance_level=clearance_level, **kwargs)
    return format_chunks_for_prompt(chunks), list(
        dict.fromkeys(str(chunk.document_id) for chunk in chunks)
    )
