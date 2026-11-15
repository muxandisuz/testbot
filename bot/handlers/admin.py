"""Admin FSM handlers for creating categories, quizzes, and bulk-importing questions in Telegram."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
from bot import engine, formatters as fmt, keyboards as kb
from config import get_settings

router = Router(name="admin")


class AdminStates(StatesGroup):
    waiting_category_input = State()
    waiting_quiz_category = State()
    waiting_quiz_title = State()
    waiting_quiz_meta = State()
    waiting_bulk_questions = State()


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_id_list


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer(
        "❎ Joriy admin amali bekor qilindi.",
        reply_markup=kb.to_aiogram_markup(kb.admin_menu_keyboard() if _is_admin(message.from_user.id) else kb.back_to_menu_keyboard()),
    )


@router.callback_query(F.data == "adm:add_cat")
async def cb_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔️ Faqat adminlar uchun!", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_category_input)
    await callback.message.edit_text(
        "➕ <b>Yangi fan qo'shish</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Quyidagi formatda xabar yuboring:\n"
        "<code>Ikonka | Fan nomi | Qisqa tavsif</code>\n\n"
        "💡 <i>Masalan:</i>\n"
        "<code>🧬 | Biologiya | Hujayra, genetika va anatomiya testlari</code>\n\n"
        "Bekor qilish uchun /cancel yuboring.",
        reply_markup=kb.to_aiogram_markup([[kb.btn("🔙 Bekor qilish", "adm:cancel")]]),
    )
    await callback.answer()


@router.message(AdminStates.waiting_category_input)
async def process_category_input(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) >= 2:
        icon, name = parts[0] or "📚", parts[1]
        desc = parts[2] if len(parts) > 2 else ""
    else:
        icon, name, desc = "📚", raw, ""

    if not name:
        await message.answer("⚠️ Fan nomi bo'sh bo'lmasligi kerak. Qaytadan yuboring yoki /cancel bosing.")
        return

    cat = await db.create_category(name=name, icon=icon, description=desc)
    await state.clear()
    await message.answer(
        f"✅ Yangi fan qo'shildi: {fmt.esc(cat['icon'])} <b>{fmt.esc(cat['name'])}</b>",
        reply_markup=kb.to_aiogram_markup(kb.admin_menu_keyboard()),
    )


@router.callback_query(F.data == "adm:add_quiz")
async def cb_add_quiz_pick_cat(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔️ Faqat adminlar uchun!", show_alert=True)
        return
    cats = await db.list_categories(active_only=True)
    if not cats:
        await callback.answer("Avval kamida bitta fan qo'shing!", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_quiz_category)
    rows = [[kb.btn(f"{c['icon']} {c['name']}", f"adm:qcat:{c['id']}")] for c in cats]
    rows.append([kb.btn("🔙 Bekor qilish", "adm:cancel")])
    await callback.message.edit_text(
        "📝 <b>Yangi test yaratish (1/3-qadam)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Test qaysi fanga tegishli bo'lishini tanlang:",
        reply_markup=kb.to_aiogram_markup(rows),
    )
    await callback.answer()


@router.callback_query(AdminStates.waiting_quiz_category, F.data.startswith("adm:qcat:"))
async def cb_add_quiz_cat_selected(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=cat_id)
    await state.set_state(AdminStates.waiting_quiz_title)
    await callback.message.edit_text(
        "📝 <b>Yangi test yaratish (2/3-qadam)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Test nomini yozib yuboring.\n\n"
        "💡 <i>Masalan:</i> <code>Kvadrat tenglamalar - 1-variant</code>",
        reply_markup=kb.to_aiogram_markup([[kb.btn("🔙 Bekor qilish", "adm:cancel")]]),
    )
    await callback.answer()


@router.message(AdminStates.waiting_quiz_title)
async def process_quiz_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("⚠️ Test nomi kamida 3 ta belgidan iborat bo'lsin.")
        return
    await state.update_data(title=title)
    await state.set_state(AdminStates.waiting_quiz_meta)
    await message.answer(
        "📝 <b>Yangi test yaratish (3/3-qadam)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Test kodi, qiyinlik va vaqtni quyidagi formatda yuboring:\n"
        "<code>kod | oson/orta/qiyin | daqiqa</code>\n\n"
        "💡 <i>Masalan:</i> <code>2025 | orta | 5</code>\n"
        "Yoki avtomatik sozlamalar uchun <code>auto</code> deb yozing.",
        reply_markup=kb.to_aiogram_markup([[kb.btn("🔙 Bekor qilish", "adm:cancel")]]),
    )


@router.message(AdminStates.waiting_quiz_meta)
async def process_quiz_meta(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    raw = (message.text or "").strip()
    code: str | None = None
    difficulty = "orta"
    time_limit_sec = 300

    if raw.lower() != "auto":
        parts = [p.strip() for p in raw.split("|")]
        if parts and parts[0] and parts[0].lower() != "auto":
            code = parts[0]
        if len(parts) > 1 and parts[1].lower() in {"oson", "orta", "qiyin"}:
            difficulty = parts[1].lower()
        if len(parts) > 2 and parts[2].isdigit():
            time_limit_sec = max(60, int(parts[2]) * 60)

    try:
        quiz = await db.create_quiz(
            category_id=int(data["category_id"]),
            title=str(data["title"]),
            code=code,
            difficulty=difficulty,
            time_limit_sec=time_limit_sec,
        )
    except ValueError as exc:
        await message.answer(f"⚠️ {fmt.esc(str(exc))}")
        return

    await state.clear()
    await message.answer(
        f"✅ <b>Test muvaffaqiyatli yaratildi!</b>\n"
        f"📝 Nomi: <b>{fmt.esc(quiz['title'])}</b>\n"
        f"🔑 Test kodi: <code>{fmt.esc(quiz['code'])}</code>\n\n"
        "Endi unga savollar qo'shishingiz mumkin:",
        reply_markup=kb.to_aiogram_markup([
            [kb.btn("📥 Savollar import qilish", f"adm:bulk:{quiz['id']}")],
            [kb.btn("🔙 Admin Panel", "adm:m")],
        ]),
    )


@router.callback_query(F.data.startswith("adm:bulk:"))
async def cb_bulk_import_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔️ Faqat adminlar uchun!", show_alert=True)
        return
    quiz_id = int(callback.data.split(":")[2])
    quiz = await db.get_quiz(quiz_id)
    if not quiz:
        await callback.answer("Test topilmadi", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_bulk_questions)
    await state.update_data(quiz_id=quiz_id)
    await callback.message.edit_text(
        f"📥 <b>Savollarni tezkor import qilish — {fmt.esc(quiz['title'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Har bir qatorga 1 ta savolni quyidagi formatda yuboring:\n"
        "<code>Savol | A | B | C | D | To'g'ri(A/B/C/D) | Izoh</code>\n\n"
        "💡 <i>Namuna:</i>\n"
        "<code>2 + 2 nechaga teng? | 3 | 4 | 5 | 6 | B | Oddiy qo'shish amali.</code>\n"
        "<code>O'zbekiston poytaxti? | Samarqand | Buxoro | Toshkent | Xiva | C | Toshkent shahri poytaxt.</code>",
        reply_markup=kb.to_aiogram_markup([[kb.btn("🔙 Bekor qilish", "adm:cancel")]]),
    )
    await callback.answer()


@router.message(AdminStates.waiting_bulk_questions)
async def process_bulk_questions(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    quiz_id = int(data["quiz_id"])
    created, errors = await db.bulk_create_questions(quiz_id, message.text or "")
    await state.clear()
    err_block = ("\n\n⚠️ <b>Xatolar:</b>\n" + "\n".join(fmt.esc(e) for e in errors[:5])) if errors else ""
    await message.answer(
        f"✅ <b>{len(created)} ta savol qo'shildi!</b>{err_block}",
        reply_markup=kb.to_aiogram_markup([
            [kb.btn("👀 Testni ko'rish", f"qz:i:{quiz_id}")],
            [kb.btn("🔙 Admin Panel", "adm:m")],
        ]),
    )


@router.callback_query(F.data == "adm:cancel")
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_adm = _is_admin(callback.from_user.id)
    resp = await engine.handle_callback(
        telegram_id=callback.from_user.id,
        full_name=callback.from_user.full_name,
        username=callback.from_user.username,
        data="adm:m" if is_adm else "m:main",
        is_admin=is_adm,
    )
    await callback.message.edit_text(resp.text, reply_markup=kb.to_aiogram_markup(resp.keyboard))
    await callback.answer("Bekor qilindi")
