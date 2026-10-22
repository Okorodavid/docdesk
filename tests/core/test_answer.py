import anthropic
import httpx2

from communityops.answer import ANSWER_SCHEMA, ESCALATED_REPLY, NO_DOCS_REPLY, Answerer, build_request, decide
from communityops.config import Settings
from communityops.store import Hit
from .conftest import PAGE_URL, FakeClient, fake_response

HITS = [
    Hit("Withdrawals take 7 days.", "Bridge FAQ", "Withdrawals", f"{PAGE_URL}#withdrawal-time", -3.0),
    Hit("There is no bridge fee.", "Bridge FAQ", "Fees", f"{PAGE_URL}#fees", -2.0),
]


def test_request_shape_for_opus_includes_fallbacks_and_schema(settings):
    req = build_request(settings, "How long?", HITS)
    assert req["model"] == "claude-opus-5-5"
    assert req["betas"] == ["server-side-fallback-2026-07-01"] and req["fallbacks"] == "default"
    assert req["output_config"]["format"] == {"type": "json_schema", "schema": ANSWER_SCHEMA}
    assert req["output_config"]["effort"] == "medium"
    assert "thinking" not in req  # Opus 5.5 rejects disabled thinking; adaptive is the default
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Example Protocol" in req["system"][0]["text"]
    user = req["messages"][0]["content"]
    assert '<excerpt number="1" source="Bridge FAQ / Withdrawals">' in user and "<question>\nHow long?" in user


def test_no_fallbacks_for_haiku():
    req = build_request(Settings(model="claude-haiku-5-5"), "q", HITS)
    assert "fallbacks" not in req and "betas" not in req


def test_schema_is_strict():
    assert ANSWER_SCHEMA["additionalProperties"] is False
    assert set(ANSWER_SCHEMA["required"]) == set(ANSWER_SCHEMA["properties"])


def test_decide_answers_with_sources():
    r = decide("q", {"answerable": True, "answer": "It takes 7 days.", "citations": [1, 1, 2],
                     "confidence": "high", "escalation_reason": ""}, HITS)
    assert r.status == "answered" and not r.escalate
    assert r.sources == [f"{PAGE_URL}#withdrawal-time", f"{PAGE_URL}#fees"]
    assert r.reply.startswith("It takes 7 days.") and r.reply.endswith(f"{PAGE_URL}#fees")


def test_decide_escalates_without_valid_citation():
    r = decide("q", {"answerable": True, "answer": "Trust me.", "citations": [7],
                     "confidence": "high", "escalation_reason": ""}, HITS)
    assert r.status == "escalated" and r.reason == "answer had no valid citation"
    assert r.reply == ESCALATED_REPLY


def test_decide_escalates_on_low_confidence_or_unanswerable():
    low = decide("q", {"answerable": True, "answer": "Maybe 7 days.", "citations": [1],
                       "confidence": "low", "escalation_reason": ""}, HITS)
    assert low.status == "escalated" and low.reason == "low confidence"
    no = decide("q", {"answerable": False, "answer": "Asked the team.", "citations": [],
                      "confidence": "low", "escalation_reason": "price prediction"}, HITS)
    assert no.status == "escalated" and no.reason == "price prediction"


async def test_answerer_happy_path(settings, indexed_store):
    client = FakeClient(fake_response({"answerable": True, "answer": "Withdrawals take 7 days.",
                                       "citations": [1], "confidence": "high", "escalation_reason": ""}))
    r = await Answerer(settings, indexed_store, client).answer("How long do withdrawals take?")
    assert r.status == "answered"
    assert r.input_tokens == 1800 and r.output_tokens == 120 and r.model == "claude-opus-5-5"
    assert len(client.calls) == 1


async def test_answerer_skips_api_when_no_docs_match(settings, indexed_store):
    client = FakeClient()
    r = await Answerer(settings, indexed_store, client).answer("zzzqqq xyzzy plugh?")
    assert r.status == "no_docs" and r.reply == NO_DOCS_REPLY and client.calls == []


async def test_answerer_handles_refusal_truncation_and_bad_json(settings, indexed_store):
    for response, status in [
        (fake_response(stop_reason="refusal", text=""), "refused"),
        (fake_response(stop_reason="max_tokens", text='{"answerable": tr'), "error"),
        (fake_response(text="not json"), "error"),
    ]:
        r = await Answerer(settings, indexed_store, FakeClient(response)).answer("bridge fee?")
        assert r.status == status and r.escalate and r.reply == ESCALATED_REPLY


async def test_answerer_handles_api_errors(settings, indexed_store):
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    r = await Answerer(settings, indexed_store, FakeClient(error=err)).answer("bridge fee?")
    assert r.status == "error" and r.reason.startswith("connection error")
