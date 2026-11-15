"""User Telegram bot handlers delegating directly to the shared quiz engine."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import engine, keyboards as kb
from config import get_settings

router = Router(name="user")


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_id_list


@router.message(Command("start", "help", "stats", "top", "admin"))
async def handle_commands(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    resp = await engine.handle_text_message(
        telegram_id=user.id,
        full_name=user.full_name,
        username=user.username,
        text=message.text or "/start",
        is_admin=_is_admin(user.id),
    )
    await message.answer(
        resp.text,
        reply_markup=kb.to_aiogram_markup(resp.keyboard),
    )


@router.callback_query()
async def handle_callbacks(callback: CallbackQuery) -> None:
    user = callback.from_user
    resp = await engine.handle_callback(
        telegram_id=user.id,
        full_name=user.full_name,
        username=user.username,
        data=callback.data or "m:main",
        is_admin=_is_admin(user.id),
    )
    if callback.message:
        try:
            await callback.message.edit_text(
                resp.text,
                reply_markup=kb.to_aiogram_markup(resp.keyboard),
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                await callback.message.answer(
                    resp.text,
                    reply_markup=kb.to_aiogram_markup(resp.keyboard),
                )
    await callback.answer(resp.toast or "")


@router.message(F.text)
async def handle_plain_text(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    resp = await engine.handle_text_message(
        telegram_id=user.id,
        full_name=user.full_name,
        username=user.username,
        text=message.text or "",
        is_admin=_is_admin(user.id),
    )
    await message.answer(
        resp.text,
        reply_markup=kb.to_aiogram_markup(resp.keyboard),
    )
