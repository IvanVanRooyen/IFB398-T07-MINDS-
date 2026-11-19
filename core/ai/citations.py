"""Inspectable citation mechanics and excerpt checks, without semantic truth claims."""

import re
import unicodedata
from decimal import Decimal

VERSION = "citation-audit-v1"
MARKER = re.compile(r"\[([dD]\d[^\]\n]{0,64})\]")
VALID_GROUP = re.compile(r"D\d+(?:\s*[,;]\s*D\d+)*")
NUMBER = re.compile(
    r"(?<![\w.])(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|ppm\b|ppb\b|g/t\b|km\b|m\b|Mt\b|t\b)", re.I
)
QUOTE = re.compile(r'["“]([^"“”\n]{3,500})["”]')
FOOTER_ROW = re.compile(r"^\s*[-*]\s+\[D\d+\]\s+\[.*\]\([^\n]*\)\s+[—-]\s+v\d+\s*$")
DEFINITION = re.compile(r"^\s*\[(D\d+)\]:\s*(\S+)\s*$")


def _normal(text):
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def _quantities(text):
    # Unit conversion, inference and calculated quantities require human review.
    return {
        (Decimal(number.replace(",", "")), unit.casefold()) for number, unit in NUMBER.findall(text)
    }


def audit_citations(markdown, manifest):
    """Audit the current body against the supplied excerpts, excluding source-list credit.

    Quotes/quantities are checked against passages cited within their paragraph.
    Coverage counts paragraphs, not factual claims. No result certifies correctness.
    """
    if not isinstance(manifest, dict) or not manifest.get("schema_version"):
        return {
            "version": VERSION,
            "status": "unavailable",
            "summary": "No recorded generation inputs are available.",
            "review_notes": [],
        }
    sources = manifest.get("sources")
    container = manifest.get("context")
    context = container.get("documents") if isinstance(container, dict) else None
    if (
        not isinstance(sources, list)
        or not isinstance(context, list)
        or not isinstance(manifest.get("options"), dict)
        or any(
            not isinstance(source, dict)
            or not isinstance(source.get("label"), str)
            or not source.get("id")
            for source in sources
        )
        or any(
            not isinstance(source, dict)
            or not isinstance(source.get("label"), str)
            or not source.get("id")
            or not isinstance(source.get("excerpt", ""), str)
            for source in context
        )
    ):
        return {
            "version": VERSION,
            "status": "unavailable",
            "summary": "The generation input record is incomplete.",
            "review_notes": [],
        }
    records = {source["label"]: source for source in sources}
    supplied = {
        source["label"]: source.get("excerpt", "")
        for source in context
        if source.get("label") in records and source.get("id") == records[source["label"]].get("id")
    }
    required = bool(manifest.get("options", {}).get("include_references"))
    # Code samples and deterministic appended source lists do not cite report prose.
    body = re.sub(r"```[^\n]*\n.*?```", "", markdown, flags=re.S)
    body = re.sub(r"`[^`\n]+`", "", body)
    lines = [
        line
        for line in body.splitlines()
        if not FOOTER_ROW.match(line) and not DEFINITION.match(line)
    ]
    blocks = [
        "\n".join(
            line for line in block.splitlines() if not re.match(r"^\s*#{1,6}\s", line)
        ).strip()
        for block in re.split(r"\n\s*\n|\n(?=\s*(?:[-*+]\s+|\d+[.)]\s+))", "\n".join(lines))
    ]
    blocks = [block for block in blocks if block and not re.fullmatch(r"[-*_\s]+", block)]
    cited, unknown, malformed, mismatches = set(), set(), set(), []
    # Validate markers in headings and declarations too, without crediting them
    # toward paragraph citation coverage.
    for marker in MARKER.finditer(body):
        group = marker.group(1)
        if not VALID_GROUP.fullmatch(group):
            malformed.add(group)
        else:
            unknown.update(label for label in re.findall(r"D\d+", group) if label not in supplied)
    for group, url in re.findall(r"\[(D\d+(?:\s*[,;]\s*D\d+)*)\]\(([^)]+)\)", body):
        for label in re.findall(r"D\d+", group):
            expected = (
                records.get(label, {}).get("url")
                or f"/documents/{records.get(label, {}).get('id')}/"
            )
            if label in supplied and url != expected:
                mismatches.append({"paragraph": None, "label": label, "url": url})
    for line in body.splitlines():
        definition = DEFINITION.match(line)
        if FOOTER_ROW.match(line) or definition:
            label = definition.group(1) if definition else re.search(r"\[(D\d+)\]", line).group(1)
            if label not in supplied:
                unknown.add(label)
            else:
                linked = re.search(r"\]\(([^)]+)\)", line)
                expected = records[label].get("url") or f"/documents/{records[label]['id']}/"
                destination = (
                    definition.group(2) if definition else linked.group(1) if linked else None
                )
                if destination and destination != expected:
                    mismatches.append({"paragraph": None, "label": label, "url": destination})
    quotes, unsupported_quantities, uncited = [], [], []
    cited_blocks, marker_count = 0, 0
    for index, block in enumerate(blocks, 1):
        labels = []
        for marker in MARKER.finditer(block):
            group = marker.group(1)
            if not VALID_GROUP.fullmatch(group):
                malformed.add(group)
                continue
            for label in re.findall(r"D\d+", group):
                marker_count += 1
                if label not in supplied:
                    unknown.add(label)
                else:
                    labels.append(label)
                    cited.add(label)
        if labels:
            cited_blocks += 1
        elif required and supplied:
            uncited.append({"paragraph": index, "preview": block[:180]})
        evidence = "\n".join(supplied[label] for label in dict.fromkeys(labels))
        for quote in QUOTE.findall(block):
            status = (
                (
                    "matched_supplied_excerpt"
                    if _normal(quote) in _normal(evidence)
                    else "not_found_in_supplied_excerpt"
                )
                if labels
                else "uncited"
            )
            quotes.append(
                {
                    "paragraph": index,
                    "quote": quote,
                    "labels": sorted(set(labels)),
                    "status": status,
                }
            )
        if labels:
            evidence_quantities = _quantities(evidence)
            for number, unit in sorted(_quantities(MARKER.sub("", block)) - evidence_quantities):
                unsupported_quantities.append(
                    {
                        "paragraph": index,
                        "value": str(number),
                        "unit": unit,
                        "labels": sorted(set(labels)),
                    }
                )
    quote_misses = [quote for quote in quotes if quote["status"] == "not_found_in_supplied_excerpt"]
    issues = bool(
        unknown or malformed or mismatches or uncited or quote_misses or unsupported_quantities
    )
    status = (
        "issues_found"
        if issues
        else "no_document_evidence"
        if not supplied
        else "references_not_requested"
        if not required
        else "no_report_prose"
        if not blocks
        else "no_structural_issues"
    )
    notes = []
    if unknown:
        notes.append("Unknown source labels: " + ", ".join(sorted(unknown)) + ".")
    if malformed:
        notes.append("Malformed source markers: " + ", ".join(sorted(malformed)) + ".")
    for count, singular, plural in [
        (
            len(mismatches),
            "source link differs from its recorded destination",
            "source links differ from their recorded destination",
        ),
        (
            len(uncited),
            "paragraph or list item has no recognised document citation",
            "paragraphs or list items have no recognised document citation",
        ),
        (
            len(quote_misses),
            "quoted passage was not found in its cited excerpts",
            "quoted passages were not found in their cited excerpts",
        ),
        (
            len(unsupported_quantities),
            "measurement was not found in its cited excerpts",
            "measurements were not found in their cited excerpts",
        ),
    ]:
        if count:
            notes.append(f"{count} {singular if count == 1 else plural}.")
    empty = sorted(label for label, text in supplied.items() if not text.strip())
    if empty:
        notes.append("No extracted excerpt text for: " + ", ".join(empty) + ".")
    for item in quote_misses[:5]:
        notes.append(
            f"Paragraph {item['paragraph']}: quote not found in cited excerpts: {item['quote'][:100]}"
        )
    for item in unsupported_quantities[:5]:
        notes.append(
            f"Paragraph {item['paragraph']}: measurement {item['value']} {item['unit']} not found in cited excerpts."
        )
    summary = {
        "issues_found": "Citation issues need review.",
        "no_document_evidence": "No document excerpts were supplied.",
        "references_not_requested": "Source references were disabled for this generation.",
        "no_report_prose": "No report prose was available to check.",
        "no_structural_issues": "The checked source labels and literal excerpt matches resolve.",
    }[status]
    return {
        "version": VERSION,
        "status": status,
        "summary": summary,
        "review_notes": notes,
        "references_requested": required,
        "supplied_labels": sorted(supplied),
        "empty_excerpt_labels": sorted(
            label for label, text in supplied.items() if not text.strip()
        ),
        "cited_labels": sorted(cited),
        "unknown_labels": sorted(unknown),
        "malformed_markers": sorted(malformed),
        "linked_citation_mismatches": mismatches,
        "marker_count": marker_count,
        "paragraph_count": len(blocks),
        "cited_paragraph_count": cited_blocks,
        "uncited_paragraphs": uncited,
        "quote_checks": quotes,
        "unsupported_quantities": unsupported_quantities,
        "limitation": "Source labels, paragraph coverage and literal excerpt matches do not establish factual or semantic support.",
    }
