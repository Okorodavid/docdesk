import pytest

from communityops.store import build_match_query
from .conftest import PAGE_URL


def test_search_ranks_the_right_section(indexed_store):
    hits = indexed_store.search("how long does a withdrawal take?")
    assert hits and hits[0].url == f"{PAGE_URL}#withdrawal-time"
    hits = indexed_store.search("bridge tx stuck pending")
    assert hits[0].url == f"{PAGE_URL}#stuck-transaction"


def test_match_query_is_safe_against_fts_syntax(indexed_store):
    nasty = 'fees" OR text:* NEAR( AND -bridge ^ * "unclosed'
    q = build_match_query(nasty)
    assert q.count('"') % 2 == 0
    indexed_store.search(nasty)  # must not raise sqlite3.OperationalError


def test_match_query_drops_stopwords_and_empty():
    assert build_match_query("how do I?") == ""
    assert build_match_query("Is the $EXA airdrop live?") == '"$exa" OR "airdrop" OR "live"'


def test_empty_query_returns_nothing(indexed_store):
    assert indexed_store.search("what is it?") == []


def test_question_log_and_reports(store):
    store.log_question(platform="telegram", question="q1", status="answered", citations=["https://a"], ts=1000.0)
    store.log_question(platform="telegram", question="q2", status="escalated", reason="low confidence", ts=1001.0)
    store.log_question(platform="telegram", question="q3", status="limited", ts=1002.0)
    assert store.answers_since(0) == 2
    stats = store.stats(0)
    assert stats["answered"]["n"] == 1 and stats["escalated"]["n"] == 1
    gaps = store.doc_gaps(0)
    assert [g["question"] for g in gaps] == ["q2"]
    with pytest.raises(ValueError):
        store.log_question(platform="telegram", question="q", status="bogus")
