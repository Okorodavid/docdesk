"""One SQLite file holds the docs index (FTS5, BM25 ranking) and the question log."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    url TEXT PRIMARY KEY,
    title TEXT,
    fetched_at REAL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    text, title, heading, url UNINDEXED, source UNINDEXED,
    tokenize = 'porter unicode61'
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    platform TEXT NOT NULL,
    chat_id INTEGER,
    chat_title TEXT,
    message_id INTEGER,
    user_id INTEGER,
    username TEXT,
    question TEXT NOT NULL,
    answer TEXT,
    citations TEXT,
    confidence TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS questions_ts ON questions(ts);
"""

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does", "for",
    "from", "get", "has", "have", "hi", "hello", "how", "i", "if", "in", "is", "it", "its",
    "me", "my", "no", "not", "of", "on", "or", "please", "so", "that", "the", "their",
    "there", "this", "to", "was", "we", "what", "when", "where", "which", "who", "why",
    "will", "with", "you", "your", "anyone", "help", "guys",
}

# Statuses a question can end in. "answered" is the only one that does not escalate.
STATUSES = ("answered", "escalated", "no_docs", "refused", "error", "limited")


@dataclass
class Chunk:
    text: str
    title: str
    heading: str
    url: str
    source: str  # page URL without the anchor; used to replace a page on re-ingest


@dataclass
class Hit:
    text: str
    title: str
    heading: str
    url: str
    score: float


def build_match_query(question: str, max_terms: int = 12) -> str:
    """Turn free text into a safe FTS5 query: quoted terms joined with OR."""
    terms: list[str] = []
    for raw in re.findall(r"[\w$.-]+", question.lower()):
        term = raw.strip(".-")
        if len(term) < 2 or term in STOPWORDS or term in terms:
            continue
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return " OR ".join('"' + t.replace('"', "") + '"' for t in terms)


class Store:
    def __init__(self, path: str | Path = "communityops.db"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ---- docs index ----
    def replace_source(self, source: str, title: str, chunks: list[Chunk]) -> None:
        """Insert a page's chunks, replacing any earlier copy of the same page."""
        with self.conn:
            self.conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
            self.conn.executemany(
                "INSERT INTO chunks (text, title, heading, url, source) VALUES (?, ?, ?, ?, ?)",
                [(c.text, c.title, c.heading, c.url, c.source) for c in chunks],
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO sources (url, title, fetched_at) VALUES (?, ?, ?)",
                (source, title, time.time()),
            )

    def clear_docs(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chunks")
            self.conn.execute("DELETE FROM sources")

    def doc_counts(self) -> tuple[int, int]:
        pages = self.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return pages, chunks

    def search(self, question: str, k: int = 6) -> list[Hit]:
        match = build_match_query(question)
        if not match:
            return []
        rows = self.conn.execute(
            # bm25 weights: text, title, heading (url and source are unindexed).
            "SELECT text, title, heading, url, bm25(chunks, 1.0, 2.0, 3.0) AS score "
            "FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?",
            (match, k),
        ).fetchall()
        return [Hit(r["text"], r["title"], r["heading"], r["url"], r["score"]) for r in rows]

    # ---- question log ----
    def log_question(self, **fields) -> int:
        fields.setdefault("ts", time.time())
        if isinstance(fields.get("citations"), (list, tuple)):
            fields["citations"] = json.dumps(list(fields["citations"]))
        if fields.get("status") not in STATUSES:
            raise ValueError(f"unknown status {fields.get('status')!r}")
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self.conn:
            cur = self.conn.execute(
                f"INSERT INTO questions ({cols}) VALUES ({marks})", tuple(fields.values())
            )
        return int(cur.lastrowid)

    def answers_since(self, since_ts: float) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM questions WHERE ts >= ? AND status != 'limited'", (since_ts,)
        ).fetchone()[0]

    def stats(self, since_ts: float) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n, AVG(latency_ms) AS ms, "
            "SUM(input_tokens) AS tin, SUM(output_tokens) AS tout "
            "FROM questions WHERE ts >= ? GROUP BY status",
            (since_ts,),
        ).fetchall()
        return {r["status"]: dict(r) for r in rows}

    def doc_gaps(self, since_ts: float, limit: int = 50) -> list[sqlite3.Row]:
        """Questions the docs could not answer: the weekly 'doc gaps' digest."""
        return self.conn.execute(
            "SELECT ts, chat_title, username, question, status, reason FROM questions "
            "WHERE ts >= ? AND status IN ('escalated', 'no_docs', 'refused', 'error') "
            "ORDER BY ts DESC LIMIT ?",
            (since_ts, limit),
        ).fetchall()
