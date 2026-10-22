# Devpost submission: copy-paste text

## Project name

DocDesk: your help centre, inside Alexa+

## Tagline (short)

Brands plug in their help centre. Customers ask Alexa+ and get cited answers, tickets that remember them, and good news when the docs catch up.

## Tracks

- Primary track: **Alexa+**
- Mini challenges: **AWS Builder**, **Open Source**

## Text description

**The problem.** When customers get stuck, they dig through help websites, wait hours for an agent, or get a confident wrong answer from a chatbot. Brands pay to answer the same questions again and again, and nobody can see which questions the help centre fails to answer.

**What DocDesk does.** DocDesk is a self-hosted MCP server that turns any brand's help centre into an Alexa+ add-on.

- It answers only from the brand's own help articles, in short spoken sentences, and shows the exact source section on screen. An answer without a valid source is never spoken.
- When the help centre does not cover a question, it opens a support ticket instead of guessing. Follow-ups on the same topic join the existing ticket.
- It remembers each customer across sessions. "Any news on my tickets?" works days later, and customers only ever see their own tickets.
- It closes the loop on its own. When the support team publishes a new article, DocDesk re-checks every open ticket against it, resolves the ones it now answers, and tells each customer the next time they talk to Alexa: "Good news about ticket 1..."
- It shows the brand a staff-only report of what customers asked that the docs could not answer, grouped by topic, so the team knows what to write next.

**How it works.**

- **MCP server:** Python, MCP SDK 2.3.0, Streamable HTTP at `/mcp`, MCP spec 2025-11-25 handshake, stateful sessions. Five tools: `ask_support`, `my_support_tickets`, `add_ticket_details`, `close_ticket`, and the staff-only `support_gaps_report`.
- **MCP Apps:** the answer, ticket and gaps views are an MCP Apps card (`ui://docdesk/card.html`) bound to the tools. Every tool also returns complete spoken text, so voice-only hosts lose nothing.
- **Retrieval and answers:** a SQLite FTS5 index of the help centre, split by heading so citations deep-link to a section. With an API key, Claude writes the spoken answer from the retrieved sections only, as structured output with citations, and anything uncited or low-confidence becomes a ticket. Without a key, an offline extractive mode quotes the best-matching section, so the whole demo runs with no credentials.
- **Memory:** tickets, per-customer turns and a question log in the same SQLite file.
- **Alexa+ simulator:** the hackathon FAQ confirms that the Alexa+ add-on tools are partner-only, so the demo uses a web page that is a real MCP client (initialize, tools/list, tools/call over Streamable HTTP) and a real MCP Apps host (it reads the `ui://` resource and renders it in a sandboxed iframe). A "host brain" picks the tool, either by rules or by letting Claude choose from the live `tools/list`. The inspector panel shows every JSON-RPC message.
- **Strands Agents host (AWS Builder):** a second host built on the Strands Agents SDK connects to DocDesk as an MCP client over Streamable HTTP. With AWS credentials, a Strands agent on Amazon Bedrock (Amazon Nova Pro by default) chooses the DocDesk tool. Without credentials it calls the MCP tools directly through Strands.
- **Tests:** 41 tests, including full MCP sessions against the real Streamable HTTP app with the official MCP client.

**What is real and what is simulated.** The MCP server, tools, MCP App, answering, tickets, memory and automatic re-check are real and tested. Alexa+ itself is simulated, because add-on tooling is partner-only. Customer identity is a header that stands in for the linked Alexa account. The Bedrock and Claude model paths are written but were not run live during the build, because the hackathon AWS credits had run out and no keys were available; the offline paths were run. The demo brand, Brightline Internet, is fictional.

**Built during the hackathon.** The retrieval and cited-answer core (`communityops/`) comes from my Telegram support bot, written on 21 October 2026, inside the submission window. Everything in `docdesk/`, `web/` and `hosts/` was built on 22 October 2026 for this submission: the MCP server, tools, MCP App card, ticket memory, automatic re-check, gaps report, simulator, console, Strands host and tests.

## Open Source mini challenge fields

- Contribution URL: https://github.com/Okorodavid/mcp-lite
- Project repository URL: https://github.com/Okorodavid/docdesk
- GitHub username: Okorodavid
- Description: **mcp-lite** is a new MIT-licensed, dependency-free MCP client for the browser over Streamable HTTP, plus a minimal MCP Apps host. The client speaks the 2025-11-25 handshake, keeps `Mcp-Session-Id`, sends `MCP-Protocol-Version`, and reads both JSON and SSE responses, so a plain web page can talk to any Streamable HTTP MCP server without a build step. The Apps host reads a tool's `ui://` resource, renders it in a sandboxed iframe, and implements the postMessage handshake (`ui/initialize`, tool-input, tool-result, size-changed, open-link). It matters because most MCP clients are Node or Python libraries; mcp-lite lets anyone build a browser-based MCP host or simulator in one script tag. It powers DocDesk's Alexa+ simulator and includes tests and an example.

## AWS Builder answer (put this in Product Feedback too)

AWS services used: the **Strands Agents SDK** (`hosts/strands/host.py`) as an MCP host that consumes the DocDesk server over Streamable HTTP with `MCPClient`, and **Amazon Bedrock** (Amazon Nova Pro, via Strands `BedrockModel`) as the model that chooses which DocDesk tool to call when AWS credentials are present. Without credentials, the same Strands host calls DocDesk's MCP tools directly with `agent.tool.<name>()`, which was run during the build.

## Product feedback and friction log

Paste from `docs/FEEDBACK.md` and `docs/FRICTION_LOG.md`.

## Feature requests

| Request | Why it matters | Priority |
|---|---|---|
| Documented identity and account-linking contract for MCP add-ons | Stateful add-ons such as DocDesk need a stable per-customer ID from the host | Critical |
| Public Alexa+ add-on sandbox that accepts a Streamable HTTP URL | Builders cannot test real tool selection and voice rendering today | Critical |
| State whether Alexa+ renders MCP Apps on screen devices | Needed to design cards | Important |
| Proactive notification API for add-ons | DocDesk could tell a customer about a resolved ticket without waiting for them to speak | Important |
| Windows support or a hosted Vega virtual device | Opens Fire TV to Windows builders | Nice-to-have for this project |

## Checklist before you press Submit

- [ ] GitHub repo is public and the MIT license shows in the About section
- [ ] Demo video under 3 minutes, public on YouTube, English, no copyrighted music
- [ ] Video shows the MCP handshake and tool calls in the inspector, not only the chat
- [ ] Track: Alexa+. Mini challenges: AWS Builder and Open Source
- [ ] Open Source fields filled with the mcp-lite repo URL
- [ ] Product feedback pasted, including the AWS paragraph
- [ ] Friction log pasted
- [ ] Submitted before Friday 23 October, 12:00 PM PT (8:00 PM in Nigeria)
