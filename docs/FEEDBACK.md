# Product feedback

Written for the Build, Ship, Shape submission form. One section per tool used.

## Model Context Protocol and the MCP Python SDK 2.3.0

**What I used it for.** The DocDesk server: five tools over Streamable HTTP, the 2025-11-25 initialize handshake, `structuredContent` results, and the MCP Apps extension for the answer card. I also used the SDK's client in the test suite to drive full sessions against the real app.

**What worked well.**
- The built-in `Apps` extension made MCP Apps a few lines: `@apps.tool(resource_uri=...)` plus `add_html_resource(...)`. It even refuses to start when a tool points at a missing `ui://` resource, which caught a mistake early.
- `Context.headers` gives tools the HTTP headers, which made per-customer identity simple.
- The v1 import `mcp.server.fastmcp` fails with a message that names the new class and links the migration guide. That saved real time.
- DNS-rebinding protection turns on automatically for localhost binds.

**What needs work.**
- `StreamableHTTPSessionManager.run()` can only run once per instance, and entering the app lifespan in one task and leaving it in another raises an anyio cancel-scope error. Both are easy to hit from pytest fixtures. A testing helper or a documented in-process test pattern would help.
- Returning both speakable text and structured data needs a hand-built `CallToolResult`. A documented helper for "text for the model plus structured data for the UI" would make this common voice-assistant pattern easier.

**Onboarding.** Under an hour from install to a working Streamable HTTP server with tools.

**Would I build with it again?** Yes. It is the cleanest way to expose a service to agentic hosts.

## Alexa+ (add-on path via MCP)

**What I used it for.** The target platform. DocDesk is shaped as an Alexa+ add-on: short spoken replies, per-customer memory, cards for screen devices.

**What worked well.**
- Choosing the open MCP standard means one server works with any MCP host. The same DocDesk server served the browser simulator, the official Python client and a Strands agent without changes.
- The hackathon FAQ was clear that the gated add-on tooling is not available and that a web MCP client is an acceptable demo path.

**What needs work.**
- There is no way for hackathon builders to see an MCP server inside real Alexa+, even in a sandbox. A public Alexa+ add-on simulator would let builders test the real host's tool selection and voice rendering.
- There is no public description of how Alexa+ passes the linked customer's identity to a self-hosted MCP server. I used a custom header as a stand-in. A documented identity and account-linking contract for MCP add-ons is the most important missing piece for stateful add-ons.
- It is unclear whether Alexa+ on Echo Show devices renders MCP Apps (`ui://` resources) or uses its own card format. Builders cannot design screens without knowing this.

**Onboarding.** Fast, because the path is plain MCP. The add-on-specific docs could not be used.

**Would I build with it again?** Yes, if the identity contract and a sandbox host become available.

## Strands Agents SDK 1.62 (AWS Builder mini challenge)

**What I used it for.** A second host (`hosts/strands/host.py`) that connects to DocDesk as an MCP client, loads its tools, and either lets an agent on Amazon Bedrock (Nova Pro by default) or Anthropic choose the tool, or calls the tool directly when no model credentials are present.

**What worked well.**
- `MCPClient(url=..., headers=...)` connects to a Streamable HTTP server in one line, with custom headers for identity.
- `agent.tool.<name>(...)` calls an MCP tool directly without a model. That let me exercise the full MCP round trip offline.
- The client in Strands (MCP SDK 2.1.1) interoperated with the DocDesk server (MCP SDK 2.3.0) with no changes.

**What needs work.**
- `strands-agents` requires `mcp<2.2`, and its `anthropic` extra requires `anthropic<1.0`. A project whose server uses MCP SDK 2.3 and Anthropic SDK 1.x cannot install Strands in the same environment. I had to give the Strands host its own virtual environment. Wider version ranges, or a lighter "MCP client only" install, would fix this.

**Onboarding.** About 20 minutes, most of it spent on the dependency conflict.

**Would I build with it again?** Yes. The MCP integration is the best I have used in an agent framework.

## Amazon Bedrock and AWS credits

**What I used it for.** The Strands host's default model path (Amazon Nova Pro on Bedrock).

**What needs work.** The hackathon's $150 AWS promotional credits ran out on 7 October, before many builders started. I could not run the Bedrock path live, so it is written and documented but not demonstrated. More credits, or a small free Bedrock allowance for registered hackathon participants, would let more entries show AWS working end to end.

## Fire TV (Vega SDK), evaluated and not used

I first considered the Fire TV track. The Vega SDK and its virtual device support only macOS and Ubuntu, and the docs say Windows and WSL are not supported. On a Windows machine that ruled the track out. Windows support, or a hosted Vega virtual device, would open Fire TV to many more builders.
