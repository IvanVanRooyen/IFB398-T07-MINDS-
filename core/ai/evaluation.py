"""Offline quality regressions and optional, explicitly requested live-provider records."""

import hashlib
import json
from pathlib import Path

from .citations import VERSION as CITATION_VERSION
from .citations import audit_citations
from .passages import VERSION as PASSAGE_VERSION
from .passages import select_passage

DATASET = Path(__file__).with_name("evaluation_data") / "quality-v1.json"


def fixture_manifest(case):
    sources, documents = [], []
    for index, source in enumerate(case["sources"], 1):
        record = {
            "label": source["label"],
            "id": f"source-{index}",
            "url": f"/documents/source-{index}/",
        }
        sources.append(record)
        documents.append({**record, "excerpt": source["text"]})
    return {
        "schema_version": 2,
        "options": {"include_references": case.get("references_requested", True)},
        "sources": sources,
        "context": {"documents": documents},
    }


def run_evaluation(dataset_path=DATASET, *, live=False):
    raw = Path(dataset_path).read_bytes()
    data = json.loads(raw)
    retrieval = []
    for case in data["retrieval_cases"]:
        limit = case.get("byte_limit", 600)
        leading = case["text"].encode("utf-8")[:limit].decode("utf-8", errors="ignore")
        passage = select_passage(case["text"], case["query"], limit)
        gold = case["relevant_quotes"]
        retrieval.append(
            {
                "id": case["id"],
                "split": case["split"],
                "answerable": bool(gold),
                "leading_hit": any(quote in leading for quote in gold),
                "ranked_hit": any(quote in passage["text"] for quote in gold),
                "lexical_match": passage["score"] > 0,
                "passage": passage,
            }
        )
    citations = []
    for case in data["citation_cases"]:
        check = audit_citations(case["report"], fixture_manifest(case))
        observed = {
            **check,
            "quote_miss_count": sum(
                q["status"] == "not_found_in_supplied_excerpt" for q in check["quote_checks"]
            ),
            "unsupported_quantity_count": len(check["unsupported_quantities"]),
            "uncited_paragraph_count": len(check["uncited_paragraphs"]),
            "linked_mismatch_count": len(check["linked_citation_mismatches"]),
        }
        failures = {
            key: {"expected": value, "observed": observed.get(key)}
            for key, value in case["expected"].items()
            if observed.get(key) != value
        }
        citations.append(
            {
                "id": case["id"],
                "split": case["split"],
                "passed": not failures,
                "failures": failures,
                "audit": check,
            }
        )
    metrics = {}
    for split in ["all", *sorted({case["split"] for case in retrieval})]:
        rows = [row for row in retrieval if split == "all" or row["split"] == split]
        answers = [row for row in rows if row["answerable"]]
        absent = [row for row in rows if not row["answerable"]]
        metrics[split] = {
            "answerable_cases": len(answers),
            "leading_hit_rate": sum(row["leading_hit"] for row in answers) / max(1, len(answers)),
            "ranked_hit_rate": sum(row["ranked_hit"] for row in answers) / max(1, len(answers)),
            "no_answer_cases": len(absent),
            "no_answer_lexical_matches": sum(row["lexical_match"] for row in absent),
        }
    regressions = []
    for split, minimum in data.get("retrieval_thresholds", {}).items():
        observed = metrics.get(split, {}).get("ranked_hit_rate", 0)
        if observed < minimum:
            regressions.append({"split": split, "minimum": minimum, "observed": observed})
    result = {
        "dataset_version": data["version"],
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "passage_version": PASSAGE_VERSION,
        "citation_version": CITATION_VERSION,
        "retrieval_metrics": metrics,
        "retrieval_cases": retrieval,
        "citation_cases": citations,
        "citation_cases_passed": sum(row["passed"] for row in citations),
        "citation_cases_total": len(citations),
        "retrieval_regressions": regressions,
        "retrieval_thresholds": data.get("retrieval_thresholds", {}),
        "live_provider_used": live,
        "limitation": "Authored synthetic regression data. These scores do not establish real-world semantic relevance or factual accuracy.",
    }
    if live:
        from .granite_client import GraniteClient

        client = GraniteClient()
        runs = []
        for case in data.get("live_generation_cases", []):
            manifest = fixture_manifest(case)
            prompt = (
                "Answer using only these records. Cite [D1], [D2], etc. "
                "Do not invent facts; state when evidence is insufficient.\n"
                + json.dumps(manifest["context"], ensure_ascii=False)
                + "\nQuestion: "
                + case["question"]
            )
            text = client.complete(prompt)
            runs.append(
                {
                    "id": case["id"],
                    "model": client.model,
                    "backend": client.backend,
                    "prompt": prompt,
                    "response": text,
                    "citation_audit": audit_citations(text, manifest),
                    "semantic_review": "not_performed",
                }
            )
        result["live_generation_runs"] = runs
    return result
