# Friction log

Each entry: the task, the steps, what I expected and what happened, severity, the workaround, and a suggestion.

## 1. Testing a self-hosted MCP server inside Alexa+

- **Task:** See DocDesk's tools working in a real Alexa+ host.
- **Steps:** Read the Alexa+ add-on docs, then the hackathon FAQ.
- **Expected:** A sandbox or simulator where a self-hosted MCP server can be registered for testing.
- **Actual:** The Category SDK, MCP Toolkit, CLI and Web Simulator are limited to select partners. Some setup-guide pages do not say so, which the FAQ notes has caused confusion.
- **Severity:** High.
- **Workaround:** Built a browser simulator that is a real MCP client and MCP Apps host.
- **Suggestion:** Offer a public, rate-limited Alexa+ add-on simulator that accepts a Streamable HTTP URL, or mark every gated page clearly.

## 2. Getting the customer's identity in a stateful add-on

- **Task:** Keep tickets per customer across sessions.
- **Steps:** Looked for how Alexa+ tells an MCP add-on which customer is speaking.
- **Expected:** A documented header, token or account-linking flow.
- **Actual:** No public description.
- **Severity:** High for any stateful add-on.
- **Workaround:** An `X-DocDesk-Customer` header set by the host, isolated per customer in the server and covered by tests.
- **Suggestion:** Publish the identity and account-linking contract for MCP add-ons, ideally standard MCP authorization (OAuth) with a stable per-customer subject.

## 3. Rendering cards on screen devices

- **Task:** Show the answer's sources and the customer's tickets on Echo Show style devices.
- **Steps:** Built an MCP Apps card (`ui://docdesk/card.html`).
- **Expected:** Guidance on whether Alexa+ renders MCP Apps or another card format.
- **Actual:** No guidance found.
- **Severity:** Medium.
- **Workaround:** Every tool returns complete spoken text, so the card is optional. The simulator renders the card as an MCP Apps host.
- **Suggestion:** State which MCP Apps features Alexa+ supports on screen devices, and the size limits.

## 4. Installing Strands next to MCP SDK 2.3

- **Task:** Add a Strands Agents host for the AWS Builder mini challenge.
- **Steps:** Checked `strands-agents` 1.62.0 dependencies before installing into the server's environment.
- **Expected:** Compatible with the current MCP SDK.
- **Actual:** It requires `mcp<2.2`, and its `anthropic` extra requires `anthropic<1.0`. The server uses `mcp==2.3.0` and `anthropic` 1.17.
- **Severity:** Medium.
- **Workaround:** A separate virtual environment for the Strands host, which talks to the server only over MCP.
- **Suggestion:** Widen the version ranges, or ship an MCP-client-only install without model extras.

## 5. Session manager reuse in tests

- **Task:** Run full MCP sessions against the Streamable HTTP app in pytest.
- **Steps:** Entered the app lifespan per client connection, then from an async pytest fixture.
- **Expected:** Either pattern works.
- **Actual:** The first raised "StreamableHTTPSessionManager .run() can only be called once per instance". The second raised an anyio error about exiting a cancel scope in a different task.
- **Severity:** Low.
- **Workaround:** Start the app inside each test with an async context manager.
- **Suggestion:** Document an in-process testing pattern for Streamable HTTP servers in the MCP Python SDK.

## 6. AWS promotional credits

- **Task:** Run the Bedrock path of the Strands host live.
- **Steps:** Read the rules and resources pages for the $150 credit request.
- **Expected:** Credits available until the stated 21 October request deadline.
- **Actual:** An update on both pages says the credit codes ran out on 7 October.
- **Severity:** Medium.
- **Workaround:** The Bedrock path is written and documented; the offline direct-tool path is demonstrated.
- **Suggestion:** Size the credit pool to registrations, or give participants a small Bedrock allowance.

## 7. Fire TV development on Windows

- **Task:** Evaluate the Fire TV track.
- **Steps:** Read the Vega SDK install requirements.
- **Expected:** Windows support, or a hosted virtual device.
- **Actual:** macOS and Ubuntu only; Windows and WSL are not supported.
- **Severity:** High for Windows-only builders.
- **Workaround:** Chose the Alexa+ track.
- **Suggestion:** Support Windows, or offer a cloud Vega virtual device.
