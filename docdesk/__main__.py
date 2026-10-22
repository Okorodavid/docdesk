"""Command line: python -m docdesk <serve|ask|tickets|gaps|reset> ..."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def cmd_serve(args, settings) -> int:
    import uvicorn

    from .server import build_app

    if args.port:
        settings.port = args.port
    app, desk = build_app(settings)
    pages, chunks = desk.store.doc_counts()
    print(f"DocDesk for {settings.brand}")
    print(f"  answers:   {desk.mode}")
    print(f"  docs:      {pages} pages, {chunks} sections indexed")
    print(f"  MCP:       {settings.base_url}/mcp  (Streamable HTTP)")
    print(f"  simulator: {settings.base_url}/")
    print(f"  console:   {settings.base_url}/console")
    print(f"  staff token (for MCP clients outside this machine): {settings.staff_token}")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
    return 0


def _desk(settings):
    from .server import index_docs
    from .service import DocDesk

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    desk = DocDesk(settings)
    index_docs(desk, settings)
    return desk


def cmd_ask(args, settings) -> int:
    desk = _desk(settings)
    outcome = asyncio.run(desk.ask(args.customer, " ".join(args.question)))
    print(outcome.speech)
    print(json.dumps(outcome.to_dict(), indent=2) if args.json else f"\n[{outcome.status}, {desk.mode}]")
    return 0


def cmd_tickets(args, settings) -> int:
    desk = _desk(settings)
    for t in desk.memory.all_tickets():
        print(f"#{t.id:<4} {t.status:<18} {t.customer_id:<12} {t.question}")
        if t.resolution:
            print(f"      -> {t.resolution}")
    return 0


def cmd_gaps(args, settings) -> int:
    print(json.dumps(_desk(settings).gaps_report(days=args.days), indent=2))
    return 0


def cmd_reset(args, settings) -> int:
    from .server import reset_demo

    reset_demo(_desk(settings), settings)
    print("Demo reset: tickets, memory, question log and staff articles cleared; docs re-indexed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    from .config import load_settings

    p = argparse.ArgumentParser(prog="docdesk", description="DocDesk: a help-centre add-on for Alexa+")
    p.add_argument("--env", default=".env", help="path to a .env file (default: .env)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("serve", help="run the MCP server, simulator and console")
    ps.add_argument("--port", type=int)

    pa = sub.add_parser("ask", help="ask one question from the terminal")
    pa.add_argument("question", nargs="+")
    pa.add_argument("--customer", default="cli")
    pa.add_argument("--json", action="store_true")

    sub.add_parser("tickets", help="list all tickets")
    pg = sub.add_parser("gaps", help="doc gaps report")
    pg.add_argument("--days", type=float, default=7)
    sub.add_parser("reset", help="clear tickets, memory and staff articles for a fresh demo")

    args = p.parse_args(argv)
    settings = load_settings(args.env)
    handler = {"serve": cmd_serve, "ask": cmd_ask, "tickets": cmd_tickets, "gaps": cmd_gaps,
               "reset": cmd_reset}[args.cmd]
    return handler(args, settings)


if __name__ == "__main__":
    sys.exit(main())
