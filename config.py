from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip().replace(",", ".")
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    hh_token: str | None = None
    owner_id: int | None = None
    proxy_url: str | None = None
    db_path: Path = field(default_factory=lambda: BASE_DIR / "data" / "bot.sqlite3")
    batch_size: int = 10
    message_delay: float = 1.4
    page_delay: float = 1.0
    max_pages: int = 40
    request_timeout: int = 35

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token)


def load_settings() -> Settings:
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        hh_token=os.getenv("HH_TOKEN", "").strip() or None,
        owner_id=_env_int("OWNER_ID"),
        proxy_url=os.getenv("PROXY_URL", "").strip() or None,
        db_path=Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "bot.sqlite3"))),
        batch_size=max(1, _env_int("BATCH_SIZE", 10) or 10),
        message_delay=max(0.0, _env_float("MESSAGE_DELAY", 1.4)),
        page_delay=max(0.0, _env_float("PAGE_DELAY", 1.0)),
        max_pages=max(1, _env_int("MAX_PAGES", 40) or 40),
        request_timeout=max(5, _env_int("REQUEST_TIMEOUT", 35) or 35),
    )
