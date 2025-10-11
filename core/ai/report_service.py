from __future__ import annotations
from datetime import datetime
from typing import Iterable

from django.db.models import QuerySet
from django.utils.timezone import localtime

from ..models import Process, Document
from .granite_client import GraniteClient

def _fmt_dt(dt):
    if not dt:
        return ""
    try:
        return localtime(dt).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt)

def fetch_process_bundle(process_id: str) -> dict:
    """
    Fetch the project (Process) and a small slice of related documents.
    Keep it light for now; you can expand the queryset/joins later.
    """
    proc = Process.objects.select_related("organisation").get(pk=process_id)
    docs: QuerySet[Document] = (
        Document.objects
        .filter(process=proc)
        .order_by("-timestamp", "-created_at")[:50]
        .only("id","title","timestamp","doc_type","commodity","author","confidentiality","file","created_at","checksum_sha256")
    )
    return {
        "process": proc,
        "docs": list(docs),
    }

def build_structured_context(bundle: dict) -> str:
    """
    Convert DB records into a compact, LLM-friendly context block.
    """
    p: Process = bundle["process"]
    lines = []
    lines.append(f"PROCESS")
    lines.append(f"  id: {p.id}")
    lines.append(f"  name: {p.name or ''}")
    lines.append(f"  mode: {p.mode}")
    lines.append(f"  commodity: {p.commodity or ''}")
    lines.append("")
    lines.append("DOCUMENTS (latest up to 50)")
    for d in bundle["docs"]:
        lines.append(
            "  - {"
            f"id: {d.id}, title: {d.title!r}, date: {d.timestamp}, type: {d.doc_type}, "
            f"commodity: {d.commodity or ''}, author: {d.author or ''}, "
            f"conf: {d.confidentiality}, created_at: {_fmt_dt(d.created_at)}"
            "}"
        )
    return "\n".join(lines)

REPORT_SYSTEM_INSTRUCTIONS = """You are a technical writer generating concise mining/exploration project reports.
Write clearly and factually, using only the provided context. If data is missing, say so briefly.
Output Markdown. Keep it structured with headings.
Audience: internal stakeholders (technical + managerial)."""

def build_prompt(context: str, as_of: str | None = None, sections: Iterable[str] | None = None) -> str:
    sections = sections or [
        "1. Project Summary",
        "2. Key Documents & Evidence",
        "3. Activities Timeline",
        "4. Commodities & Targets",
        "5. Data Gaps & Next Steps",
    ]
    as_of = as_of or datetime.utcnow().strftime("%Y-%m-%d")
    return f"""{REPORT_SYSTEM_INSTRUCTIONS}

DATE: {as_of}

CONTEXT:
{context}

TASK:
Generate a succinct, well-structured Markdown report for the project above.
Use the following section outline (omit any section with no information):

{chr(10).join(f"- {s}" for s in sections)}

Style:
- Bullet points where helpful.
- Include internal file names/links if present.
- Keep to ~400–700 words.
"""

def generate_project_report(process_id: str) -> str:
    """
    Orchestrates: fetch → structure → call Granite → return Markdown.
    """
    bundle = fetch_process_bundle(process_id)
    ctx = build_structured_context(bundle)
    prompt = build_prompt(ctx)

    client = GraniteClient()
    try:
        text = client.complete(prompt)
    except Exception as e:
        # Fall back to a plain template if model is offline
        p = bundle["process"]
        return f"""# {p.name or "Project"} — Auto Report (Fallback)

Granite unavailable. Minimal context below:

- Mode: {p.mode}
- Commodity: {p.commodity or "n/a"}
- Documents: {len(bundle["docs"])}

You can retry when the model service is reachable.
"""
    return text
