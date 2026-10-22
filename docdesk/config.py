"""DocDesk settings, read from environment variables and an optional .env file."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from communityops.config import FALLBACK_MODELS, Settings

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent


def _bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class DocDeskSettings:
    brand: str = "Brightline Internet"
    db_path: Path = ROOT / "data" / "docdesk.db"
    articles_dir: Path = ROOT / "data" / "articles"
    host: str = "127.0.0.1"
    port: int = 8765
    answer_mode: str = "auto"  # auto | claude | offline
    model: str = "claude-opus-5-5"
    planner_model: str = "claude-haiku-5-5"
    effort: str = "low"
    top_k: int = 6
    staff_token: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    demo_docs_dir: Path = ROOT / "demo" / "docs"
    app_map_path: Path = ROOT / "demo" / "app-map.json"  # the brand's app screens, for guided steps

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def has_api_key(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @property
    def use_claude(self) -> bool:
        if self.answer_mode == "claude":
            return True
        if self.answer_mode == "offline":
            return False
        return self.has_api_key

    def core(self) -> Settings:
        """Settings object the communityops answerer expects."""
        return Settings(
            project_name=self.brand,
            db_path=self.db_path,
            model=self.model,
            effort=self.effort,
            use_fallbacks=self.model in FALLBACK_MODELS,
            max_tokens=4000,
            top_k=self.top_k,
        )


def load_settings(env_file: str | os.PathLike | None = ".env") -> DocDeskSettings:
    if load_dotenv and env_file and Path(env_file).exists():
        load_dotenv(env_file)
    env = os.environ.get
    mode = (env("ANSWER_MODE") or "auto").strip().lower()
    if mode not in {"auto", "claude", "offline"}:
        raise ValueError("ANSWER_MODE must be auto, claude or offline")
    s = DocDeskSettings(
        brand=env("BRAND_NAME") or "Brightline Internet",
        db_path=Path(env("DB_PATH")) if env("DB_PATH") else ROOT / "data" / "docdesk.db",
        host=env("HOST") or "127.0.0.1",
        port=int(env("PORT") or 8765),
        answer_mode=mode,
        model=env("MODEL") or "claude-opus-5-5",
        planner_model=env("PLANNER_MODEL") or "claude-haiku-5-5",
        effort=env("EFFORT") or "low",
        top_k=int(env("TOP_K") or 6),
    )
    if env("APP_MAP"):
        s.app_map_path = Path(env("APP_MAP"))
    if env("STAFF_TOKEN"):
        s.staff_token = env("STAFF_TOKEN")
    if not _bool(env("USE_DEMO_DOCS"), True):
        s.demo_docs_dir = Path("")
    return s
