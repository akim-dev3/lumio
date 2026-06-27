"""Centralised configuration loader.

Loads environment variables from a local ``.env`` file (when present) and
exposes them via the :class:`Config` dataclass. Missing required variables
cause an immediate ``RuntimeError`` so the process never starts in a
half-configured state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root if it exists. In production (Render) the
# environment is provided by the platform and the file is absent — that's fine,
# load_dotenv silently no-ops in that case.
load_dotenv(BASE_DIR / ".env")


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in your .env file or in the hosting platform settings."
        )
    return value


def _optional(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Config:
    bot_token: str
    openrouter_api_key: str
    openrouter_model: str
    webapp_url: str
    webhook_url: str
    database_path: str
    webhook_secret: str
    port: int

    @property
    def webhook_path(self) -> str:
        return "/webhook"

    @property
    def full_webhook_url(self) -> str:
        return f"{self.webhook_url.rstrip('/')}{self.webhook_path}"


def load_config() -> Config:
    return Config(
        bot_token=_require("BOT_TOKEN"),
        openrouter_api_key=_require("OPENROUTER_API_KEY"),
        openrouter_model=_optional("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
        webapp_url=_require("WEBAPP_URL"),
        webhook_url=_require("WEBHOOK_URL"),
        database_path=_optional("DATABASE_PATH", str(BASE_DIR / "lumio.db")),
        webhook_secret=_optional("WEBHOOK_SECRET", "lumio-secret"),
        port=int(_optional("PORT", "8080")),
    )


config = load_config()
