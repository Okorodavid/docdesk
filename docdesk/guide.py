"""Step-by-step guides: turn the in-app directions inside a help answer ("Open the Brightline
app, go to Billing, tap Pay now, and choose Mobile money") into steps that point at the exact
place on the brand's app screen. The answer card shows each screen with a glowing highlight
on the place to tap while the assistant reads the step aloud.

The brand describes its app once in an app map (demo/app-map.json): screens, the elements on
them, and which screen each element opens. Guides are built only from text in the cited answer,
so the walkthrough never shows a step the help centre did not state."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

VERBS = (
    "open", "go", "tap", "choose", "select", "press", "pick", "switch", "turn", "look", "click",
    "find", "enter", "scroll", "hit", "use",
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_CHUNK = re.compile(r"\s*(?::|;|,\s*(?:and\s+|then\s+)?|\s+then\s+|\s+and then\s+|\s+and\s+(?=(?:" + "|".join(VERBS) + r")\b))\s*", re.I)


@lru_cache(maxsize=8)
def load_app_map(path: str) -> dict | None:
    p = Path(path)
    if not str(path) or not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _index(app_map: dict) -> dict[str, tuple[str, dict]]:
    """element id -> (screen id, element)"""
    return {el["id"]: (sid, el) for sid, screen in app_map["screens"].items() for el in screen["elements"]}


def _names(el: dict) -> list[str]:
    return [n.lower() for n in [el["label"], *el.get("aliases", [])]]


def _mentions(chunk: str, name: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", chunk.lower()) is not None


def _match(chunk: str, app_map: dict, current: str) -> tuple[str, dict] | None:
    """Best element named in the chunk: longest name wins, the current screen breaks ties."""
    best, best_key = None, None
    for sid, screen in app_map["screens"].items():
        for el in screen["elements"]:
            for name in _names(el):
                if _mentions(chunk, name):
                    key = (len(name), sid == current)
                    if best_key is None or key > best_key:
                        best, best_key = (sid, el), key
    return best


def _say(chunk: str, el: dict) -> str:
    text = re.sub(r"^(and|then|also)\s+", "", chunk.strip(), flags=re.I).rstrip(".")
    text = re.sub(r"^in the (?:\w+ )?app,?\s+", "", text, flags=re.I)
    if re.match(r"^under\s+", text, re.I):
        text = "Go to " + re.sub(r"^under\s+", "", text, flags=re.I)
    if not re.match(r"^(" + "|".join(VERBS) + r")\b", text, re.I):
        text = "Tap " + el["label"]
    return text[0].upper() + text[1:] + "."


def _is_step(chunk: str) -> bool:
    c = re.sub(r"^(and|then|also)\s+", "", chunk.strip().lower())
    c = re.sub(r"^in the (?:\w+ )?app,?\s+", "", c)
    return bool(re.match(r"^(" + "|".join(VERBS) + r"|under)\b", c))


def build_guide(answer: str, app_map: dict | None) -> dict | None:
    """Return {app, intro, steps, after, screens} when the answer has at least two in-app steps."""
    if not app_map or not answer:
        return None
    current = app_map.get("start", "launcher")
    steps: list[dict] = []
    intro: list[str] = []
    after: list[str] = []  # notes that follow the steps, read once the walkthrough ends
    for sentence in _SENTENCE.split(answer.strip()):
        chunks = [c for c in _CHUNK.split(sentence) if c and c.strip()]
        lead: list[str] = []
        in_steps = False
        for chunk in chunks:
            target_text = re.sub(r"^\s*(?:and\s+|then\s+)?in the (?:\w+ )?app,?\s+", "", chunk, flags=re.I)
            found = _match(target_text, app_map, current) if (in_steps or _is_step(chunk)) else None
            if found is None:
                if not in_steps:
                    lead.append(chunk)
                continue
            sid, el = found
            in_steps = True
            if steps and steps[-1]["target"] == el["id"]:
                continue
            steps.append({"say": _say(chunk, el), "screen": sid, "target": el["id"]})
            current = el.get("opens", sid)
        if not in_steps:
            (after if steps else intro).append(sentence.strip())
        else:
            text = ", ".join(lead).strip(" ,:;")
            trimmed = re.sub(r"\s+(?:in|from|on)\s+the\s+[\w ]*app$", "", text, flags=re.I).strip()
            if trimmed != text:
                trimmed += " in the app"
            if len(trimmed.split()) >= 3:
                intro.append(trimmed.rstrip(".") + ".")
    if len(steps) < 2:
        return None
    # Make sure the walkthrough starts by opening the app.
    first_screen = steps[0]["screen"]
    if first_screen != app_map.get("start") and app_map.get("start") in app_map["screens"]:
        launcher = app_map["screens"][app_map["start"]]
        opener = next((e for e in launcher["elements"] if e.get("opens") == first_screen), None)
        if opener:
            steps.insert(0, {"say": f"Open the {app_map['app']}.", "screen": app_map["start"], "target": opener["id"]})
    for n, step in enumerate(steps, 1):
        step["n"] = n
    used = {s["screen"] for s in steps}
    screens = {sid: app_map["screens"][sid] for sid in app_map["screens"] if sid in used}
    lead = " ".join(intro).strip() or "Here's how."
    tail = "I'll show you where to tap, step by step."
    return {
        "app": app_map["app"], "intro": f"{lead} {tail}".strip(), "steps": steps,
        "after": " ".join(after).strip(), "screens": screens,
    }
