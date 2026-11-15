"""Async lifecycle manager for running Aiogram polling alongside FastAPI."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.handlers import admin as admin_handlers
from bot.handlers import user as user_handlers
from config import get_settings

logger = logging.getLogger("testmaster.bot")


class BotManager:
    """Manages Bot and Dispatcher polling tasks safely inside FastAPI's event loop."""

    def __init__(self) -> None:
        self._bot: Bot | None = None
        self._dp: Dispatcher | None = None
        self._task: asyncio.Task[None] | None = None
        self._status: dict[str, Any] = {
            "running": False,
            "mode": "simulator",
            "bot_username": None,
            "bot_name": None,
            "has_token": False,
            "error": None,
        }

    def get_status(self) -> dict[str, Any]:
        return dict(self._status)

    async def stop_bot(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

        if self._dp is not None:
            self._dp = None

        if self._bot is not None:
            try:
                await self._bot.session.close()
            except Exception:
                pass
            self._bot = None

        self._status["running"] = False
        self._status["bot_username"] = None
        self._status["bot_name"] = None

    async def start_or_restart(self, token: str | None = None) -> dict[str, Any]:
        await self.stop_bot()
        active_token = (token if token is not None else get_settings().bot_token).strip()
        self._status["has_token"] = bool(active_token)
        self._status["error"] = None

        if not active_token:
            self._status["mode"] = "simulator"
            self._status["running"] = False
            logger.info("BOT_TOKEN topilmadi — Web Simulyator rejimida ishlayapti.")
            return self.get_status()

        bot = Bot(
            token=active_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        try:
            me = await bot.get_me()
            await bot.delete_webhook(drop_pending_updates=False)
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="🏠 Bosh menyu"),
                    BotCommand(command="stats", description="📊 Mening statistikam"),
                    BotCommand(command="top", description="🏆 Reyting jadvali"),
                    BotCommand(command="help", description="ℹ️ Qo'llanma va qoidalar"),
                    BotCommand(command="admin", description="⚙️ Admin panel"),
                ]
            )
        except Exception as exc:
            await bot.session.close()
            self._status["mode"] = "error"
            self._status["running"] = False
            self._status["error"] = f"Telegram token xatosi: {exc}"
            logger.warning("Telegram botga ulanib bo'lmadi: %s", exc)
            return self.get_status()

        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(admin_handlers.router)
        dp.include_router(user_handlers.router)

        self._bot = bot
        self._dp = dp
        self._status["mode"] = "telegram"
        self._status["running"] = True
        self._status["bot_username"] = me.username
        self._status["bot_name"] = me.full_name
        self._status["error"] = None

        self._task = asyncio.create_task(self._run_polling(dp, bot), name="aiogram-polling")
        logger.info("Telegram bot ishga tushdi: @%s", me.username)
        return self.get_status()

    async def _run_polling(self, dp: Dispatcher, bot: Bot) -> None:
        try:
            await dp.start_polling(bot, handle_signals=False, allowed_updates=dp.resolve_used_update_types())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Polling xatosi: %s", exc)
            self._status["running"] = False
            self._status["mode"] = "error"
            self._status["error"] = str(exc)

    async def send_message_to_users(self, telegram_ids: list[int], text: str) -> dict[str, int]:
        """Send a Telegram message to one or more users via the active or configured bot."""
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("Xabar matni bo'sh bo'lmasligi kerak.")

        temp_bot: Bot | None = None
        bot = self._bot
        if bot is None:
            token = get_settings().bot_token.strip()
            if not token:
                raise RuntimeError("Telegram bot ulanmagan (BOT_TOKEN kiritilmagan).")
            temp_bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            bot = temp_bot

        sent = 0
        failed = 0
        try:
            for tid in telegram_ids:
                try:
                    await bot.send_message(chat_id=tid, text=clean_text)
                    sent += 1
                except Exception as exc:
                    logger.warning("Foydalanuvchi %s ga xabar yuborib bo'lmadi: %s", tid, exc)
                    failed += 1
        finally:
            if temp_bot is not None:
                await temp_bot.session.close()
        return {"sent": sent, "failed": failed}


bot_manager = BotManager()
