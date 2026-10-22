"""Offline answerer: no API key needed. It answers only when one doc section clearly covers
the question, quoting that section's opening sentences. Everything else becomes a ticket.

It exists so judges can run the whole demo without keys. With ANTHROPIC_API_KEY set,
DocDesk uses the Claude answerer from communityops instead."""

from __future__ import annotations

import re
import time

from communityops.answer import NO_DOCS_REPLY, Result, decide
from communityops.store import Hit, Store

from .memory import terms

_MD = re.compile(r"[*_`#>]+")


def best_sentences(text: str, question: str, n: int = 2, max_chars: int = 420) -> str:
    """The n sentences sharing the most words with the question, kept in document order.
    Ties go to earlier sentences, so a section's opening line wins when nothing stands out."""
    flat = " ".join(_MD.sub("", line).strip(" -") for line in text.splitlines() if line.strip())
    parts = [p for p in re.split(r"(?<=[.!?])\s+", flat) if p]
    q = terms(question)
    ranked = sorted(range(len(parts)), key=lambda i: (-len(q & terms(parts[i])), i))[:n]
    out = " ".join(parts[i] for i in sorted(ranked)).strip()
    return out if len(out) <= max_chars else out[: max_chars - 3].rsplit(" ", 1)[0] + "..."


def coverage(question: str, hit: Hit) -> float:
    """Share of the question's content words that appear in the excerpt or its heading."""
    q = terms(question)
    if not q:
        return 0.0
    return len(q & terms(f"{hit.title} {hit.heading} {hit.text}")) / len(q)


class OfflineAnswerer:
    """Same interface as communityops.answer.Answerer: `await answer(question) -> Result`."""

    min_coverage = 0.75

    def __init__(self, store: Store, top_k: int = 6):
        self.store = store
        self.top_k = top_k

    async def answer(self, question: str) -> Result:
        started = time.monotonic()
        hits = self.store.search(question, k=self.top_k)
        if not hits:
            return Result(question, "no_docs", NO_DOCS_REPLY, reason="no matching doc excerpts")
        scored = sorted(enumerate(hits, 1), key=lambda ih: coverage(question, ih[1]), reverse=True)
        best_n, best = scored[0]
        cov = coverage(question, best)
        if cov >= self.min_coverage:
            data = {
                "answerable": True,
                "answer": best_sentences(best.text, question),
                "citations": [best_n],
                "confidence": "medium",
                "escalation_reason": "",
            }
        else:
            data = {
                "answerable": False,
                "answer": "",
                "citations": [],
                "confidence": "low",
                "escalation_reason": f"offline mode: best excerpt covers {cov:.0%} of the question",
            }
        result = decide(question, data, hits)
        result.model = "offline-extractive"
        result.latency_ms = int((time.monotonic() - started) * 1000)
        return result
