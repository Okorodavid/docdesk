import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from communityops.config import Settings
from communityops.ingest import chunk_sections, html_to_sections
from communityops.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_URL = "https://docs.example.org/docs/bridge"


@pytest.fixture
def settings(tmp_path):
    return Settings(project_name="Example Protocol", db_path=tmp_path / "t.db", escalation_chat_id=-100555)


@pytest.fixture
def store(settings):
    s = Store(settings.db_path)
    yield s
    s.close()


@pytest.fixture
def indexed_store(store):
    title, sections = html_to_sections((FIXTURES / "bridge.html").read_text(encoding="utf-8"))
    store.replace_source(PAGE_URL, title, chunk_sections(sections, title, PAGE_URL))
    return store


def fake_response(payload=None, *, stop_reason="end_turn", text=None, model="claude-opus-5-5"):
    body = text if text is not None else json.dumps(payload)
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="general_harms") if stop_reason == "refusal" else None,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=body)],
        usage=SimpleNamespace(input_tokens=1800, output_tokens=120, cache_read_input_tokens=0),
        model=model,
    )


class FakeClient:
    """Stands in for anthropic.AsyncAnthropic: client.beta.messages.create(**kwargs)."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self._response = response
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response
