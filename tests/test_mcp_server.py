"""Drive the real Streamable HTTP app with the official MCP client, in process."""

import contextlib
import json

import httpx2
import pytest

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from docdesk.planner import clean_utterance, plan_rules
from docdesk.server import build_app

APPS = {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}


@contextlib.asynccontextmanager
async def running(settings):
    app, desk = build_app(settings)
    async with app.router.lifespan_context(app):
        yield app
    desk.store.close()


class Conn:
    def __init__(self, app, headers):
        self.app, self.headers = app, headers

    async def __aenter__(self):
        self.http = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=self.app), base_url="http://127.0.0.1:8765", headers=self.headers
        )
        self._streams = streamable_http_client("http://127.0.0.1:8765/mcp", http_client=self.http)
        streams = await self._streams.__aenter__()
        self.session = ClientSession(streams[0], streams[1], extensions=APPS)
        await self.session.__aenter__()
        self.init = await self.session.initialize()
        return self

    async def __aexit__(self, *exc):
        await self.session.__aexit__(*exc)
        await self._streams.__aexit__(*exc)
        await self.http.aclose()

    async def call(self, name, args=None):
        r = await self.session.call_tool(name, args or {})
        return " ".join(c.text for c in r.content if c.type == "text"), r.structured_content


async def test_handshake_tools_and_card(settings):
    async with running(settings) as app:
        async with Conn(app, {"X-DocDesk-Customer": "ada"}) as c:
            assert c.init.protocol_version == "2025-11-25"
            tools = {t.name: t for t in (await c.session.list_tools()).tools}
            assert set(tools) == {"ask_support", "my_support_tickets", "support_gaps_report", "add_ticket_details", "close_ticket"}
            assert tools["ask_support"].meta["ui"]["resourceUri"] == "ui://docdesk/card.html"
            assert tools["ask_support"].input_schema["required"] == ["question"]
            card = await c.session.read_resource("ui://docdesk/card.html")
            assert card.contents[0].mime_type == "text/html;profile=mcp-app"
            assert "ui/notifications/tool-result" in card.contents[0].text


async def test_customer_flow_over_mcp(settings):
    async with running(settings) as app:
        async with Conn(app, {"X-DocDesk-Customer": "ada"}) as c:
            text, data = await c.call("ask_support", {"question": "How do I restart my router?"})
            assert data["status"] == "answered" and "unplug" in text
            text, data = await c.call("ask_support", {"question": "Can I pay with mobile money?"})
            assert data["status"] == "ticket_opened"
            ticket_id = data["ticket"]["id"]
            text, data = await c.call("add_ticket_details", {"ticket_id": ticket_id, "details": "I use OPay"})
            assert data["ok"] is True
        async with Conn(app, {"X-DocDesk-Customer": "tunde"}) as c:
            text, data = await c.call("my_support_tickets")
            assert data["open"] == [] and "don't have any" in text


async def test_gaps_report_is_staff_only(settings):
    async with running(settings) as app:
        async with Conn(app, {"X-DocDesk-Customer": "ada"}) as c:
            text, data = await c.call("support_gaps_report", {"days": 7})
            assert data == {"speech": text, "denied": True}
        async with Conn(app, {"X-DocDesk-Customer": "staff", "X-DocDesk-Staff": settings.staff_token}) as c:
            text, data = await c.call("support_gaps_report", {"days": 7})
            assert "topics" in data


async def test_staff_api_requires_token_and_article_resolves_ticket(settings):
    async with running(settings) as app:
        async with Conn(app, {"X-DocDesk-Customer": "ada"}) as c:
            _, data = await c.call("ask_support", {"question": "Can I pay with mobile money?"})
            ticket_id = data["ticket"]["id"]
            r = await c.http.get("/api/tickets")
            assert r.status_code == 401
            r = await c.http.post("/api/articles", headers={"X-DocDesk-Staff": settings.staff_token}, content=json.dumps({
                "title": "Payment methods", "heading": "Pay with mobile money",
                "body": "You can pay your Brightline bill with mobile money in the app under Billing."}))
            assert r.status_code == 200
            assert [t["id"] for t in r.json()["resolved"]] == [ticket_id]
            text, data = await c.call("my_support_tickets")
            assert data["updates"][0]["ticket_id"] == ticket_id and "Good news" in text
            r = await c.http.get("/help/new/payment-methods.md")
            assert r.status_code == 200 and 'id="pay-with-mobile-money"' in r.text


async def test_static_and_help_routes_block_path_tricks(settings):
    async with running(settings) as app:
        async with Conn(app, {}) as c:
            assert (await c.http.get("/static/app.js")).status_code == 200
            assert (await c.http.get("/static/..%2Fdocdesk%2Fconfig.py")).status_code == 404
            assert (await c.http.get("/help/..%2F..%2Fdocdesk%2Fconfig.py")).status_code == 404


def test_planner_rules():
    assert clean_utterance("Alexa, ask Brightline how do I restart my router?") == "how do I restart my router?"
    assert clean_utterance("alexa ask brightline internet whether there is a late fee") == "there is a late fee"
    assert clean_utterance("Is there a late fee?") == "Is there a late fee?"
    assert plan_rules("Alexa, ask Brightline about my tickets")["tool"] == "my_support_tickets"
    assert plan_rules("any updates on my tickets?")["tool"] == "my_support_tickets"
    assert plan_rules("add to ticket 3 that I use OPay") == {
        "tool": "add_ticket_details", "arguments": {"ticket_id": 3, "details": "I use OPay"}}
    assert plan_rules("close ticket 4")["arguments"] == {"ticket_id": 4}
    assert plan_rules("show me the doc gaps report for the last 14 days")["arguments"] == {"days": 14}
    assert plan_rules("Alexa, ask Brightline what customers are asking that our docs don't cover")["tool"] == "support_gaps_report"
    assert plan_rules("is there a late fee?") == {"tool": "ask_support", "arguments": {"question": "is there a late fee?"}}
