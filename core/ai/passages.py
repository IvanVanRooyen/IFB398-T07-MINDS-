"""Deterministic lexical passage ranking over canonical extracted document text."""

import math
import re
import unicodedata
from collections import Counter

VERSION = "bm25-windows-v1"
WINDOW_WORDS = 80
STOP_WORDS = frozenset(
    "a an and are as at be by for from has have how in is it of on or that the this to was were what which with please focus summary report project professional technical".split()
)


def terms(text):
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())
    return [word for word in words if word not in STOP_WORDS]


def windows(text, byte_limit=None):
    """Return exact character spans; overlapping word windows also cross paragraph breaks."""
    tokens = list(re.finditer(r"\S+", text))
    if not tokens:
        return []
    result = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + WINDOW_WORDS)
        if byte_limit is not None:
            low, high = start + 1, end
            while low < high:
                middle = (low + high + 1) // 2
                size = len(text[tokens[start].start() : tokens[middle - 1].end()].encode("utf-8"))
                if size <= byte_limit:
                    low = middle
                else:
                    high = middle - 1
            end = low
        result.append((tokens[start].start(), tokens[end - 1].end()))
        if end == len(tokens):
            break
        start += max(1, (end - start) * 3 // 4)
    return result


def rank(query, texts):
    """BM25 scores; corpus-local scores are for ordering, never confidence probabilities."""
    query_terms = list(dict.fromkeys(terms(query)))[:64]
    documents = [Counter(terms(text)) for text in texts]
    lengths = [sum(document.values()) for document in documents]
    mean_length = sum(lengths) / max(1, len(lengths)) or 1
    frequencies = {word: sum(word in doc for doc in documents) for word in query_terms}
    scores = []
    for doc, length in zip(documents, lengths):
        score = 0.0
        for word in query_terms:
            frequency = doc.get(word, 0)
            if not frequency:
                continue
            idf = math.log(
                1 + (len(documents) - frequencies[word] + 0.5) / (frequencies[word] + 0.5)
            )
            score += (
                idf * frequency * 2.5 / (frequency + 1.5 * (0.25 + 0.75 * length / mean_length))
            )
        scores.append(score)
    return scores


def select_passage(text, query, byte_limit):
    """Choose one passage and retain exact offsets of the text actually supplied.

    Without a lexical match, retain the selected file's leading text explicitly as
    an unranked fallback; file selection itself is never silently discarded.
    """
    spans = windows(text, max(1, byte_limit - 15))
    if not spans or byte_limit < 32:
        return {"text": "", "start": 0, "end": 0, "score": 0.0, "method": "no_text"}
    scores = rank(query, [text[start:end] for start, end in spans])
    best = max(range(len(spans)), key=lambda index: (scores[index], -spans[index][0]))
    start, end = spans[best]
    method = VERSION if scores[best] > 0 else "leading_no_lexical_match"
    # Reserve the suffix before encoding so Unicode boundaries remain intact.
    raw = text[start:end].encode("utf-8")
    partial = start > 0 or end < len(text) or len(raw) > byte_limit
    suffix = " [truncated]" if partial else ""
    selected = raw[: max(0, byte_limit - len(suffix))].decode("utf-8", errors="ignore")
    end = start + len(selected)
    return {
        "text": selected + suffix,
        "start": start,
        "end": end,
        "score": round(scores[best], 6),
        "method": method,
    }
