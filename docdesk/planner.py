"""The simulated Alexa+ "host brain": turns what the customer said into one MCP tool call.

Real Alexa+ does this with its own model. Here there are two stand-ins:
- rules: keyword routing, free and offline.
- claude: a small Claude model chooses the tool from the live tools/list, like a real host.
The browser then performs the tools/call itself over MCP."""

from __future__ import annotations

import re
from typing import Any

def _wake(brand: str) -> re.Pattern:
    words = [re.escape(w) for w in brand.split()] or [r"\w+"]
    name = words[0] + "".join(rf"(?:\s+{w})?" for w in words[1:])
    return re.compile(
        rf"^\s*(?:hey\s+)?alexa[,.!]?\s*(?:(?:ask|tell|open)\s+(?:the\s+)?(?:{name}|\w+)\s+"
        rf"(?:(?:to|about|if|whether)\s+)?)?",
        re.I,
    )


def clean_utterance(text: str, brand: str = "Brightline Internet") -> str:
    """Drop the wake word and 'ask <brand>' so the add-on gets the question itself."""
    return _wake(brand).sub("", text).strip() or text.strip()


def plan_rules(utterance: str, brand: str = "Brightline Internet") -> dict[str, Any]:
    text = clean_utterance(utterance, brand)
    low = text.lower()
    m = re.search(r"\bticket\s*(?:number\s*)?#?(\d+)\b", low)
    ticket_id = int(m.group(1)) if m else None

    if re.search(r"\b(close|cancel)\b.*\bticket\b", low) and ticket_id:
        return {"tool": "close_ticket", "arguments": {"ticket_id": ticket_id}}
    if ticket_id and re.search(r"\b(add|also|tell them|update ticket|more detail)", low):
        details = re.sub(r"^.*?ticket\s*(?:number\s*)?#?\d+\s*(that|:|,)?\s*", "", text, flags=re.I).strip()
        return {"tool": "add_ticket_details", "arguments": {"ticket_id": ticket_id, "details": details or text}}
    if re.search(
        r"\b(my tickets?|open tickets?|ticket status|any (news|update|updates)|what('s| is| has) happen\w*|"
        r"heard back|follow(ed)? up|my (issue|issues|request|requests|complaint))\b", low
    ):
        return {"tool": "my_support_tickets", "arguments": {}}
    if re.search(
        r"\b(doc(s)? gaps?|gaps? report|what (are )?(customers|people) (are )?asking|unanswered questions|"
        r"(docs|help centre|help center) (don't|do not|doesn't|does not) cover)\b",
        low,
    ):
        days = re.search(r"\b(\d+)\s*days?\b", low)
        return {"tool": "support_gaps_report", "arguments": {"days": int(days.group(1)) if days else 7}}
    return {"tool": "ask_support", "arguments": {"question": text}}


PLANNER_SYSTEM = """You are the voice assistant's host. The customer is talking to the {brand} \
add-on. Choose exactly one of the add-on's tools for what they said and fill in its arguments. \
Pass the customer's question to ask_support in their own words, without the wake word. \
Use my_support_tickets when they ask about earlier issues, tickets, news or updates."""


async def plan_claude(utterance: str, tools: list[dict], brand: str, model: str, client=None) -> dict[str, Any]:
    import anthropic

    client = client or anthropic.AsyncAnthropic()
    api_tools = [
        {
            "name": t["name"],
            "description": (t.get("description") or "")[:1000],
            "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]
    response = await client.messages.create(
        model=model,
        max_tokens=400,
        system=PLANNER_SYSTEM.format(brand=brand),
        tools=api_tools,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": clean_utterance(utterance, brand)}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return {"tool": block.name, "arguments": dict(block.input or {})}
    return plan_rules(utterance, brand)
