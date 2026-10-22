# DocDesk: a help-centre add-on for Alexa+

DocDesk lets any brand put its help centre inside Alexa+. Customers ask a question out loud and get a short spoken answer taken only from the brand's own help articles, with the exact source section shown on screen. When the help centre does not cover the question, DocDesk opens a support ticket instead of guessing, remembers it for that customer, and tells them the answer the next time they talk to Alexa.

Built for the **Alexa+ track** of Build, Ship, Shape: Amazon Developer Hackathon 2026, with the **AWS Builder** mini challenge (Strands Agents SDK host, Amazon Bedrock) and the **Open Source** mini challenge ([mcp-lite](https://github.com/Okorodavid/mcp-lite)).

## The problem

When a customer is stuck ("my router light is orange", "can I pay with mobile money?"), today they:

- dig through a help website on their phone,
- wait hours for a support agent, or
- ask a chatbot that answers confidently and wrongly.

Brands pay for the same questions to be answered again and again, and nobody can see which questions the help centre fails to answer.

## What DocDesk does

1. **Answers only from the help centre.** Every answer cites the section it came from. If no section covers the question, it does not guess.
2. **Hands off to a human.** Unanswered questions become tickets for the support team. Similar follow-ups join the existing ticket instead of opening duplicates.
3. **Remembers each customer across sessions.** "Any news on my tickets?" works days later, and each customer only ever sees their own tickets.
4. **Closes the loop by itself.** When the support team publishes a new article, DocDesk re-checks every open ticket against it. Tickets the new article answers are resolved automatically, and the customer hears "Good news about ticket 2..." the next time they speak to Alexa.
5. **Shows the brand its doc gaps.** A staff-only report groups what customers asked that the docs could not answer, so the team knows which article to write next.

## Demo in two minutes

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m docdesk serve
```

Open these two pages side by side:

- `http://127.0.0.1:8765/` is the Alexa+ simulator.
- `http://127.0.0.1:8765/console` is the support-team console.

Then:

1. As **Ada**, click "how do I restart my router?". The answer is read aloud and the source card links to the exact help section.
2. Click "Can I pay my bill with mobile money?". The help centre does not cover it, so ticket 1 opens.
3. In the console, click **Fill example**, then **Publish and re-check tickets**. The console reports that the article answered ticket 1.
4. Back as Ada, ask anything ("Is there a late fee?"). Alexa first delivers the good news about ticket 1, then answers.
5. Switch to **Tunde**: he sees none of Ada's tickets. Switch to **Brightline team** and ask for the doc gaps report; customers get a polite refusal for the same request.

No API key is needed. Without one, DocDesk runs in offline mode: it only answers when one help section clearly covers the question, quoting that section's most relevant sentences. Set `ANTHROPIC_API_KEY` (see `.env.example`) and answers come from Claude, still restricted to the retrieved help sections, and the simulator can let Claude pick the tool like a real Alexa+ host.

The demo brand, Brightline Internet, is fictional. Its help centre lives in `demo/docs`. Run `python -m docdesk reset` to clear tickets and memory between demo takes.

## How it works

```
 Alexa+ host (simulated)                        DocDesk MCP server (Python, MCP SDK 2.3)
 ┌──────────────────────────┐   Streamable HTTP   ┌─────────────────────────────────────┐
 │ web simulator            │  POST /mcp          │ tools                               │
 │  - host brain: rules or  │ ──────────────────► │  ask_support         (MCP App card) │
 │    Claude picks a tool   │  initialize         │  my_support_tickets  (MCP App card) │
 │  - mcp-lite client       │  tools/list         │  add_ticket_details                 │
 │  - MCP Apps host renders │  tools/call         │  close_ticket                       │
 │    ui://docdesk/card     │  resources/read     │  support_gaps_report (staff only)   │
 └──────────────────────────┘                     │                                     │
 ┌──────────────────────────┐                     │ answerer: Claude or offline         │
 │ Strands Agents host      │ ──────────────────► │ SQLite: FTS5 docs index, tickets,   │
 │  Bedrock / Anthropic /   │                     │   per-customer memory, question log │
 │  direct tool calls       │                     └──────────────┬──────────────────────┘
 └──────────────────────────┘                                    │ REST (staff token)
                                                    support console: tickets, replies,
                                                    publish article, doc gaps, reset
```

**MCP surface**

| Item | Value |
|---|---|
| Endpoint | `POST /mcp`, Streamable HTTP, stateful sessions (`Mcp-Session-Id`) |
| Protocol | `2025-11-25` initialize handshake (MCP Python SDK 2.3.0 also speaks `2026-07-28`) |
| Tools | `ask_support`, `my_support_tickets`, `add_ticket_details`, `close_ticket`, `support_gaps_report` |
| MCP Apps | `ui://docdesk/card.html` (`text/html;profile=mcp-app`), bound to the first three customer tools |
| Results | Spoken text in `content`, plus `structuredContent` for cards |
| Customer identity | `X-DocDesk-Customer` header, standing in for the account the host has linked |
| Staff identity | `X-DocDesk-Staff` header carrying the staff token |

**Rules that keep it trustworthy**

- The model only sees the retrieved help sections and is told to mark anything else not answerable. An answer without a valid citation is never spoken; it becomes a ticket.
- Account-specific questions ("why is my bill higher?") are not answerable from a help centre, so they go to a human.
- Customers can only read, add to or close their own tickets. The gaps report needs the staff token.
- The voice prompt forbids asking customers to say passwords, PINs, card numbers or one-time codes.
- Question text and doc excerpts are treated as untrusted data in the prompt.

**Code map**

| Path | What it is |
|---|---|
| `docdesk/server.py` | MCP server, tools, MCP App resource, web and staff routes |
| `docdesk/service.py` | Answering, tickets, automatic re-check, gaps report |
| `docdesk/memory.py` | Tickets and per-customer conversation memory in SQLite |
| `docdesk/offline.py` | Keyless extractive answerer |
| `docdesk/planner.py` | Simulated host brain: rules, or Claude choosing from `tools/list` |
| `docdesk/cards.py` | The MCP App card |
| `communityops/` | Docs crawler, FTS5 index and cited-answer core, reused from the author's Telegram support bot |
| `web/` | Simulator, console, `mcp-client.js`, `apps-host.js` |
| `hosts/strands/host.py` | Strands Agents SDK host |
| `tests/` | 41 tests, including full MCP sessions against the real Streamable HTTP app |

## Strands Agents host (AWS Builder)

`hosts/strands/host.py` is a second host, built on the Strands Agents SDK. It connects to DocDesk as an MCP client over Streamable HTTP, loads the tools, and handles one utterance:

- With AWS credentials, a Strands agent on **Amazon Bedrock** (default `us.amazon.nova-pro-v1:0`) decides which DocDesk tool to call.
- With only `ANTHROPIC_API_KEY`, the same agent runs on Claude.
- With neither, it routes with DocDesk's offline rules and calls the MCP tool directly through Strands (`agent.tool.ask_support(...)`).

Strands pins an older MCP SDK, so it gets its own environment:

```bash
python -m venv .venv-strands
.venv-strands\Scripts\pip install -r hosts/strands/requirements.txt
.venv-strands\Scripts\python hosts/strands/host.py --customer ada "Alexa, ask Brightline how do I change my Wi-Fi password?"
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Real vs simulated

| Part | Status |
|---|---|
| MCP server, tools, Streamable HTTP, MCP App resource | Real. Tested with the official MCP Python client and with Strands. |
| Answering, tickets, memory, re-check, gaps report | Real. |
| Strands host | Real Strands MCP client. The Bedrock and Anthropic model paths are written but were not run live, because no credentials were available while building; the direct-call path was run. |
| Claude answerer | Inherited from the author's earlier bot, where it ran live. Not run live in this build, for the same reason. Offline mode was run. |
| Alexa+ | Simulated. Alexa+ add-on tooling is limited to select partners, as the hackathon FAQ explains, so the browser simulator acts as the host: it is a real MCP client and a real MCP Apps host. |
| Customer identity | Simulated with a header. A production add-on would take the linked account from the Alexa+ host. |
| Speech | Browser speech synthesis and recognition (Chrome/Edge). |

## Open source contribution

The simulator's browser MCP client and MCP Apps host are published separately as **[mcp-lite](https://github.com/Okorodavid/mcp-lite)** under the MIT license: a dependency-free MCP client for the browser over Streamable HTTP that reads both JSON and SSE responses, plus a minimal MCP Apps host for rendering `ui://` resources in a sandboxed iframe. It has its own tests and an example page.

## License

MIT. See `LICENSE`.
