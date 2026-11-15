"""Application configuration management with dynamic .env reload support."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import dotenv_values, load_dotenv, set_key
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def _default_host() -> str:
    return "0.0.0.0" if ("RAILWAY_ENVIRONMENT" in os.environ or "PORT" in os.environ) else "127.0.0.1"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and .env."""

    bot_token: str = ""
    admin_ids: str = "123456789"
    database_path: str = "quiz_bot.db"
    host: str = Field(default_factory=_default_host)
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def admin_id_list(self) -> set[int]:
        """Parse comma-separated Telegram admin IDs into a set of integers."""
        result: set[int] = set()
        for raw in (self.admin_ids or "").split(","):
            raw = raw.strip()
            if raw.lstrip("-").isdigit():
                result.add(int(raw))
        return result

    @property
    def resolved_db_path(self) -> Path:
        """Return an absolute Path for the SQLite database file."""
        db_path = Path(self.database_path)
        if not db_path.is_absolute():
            db_path = BASE_DIR / db_path
        return db_path


_settings = Settings()


def get_settings() -> Settings:
    """Return the active Settings instance."""
    return _settings


def reload_settings(override_env: bool = False) -> Settings:
    """Reload settings, optionally forcing .env values over process env vars."""
    global _settings
    if override_env and ENV_PATH.exists():
        values = dotenv_values(ENV_PATH)
        for key, val in values.items():
            if val is not None:
                os.environ[key] = val
        load_dotenv(ENV_PATH, override=True)
    _settings = Settings()
    return _settings


def update_env_settings(bot_token: str | None = None, admin_ids: str | None = None) -> Settings:
    """Persist updated BOT_TOKEN and/or ADMIN_IDS to .env and reload settings."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            "BOT_TOKEN=\nADMIN_IDS=123456789\nDATABASE_PATH=quiz_bot.db\nHOST=127.0.0.1\nPORT=8000\n",
            encoding="utf-8",
        )
    if bot_token is not None:
        set_key(str(ENV_PATH), "BOT_TOKEN", bot_token.strip(), quote_mode="never")
    if admin_ids is not None:
        set_key(str(ENV_PATH), "ADMIN_IDS", admin_ids.strip(), quote_mode="never")
    return reload_settings(override_env=True)
