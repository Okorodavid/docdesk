"""DocDesk MCP server: Streamable HTTP at /mcp (MCP spec 2025-11-25 handshake), plus the
web pages for the Alexa+ simulator and the support-team console.

Customer identity comes from the X-DocDesk-Customer header. In a real Alexa+ deployment the
host supplies the linked account; the simulator sets the header for the chosen profile."""

from __future__ import annotations

import html
import logging
import re
import secrets
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from mcp.server.apps import Apps, client_supports_apps
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response

from communityops.ingest import slugify

from .cards import CARD_HTML, CARD_URI
from .config import ROOT, DocDeskSettings
from .planner import plan_claude, plan_rules
from .service import DocDesk

log = logging.getLogger("docdesk")
WEB = ROOT / "web"
CUSTOMER_HEADER = "x-docdesk-customer"
STAFF_HEADER = "x-docdesk-staff"
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.@-]")
LOOPBACK = {"127.0.0.1", "::1", "localhost"}

INSTRUCTIONS = """DocDesk is {brand}'s customer-support add-on. Use ask_support for any \
question about {brand}'s service, router, billing, outages or moving home; it answers only \
from {brand}'s help centre and opens a support ticket when the help centre does not cover \
the question. Use my_support_tickets when the customer asks about earlier issues or updates. \
Read the returned text to the customer as it is."""


def _result(speech: str, data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=speech)], structured_content=data)


def _customer(ctx: Context) -> str:
    headers = ctx.headers or {}
    raw = headers.get(CUSTOMER_HEADER) or headers.get(CUSTOMER_HEADER.title()) or "guest"
    return _SAFE_ID.sub("", raw)[:64] or "guest"


def _is_staff(token: str | None, settings: DocDeskSettings) -> bool:
    return bool(token) and secrets.compare_digest(token, settings.staff_token)


def build_server(settings: DocDeskSettings, desk: DocDesk | None = None) -> tuple[MCPServer, DocDesk]:
    desk = desk or DocDesk(settings)
    apps = Apps()
    apps.add_html_resource(
        CARD_URI, CARD_HTML, name="docdesk-card", title="DocDesk answer card",
        description="Shows the answer with its help-centre sources, open tickets and updates.",
        prefers_border=True,
    )

    @apps.tool(
        resource_uri=CARD_URI,
        name="ask_support",
        title=f"Ask {settings.brand} support",
        description=(
            f"Answer a customer's question about {settings.brand} from its official help centre, with the "
            "source sections. If the help centre does not cover it, opens (or adds to) a support ticket for a "
            "human and remembers it for this customer. Also delivers any answers to the customer's earlier "
            "tickets that arrived since they last spoke. On hosts that show MCP Apps, in-app directions come "
            "as a step-by-step walkthrough that highlights where to tap on the brand's app screen."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    )
    async def ask_support(
        question: Annotated[str, Field(description="The customer's question in their own words.")], ctx: Context
    ) -> CallToolResult:
        outcome = await desk.ask(_customer(ctx), question, screen=client_supports_apps(ctx))
        return _result(outcome.speech, outcome.to_dict())

    @apps.tool(
        resource_uri=CARD_URI,
        name="my_support_tickets",
        title="My support tickets",
        description=(
            "List this customer's open support tickets and tell them about any tickets that were answered "
            "since they last asked, by a new help article or by the support team."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def my_support_tickets(ctx: Context) -> CallToolResult:
        data = desk.my_tickets(_customer(ctx), screen=client_supports_apps(ctx))
        return _result(data["speech"], data)

    @apps.tool(
        resource_uri=CARD_URI,
        name="support_gaps_report",
        title="Doc gaps report (support team only)",
        description=(
            f"For {settings.brand}'s support team: what customers asked that the help centre could not answer, "
            "grouped by topic, with counts. Refuses for ordinary customers."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    async def support_gaps_report(
        ctx: Context, days: Annotated[int, Field(description="How many days back to look.", ge=1, le=90)] = 7
    ) -> CallToolResult:
        headers = ctx.headers or {}
        if not _is_staff(headers.get(STAFF_HEADER), settings):
            speech = f"Sorry, the doc gaps report is only for {settings.brand}'s support team."
            return _result(speech, {"speech": speech, "denied": True})
        data = desk.gaps_report(days=max(1, min(int(days), 90)))
        return _result(data["speech"], data)

    mcp = MCPServer(
        name="docdesk",
        title=f"DocDesk for {settings.brand}",
        description="Cited help-centre answers, support tickets that persist across sessions, and doc-gap reports.",
        instructions=INSTRUCTIONS.format(brand=settings.brand),
        version="1.0.0",
        extensions=[apps],
    )

    @mcp.tool(
        name="add_ticket_details",
        title="Add details to a ticket",
        description="Add more information from the customer to one of their open support tickets.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    )
    async def add_ticket_details(
        ticket_id: Annotated[int, Field(description="The ticket number the customer mentioned.")],
        details: Annotated[str, Field(description="What the customer wants to add, in their words.")],
        ctx: Context,
    ) -> CallToolResult:
        data = desk.add_details(_customer(ctx), ticket_id, details)
        return _result(data["speech"], data)

    @mcp.tool(
        name="close_ticket",
        title="Close a ticket",
        description="Close one of the customer's support tickets when they say the problem is sorted.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def close_ticket(
        ticket_id: Annotated[int, Field(description="The ticket number to close.")], ctx: Context
    ) -> CallToolResult:
        data = desk.close_ticket(_customer(ctx), ticket_id)
        return _result(data["speech"], data)

    _add_routes(mcp, desk, settings)
    return mcp, desk


# ------------------------------------------------------------------ web routes

def _page(name: str, request: Request, settings: DocDeskSettings) -> Response:
    text = (WEB / name).read_text(encoding="utf-8")
    # The staff token is only handed to pages opened from this machine.
    # Behind a proxy every request looks local, so this also requires a loopback bind.
    client = request.client.host if request.client else ""
    token = settings.staff_token if client in LOOPBACK and settings.host in LOOPBACK else ""
    text = text.replace("__STAFF_TOKEN__", token).replace("__BRAND__", html.escape(settings.brand))
    return HTMLResponse(text, headers={"Cache-Control": "no-store"})


def _markdown_page(path: Path, brand: str) -> str:
    """Tiny Markdown renderer for the demo help centre: headings with anchors, paragraphs, lists."""
    out, para, items = [], [], []

    def flush():
        if para:
            out.append(f"<p>{html.escape(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if m:
            flush()
            level, heading = len(m.group(1)), m.group(2)
            out.append(f'<h{level} id="{slugify(heading)}">{html.escape(heading)}</h{level}>')
        elif re.match(r"^\s*[-*]\s+", line):
            if para:
                flush()
            items.append(re.sub(r"^\s*[-*]\s+", "", line))
        elif line.strip():
            para.append(line.strip())
        else:
            flush()
    flush()
    return (
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(brand)} help centre</title>"
        "<style>body{font:16px/1.55 system-ui,sans-serif;max-width:680px;margin:40px auto;padding:0 16px;color:#14212b}"
        "h1{font-size:28px}h2{margin-top:32px}:target{background:#fff3c4}"
        "@media(prefers-color-scheme:dark){body{background:#101820;color:#e7eef3}:target{background:#4a3b00}}</style>"
        f"<p style='color:#5b6b78'>{html.escape(brand)} help centre (demo)</p>" + "".join(out)
    )


def _add_routes(mcp: MCPServer, desk: DocDesk, settings: DocDeskSettings) -> None:
    help_dirs = {"help": settings.demo_docs_dir, "help/new": settings.articles_dir}

    def staff_only(request: Request) -> Response | None:
        if not _is_staff(request.headers.get(STAFF_HEADER), settings):
            return JSONResponse({"error": "staff token required"}, status_code=401)
        return None

    @mcp.custom_route("/", methods=["GET"])
    async def simulator(request: Request) -> Response:
        return _page("index.html", request, settings)

    @mcp.custom_route("/console", methods=["GET"])
    async def console(request: Request) -> Response:
        return _page("console.html", request, settings)

    @mcp.custom_route("/static/{name}", methods=["GET"])
    async def static(request: Request) -> Response:
        name = request.path_params["name"]
        path = (WEB / name).resolve()
        if path.parent != WEB.resolve() or not path.is_file():
            return Response(status_code=404)
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    async def help_page(request: Request, base: str) -> Response:
        name = request.path_params["name"]
        folder = help_dirs[base]
        path = (folder / name).resolve()
        if not str(folder) or path.parent != folder.resolve() or path.suffix != ".md" or not path.is_file():
            return Response("Not found", status_code=404)
        return HTMLResponse(_markdown_page(path, settings.brand))

    @mcp.custom_route("/help/{name}", methods=["GET"])
    async def help_doc(request: Request) -> Response:
        return await help_page(request, "help")

    @mcp.custom_route("/help/new/{name}", methods=["GET"])
    async def help_new(request: Request) -> Response:
        return await help_page(request, "help/new")

    @mcp.custom_route("/healthz", methods=["GET"])
    async def health(request: Request) -> Response:
        pages, chunks = desk.store.doc_counts()
        return JSONResponse({"ok": True, "pages": pages, "chunks": chunks, "answer_mode": desk.mode})

    @mcp.custom_route("/host/plan", methods=["POST"])
    async def host_plan(request: Request) -> Response:
        body = await request.json()
        utterance = str(body.get("utterance", ""))[:1000]
        tools = body.get("tools") or []
        planner = "rules"
        if body.get("planner") == "claude" and settings.has_api_key:
            try:
                plan = await plan_claude(utterance, tools, settings.brand, settings.planner_model)
                planner = f"claude ({settings.planner_model})"
            except Exception as exc:  # fall back rather than break the demo
                log.warning("Claude planner failed, using rules: %s", exc)
                plan = plan_rules(utterance, settings.brand)
        else:
            plan = plan_rules(utterance, settings.brand)
        return JSONResponse({**plan, "planner": planner})

    @mcp.custom_route("/api/state", methods=["GET"])
    async def state(request: Request) -> Response:
        pages, chunks = desk.store.doc_counts()
        return JSONResponse({
            "brand": settings.brand, "answer_mode": desk.mode, "claude_available": settings.has_api_key,
            "pages": pages, "chunks": chunks,
        })

    @mcp.custom_route("/api/tickets", methods=["GET"])
    async def tickets(request: Request) -> Response:
        if (denied := staff_only(request)) is not None:
            return denied
        return JSONResponse({"tickets": [t.to_dict() for t in desk.memory.all_tickets()]})

    @mcp.custom_route("/api/tickets/{ticket_id:int}/reply", methods=["POST"])
    async def reply(request: Request) -> Response:
        if (denied := staff_only(request)) is not None:
            return denied
        body = await request.json()
        text = str(body.get("text", "")).strip()
        if not text:
            return JSONResponse({"error": "reply text is empty"}, status_code=400)
        t = desk.agent_reply(request.path_params["ticket_id"], text[:2000], str(body.get("agent", "support"))[:40])
        if t is None:
            return JSONResponse({"error": "no such ticket"}, status_code=404)
        return JSONResponse({"ticket": t.to_dict()})

    @mcp.custom_route("/api/articles", methods=["POST"])
    async def articles(request: Request) -> Response:
        if (denied := staff_only(request)) is not None:
            return denied
        body = await request.json()
        title = str(body.get("title", "")).strip()[:120]
        text = str(body.get("body", "")).strip()[:20000]
        if not title or not text:
            return JSONResponse({"error": "title and body are required"}, status_code=400)
        heading = str(body.get("heading", "")).strip()[:120] or title
        markdown = f"# {title}\n\n## {heading}\n\n{text}\n"
        desk.add_article(settings.articles_dir, f"{settings.base_url}/help/new", title, markdown)
        resolved = await desk.recheck_open_tickets()
        return JSONResponse({"indexed": title, "resolved": [t.to_dict() for t in resolved]})

    @mcp.custom_route("/api/recheck", methods=["POST"])
    async def recheck(request: Request) -> Response:
        if (denied := staff_only(request)) is not None:
            return denied
        resolved = await desk.recheck_open_tickets()
        return JSONResponse({"resolved": [t.to_dict() for t in resolved]})

    @mcp.custom_route("/api/gaps", methods=["GET"])
    async def gaps(request: Request) -> Response:
        if (denied := staff_only(request)) is not None:
            return denied
        return JSONResponse(desk.gaps_report(days=float(request.query_params.get("days", 7))))

    @mcp.custom_route("/api/reset", methods=["POST"])
    async def reset(request: Request) -> Response:
        if (denied := staff_only(request)) is not None:
            return denied
        reset_demo(desk, settings)
        return JSONResponse({"ok": True})


def index_docs(desk: DocDesk, settings: DocDeskSettings) -> tuple[int, int]:
    pages = chunks = 0
    if str(settings.demo_docs_dir) and settings.demo_docs_dir.is_dir():
        p, c = desk.ingest_dir(settings.demo_docs_dir, f"{settings.base_url}/help")
        pages, chunks = pages + p, chunks + c
    if settings.articles_dir.is_dir():
        p, c = desk.ingest_dir(settings.articles_dir, f"{settings.base_url}/help/new")
        pages, chunks = pages + p, chunks + c
    return pages, chunks


def reset_demo(desk: DocDesk, settings: DocDeskSettings) -> None:
    """Wipe tickets, conversation memory, the question log and staff-written articles."""
    with desk.store.conn:
        for table in ("tickets", "turns", "customers", "questions"):
            desk.store.conn.execute(f"DELETE FROM {table}")
        desk.store.conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('tickets', 'turns', 'questions')"
        )
    if settings.articles_dir.is_dir():
        for f in settings.articles_dir.glob("*.md"):
            f.unlink()
    desk.store.clear_docs()
    index_docs(desk, settings)


def build_app(settings: DocDeskSettings, desk: DocDesk | None = None):
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    mcp, desk = build_server(settings, desk)
    index_docs(desk, settings)
    if settings.host in LOOPBACK:
        security = None  # the SDK turns on DNS-rebinding protection for localhost itself
    else:
        hosts = [h.strip() for h in (__import__("os").environ.get("ALLOWED_HOSTS") or "").split(",") if h.strip()]
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=bool(hosts),
            allowed_hosts=hosts, allowed_origins=[f"https://{h}" for h in hosts],
        )
    app = mcp.streamable_http_app(host=settings.host, transport_security=security)
    return app, desk
