"""Application entry point running both FastAPI Web UI and Aiogram Telegram Bot."""

from __future__ import annotations

import logging
import sys

import uvicorn

from config import get_settings
from web.app import app


def _configure_logging() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


_configure_logging()


def main() -> None:
    _configure_logging()
    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
