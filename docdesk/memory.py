"""Per-customer memory: support tickets and conversation turns, in the same SQLite file
as the docs index. This is what lets DocDesk remember an open issue across sessions."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    question TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    resolution TEXT NOT NULL DEFAULT '',
    resolution_sources TEXT NOT NULL DEFAULT '[]',
    resolved_by TEXT NOT NULL DEFAULT '',
    notified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tickets_customer ON tickets(customer_id, status);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    ts REAL NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_customer ON turns(customer_id, ts);
"""

OPEN = "open"
ANSWERED_BY_DOCS = "answered_by_docs"  # a later docs update answered it automatically
RESOLVED_BY_AGENT = "resolved_by_agent"  # a human on the support team replied
CLOSED = "closed"  # the customer said it is sorted
TICKET_STATUSES = (OPEN, ANSWERED_BY_DOCS, RESOLVED_BY_AGENT, CLOSED)

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a", "an", "and", "are", "can", "do", "does", "for", "how", "i", "if", "in", "is", "it", "my",
    "of", "on", "or", "the", "to", "what", "when", "why", "with", "you", "your", "me", "still",
    "be", "was", "this", "that", "there", "have", "has", "get", "will", "please", "alexa",
}


def terms(text: str) -> set[str]:
    """Content words, cut to a 5-letter prefix so 'outages' and 'outage' match."""
    return {w[:5] for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


def similarity(a: str, b: str) -> float:
    """Overlap coefficient: shared words over the shorter question's words."""
    ta, tb = terms(a), terms(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def content_words(text: str) -> list[str]:
    """Full content words, for showing topics to people."""
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2]


@dataclass
class Ticket:
    id: int
    customer_id: str
    question: str
    details: str
    status: str
    reason: str
    created_at: float
    updated_at: float
    resolution: str
    resolution_sources: list[str] = field(default_factory=list)
    resolved_by: str = ""
    notified: bool = False

    @property
    def is_open(self) -> bool:
        return self.status == OPEN

    def to_dict(self) -> dict:
        return asdict(self)


def _ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        id=row["id"], customer_id=row["customer_id"], question=row["question"], details=row["details"],
        status=row["status"], reason=row["reason"], created_at=row["created_at"],
        updated_at=row["updated_at"], resolution=row["resolution"],
        resolution_sources=json.loads(row["resolution_sources"] or "[]"),
        resolved_by=row["resolved_by"], notified=bool(row["notified"]),
    )


class Memory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.executescript(SCHEMA)

    # ---- customers and turns ----
    def touch_customer(self, customer_id: str) -> bool:
        """Record a visit. Returns True for a first-time customer."""
        now = time.time()
        with self.conn:
            cur = self.conn.execute(
                "UPDATE customers SET last_seen = ? WHERE id = ?", (now, customer_id)
            )
            if cur.rowcount:
                return False
            self.conn.execute(
                "INSERT INTO customers (id, first_seen, last_seen) VALUES (?, ?, ?)", (customer_id, now, now)
            )
        return True

    def add_turn(self, customer_id: str, role: str, text: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO turns (customer_id, ts, role, text) VALUES (?, ?, ?, ?)",
                (customer_id, time.time(), role, text[:2000]),
            )

    def recent_turns(self, customer_id: str, limit: int = 6) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts, role, text FROM turns WHERE customer_id = ? ORDER BY id DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---- tickets ----
    def open_ticket(self, customer_id: str, question: str, reason: str) -> Ticket:
        now = time.time()
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO tickets (customer_id, question, status, reason, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (customer_id, question.strip(), OPEN, reason, now, now),
            )
        return self.get(int(cur.lastrowid))

    def get(self, ticket_id: int) -> Ticket | None:
        row = self.conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return _ticket(row) if row else None

    def find_similar_open(self, customer_id: str, question: str, threshold: float = 0.6) -> Ticket | None:
        best, best_score = None, threshold
        for t in self.for_customer(customer_id, statuses=(OPEN,)):
            score = similarity(question, t.question)
            if score >= best_score:
                best, best_score = t, score
        return best

    def add_details(self, ticket_id: int, details: str) -> Ticket | None:
        t = self.get(ticket_id)
        if t is None:
            return None
        combined = f"{t.details}\n{details.strip()}".strip()
        with self.conn:
            self.conn.execute(
                "UPDATE tickets SET details = ?, updated_at = ? WHERE id = ?", (combined, time.time(), ticket_id)
            )
        return self.get(ticket_id)

    def resolve(self, ticket_id: int, status: str, resolution: str, sources: list[str], by: str) -> Ticket | None:
        if status not in (ANSWERED_BY_DOCS, RESOLVED_BY_AGENT, CLOSED):
            raise ValueError(f"not a resolved status: {status!r}")
        with self.conn:
            self.conn.execute(
                "UPDATE tickets SET status = ?, resolution = ?, resolution_sources = ?, resolved_by = ?, "
                "notified = 0, updated_at = ? WHERE id = ?",
                (status, resolution.strip(), json.dumps(sources), by, time.time(), ticket_id),
            )
        return self.get(ticket_id)

    def mark_notified(self, ticket_ids: list[int]) -> None:
        if not ticket_ids:
            return
        marks = ",".join("?" for _ in ticket_ids)
        with self.conn:
            self.conn.execute(f"UPDATE tickets SET notified = 1 WHERE id IN ({marks})", ticket_ids)

    def for_customer(self, customer_id: str, statuses: tuple[str, ...] | None = None) -> list[Ticket]:
        sql = "SELECT * FROM tickets WHERE customer_id = ?"
        args: list = [customer_id]
        if statuses:
            sql += f" AND status IN ({','.join('?' for _ in statuses)})"
            args.extend(statuses)
        rows = self.conn.execute(sql + " ORDER BY id DESC", args).fetchall()
        return [_ticket(r) for r in rows]

    def unnotified_resolutions(self, customer_id: str) -> list[Ticket]:
        rows = self.conn.execute(
            "SELECT * FROM tickets WHERE customer_id = ? AND status IN (?, ?) AND notified = 0 ORDER BY id",
            (customer_id, ANSWERED_BY_DOCS, RESOLVED_BY_AGENT),
        ).fetchall()
        return [_ticket(r) for r in rows]

    def all_tickets(self, statuses: tuple[str, ...] | None = None, limit: int = 200) -> list[Ticket]:
        sql = "SELECT * FROM tickets"
        args: list = []
        if statuses:
            sql += f" WHERE status IN ({','.join('?' for _ in statuses)})"
            args.extend(statuses)
        rows = self.conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
        return [_ticket(r) for r in rows]
