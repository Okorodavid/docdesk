"""Settings loaded from environment variables (and a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional; plain environment variables also work.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

# Models that accept the server-side `fallbacks: "default"` parameter.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int | None) -> int | None:
    if value is None or value.strip() == "":
        return default
    return int(value.strip())


@dataclass
class Settings:
    project_name: str = "this project"
    db_path: Path = Path("communityops.db")
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    use_fallbacks: bool = True
    max_tokens: int = 4000
    top_k: int = 6
    telegram_token: str = ""
    escalation_chat_id: int | None = None
    answer_mode: str = "questions"  # "questions" or "mention"
    allow_private: bool = False
    user_limit: int = 5  # questions per user per window
    user_window_seconds: int = 600
    daily_cap: int = 300  # answers per UTC day across all chats
    allowed_chat_ids: set[int] = field(default_factory=set)

    @property
    def fallbacks_enabled(self) -> bool:
        return self.use_fallbacks and self.model in FALLBACK_MODELS


def load_settings(env_file: str | os.PathLike | None = ".env") -> Settings:
    if load_dotenv and env_file and Path(env_file).exists():
        load_dotenv(env_file)
    env = os.environ.get
    allowed = {int(x) for x in (env("ALLOWED_CHAT_IDS") or "").replace(" ", "").split(",") if x}
    mode = (env("ANSWER_MODE") or "questions").strip().lower()
    if mode not in {"questions", "mention"}:
        raise ValueError("ANSWER_MODE must be 'questions' or 'mention'")
    return Settings(
        project_name=env("PROJECT_NAME") or "this project",
        db_path=Path(env("DB_PATH") or "communityops.db"),
        model=env("MODEL") or "claude-opus-5-5",
        effort=env("EFFORT") or "medium",
        use_fallbacks=_bool(env("USE_FALLBACKS"), True),
        max_tokens=_int(env("MAX_TOKENS"), 4000) or 4000,
        top_k=_int(env("TOP_K"), 6) or 6,
        telegram_token=env("TELEGRAM_BOT_TOKEN") or "",
        escalation_chat_id=_int(env("ESCALATION_CHAT_ID"), None),
        answer_mode=mode,
        allow_private=_bool(env("ALLOW_PRIVATE"), False),
        user_limit=_int(env("USER_LIMIT"), 5) or 5,
        user_window_seconds=_int(env("USER_WINDOW_SECONDS"), 600) or 600,
        daily_cap=_int(env("DAILY_CAP"), 300) or 300,
        allowed_chat_ids=allowed,
    )
