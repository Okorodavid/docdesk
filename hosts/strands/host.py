"""A second Alexa+-style host built on the Strands Agents SDK (AWS).

It connects to a running DocDesk server as an MCP client over Streamable HTTP, loads the
DocDesk tools, and handles one customer utterance:

- Amazon Bedrock model (when AWS credentials are configured): the agent decides which
  DocDesk tool to call, like Alexa+ would. Default model: Amazon Nova Pro.
- Anthropic model (when ANTHROPIC_API_KEY is set and AWS is not).
- No credentials: the host routes the utterance with DocDesk's offline rules and calls the
  MCP tool directly through Strands (agent.tool.<name>), so the MCP round trip still runs.

Runs in its own virtual environment because Strands pins an older MCP SDK than the server.

    python hosts/strands/host.py --customer ada "Alexa, ask Brightline how do I restart my router?"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # for docdesk.planner (standard library only)

from strands import Agent  # noqa: E402
from strands.tools.mcp import MCPClient  # noqa: E402

from docdesk.planner import plan_rules  # noqa: E402

SYSTEM = (
    "You are a voice assistant host. The customer is talking to the {brand} support add-on. "
    "Call exactly one of the add-on's tools for what they said, then repeat the tool's text reply "
    "to the customer word for word. Do not add anything of your own."
)


def pick_model():
    """Bedrock if AWS credentials resolve, else Anthropic if a key is set, else None."""
    try:
        import boto3

        if boto3.Session().get_credentials() is not None:
            from strands.models import BedrockModel

            model_id = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0")
            region = os.environ.get("AWS_REGION", "us-east-1")
            return BedrockModel(model_id=model_id, region_name=region, temperature=0.2), f"Amazon Bedrock ({model_id})"
    except Exception:
        pass
    if os.environ.get("ANTHROPIC_API_KEY"):
        from strands.models.anthropic import AnthropicModel

        model_id = os.environ.get("STRANDS_ANTHROPIC_MODEL", "claude-haiku-5-5")
        return AnthropicModel(model_id=model_id, max_tokens=1024), f"Anthropic ({model_id})"
    return None, "none (direct MCP tool call)"


def text_of(result) -> str:
    content = result.get("content", []) if isinstance(result, dict) else []
    return " ".join(c["text"] for c in content if isinstance(c, dict) and "text" in c)


def run(utterance: str, url: str, customer: str, brand: str, staff_token: str | None) -> int:
    headers = {"X-DocDesk-Customer": customer}
    if staff_token:
        headers["X-DocDesk-Staff"] = staff_token
    client = MCPClient(url=url, headers=headers, application_name="docdesk-strands-host", startup_timeout=15)
    model, model_label = pick_model()
    with client:
        tools = client.list_tools_sync()
        names = [t.tool_name for t in tools]
        print(f"[strands] connected to {url} as {customer}; tools: {', '.join(names)}")
        print(f"[strands] model: {model_label}")
        if model is not None:
            agent = Agent(model=model, tools=tools, system_prompt=SYSTEM.format(brand=brand), callback_handler=None)
            reply = agent(utterance)
            calls = [
                block["toolUse"]["name"]
                for msg in agent.messages if msg["role"] == "assistant"
                for block in msg["content"] if "toolUse" in block
            ]
            print(f"[strands] agent called: {', '.join(calls) or 'no tool'}")
            print(str(reply).strip())
        else:
            agent = Agent(tools=tools, callback_handler=None)
            plan = plan_rules(utterance, brand)
            print(f"[strands] offline routing chose {plan['tool']} {json.dumps(plan['arguments'])}")
            result = getattr(agent.tool, plan["tool"])(record_direct_tool_call=False, **plan["arguments"])
            print(text_of(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Strands Agents host for DocDesk")
    p.add_argument("utterance", nargs="+")
    p.add_argument("--url", default=os.environ.get("DOCDESK_MCP_URL", "http://127.0.0.1:8765/mcp"))
    p.add_argument("--customer", default="strands-demo")
    p.add_argument("--brand", default=os.environ.get("BRAND_NAME", "Brightline Internet"))
    p.add_argument("--staff-token", default=os.environ.get("STAFF_TOKEN"))
    args = p.parse_args(argv)
    return run(" ".join(args.utterance), args.url, args.customer, args.brand, args.staff_token)


if __name__ == "__main__":
    sys.exit(main())
