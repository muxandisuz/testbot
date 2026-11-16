"""Transport-agnostic quiz bot engine shared by Aiogram handlers and the Web Simulator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import database as db
from bot import formatters as fmt
from bot import keyboards as kb


@dataclass
class EngineResponse:
    """Unified bot response rendered in both Telegram and the Web Simulator."""

    text: str
    keyboard: kb.KeyboardRows
    toast: str | None = None
    awaiting_input: str | None = None


def _compute_remaining_sec(attempt: dict[str, Any], quiz: dict[str, Any]) -> tuple[int, int]:
    """Return (elapsed_sec, remaining_sec) for an attempt."""
    limit = int(quiz.get("time_limit_sec", 300))
    started_raw = attempt.get("started_at")
    if not started_raw:
        return 0, limit
    try:
        started_dt = datetime.fromisoformat(started_raw)
        if started_dt.tzinfo is None:
            started_dt = started_dt.replace(tzinfo=timezone.utc)
        elapsed = max(0, int((datetime.now(timezone.utc) - started_dt).total_seconds()))
    except ValueError:
        elapsed = 0
    return elapsed, max(0, limit - elapsed)


async def render_main_menu(
    telegram_id: int,
    full_name: str,
    username: str | None = None,
    is_admin: bool = False,
    db_path: Path | str | None = None,
    toast: str | None = None,
) -> EngineResponse:
    await db.get_or_create_user(telegram_id, full_name, username, db_path=db_path)
    stats = await db.get_user_stats(telegram_id, db_path=db_path)
    assert stats is not None
    text = fmt.build_welcome_text(stats, stats["accuracy"])
    return EngineResponse(text=text, keyboard=kb.main_menu_keyboard(is_admin=is_admin), toast=toast)


async def render_quiz_info_by_id(
    quiz_id: int,
    db_path: Path | str | None = None,
    toast: str | None = None,
) -> EngineResponse:
    quiz = await db.get_quiz(quiz_id, db_path=db_path)
    if not quiz:
        return EngineResponse(
            text="❌ <b>Test topilmadi.</b>",
            keyboard=kb.back_to_menu_keyboard(),
            toast="Test topilmadi",
        )
    text = fmt.build_quiz_info_text(quiz)
    markup = kb.quiz_info_keyboard(
        quiz_id=int(quiz["id"]),
        category_id=int(quiz["category_id"]),
        question_count=int(quiz.get("question_count", 0)),
    )
    return EngineResponse(text=text, keyboard=markup, toast=toast)


async def _render_attempt_result(
    attempt_id: int,
    auto_expired: bool = False,
    db_path: Path | str | None = None,
    toast: str | None = None,
) -> EngineResponse:
    attempt = await db.get_attempt(attempt_id, db_path=db_path)
    if not attempt:
        return EngineResponse(
            text="❌ <b>Natija topilmadi.</b>",
            keyboard=kb.back_to_menu_keyboard(),
        )
    if not attempt["is_completed"]:
        attempt = await db.finalize_attempt(attempt_id, db_path=db_path)
    quiz = await db.get_quiz(int(attempt["quiz_id"]), db_path=db_path)
    review_items = await db.get_attempt_review_items(attempt_id, wrong_only=False, db_path=db_path)
    wrong_items = await db.get_attempt_review_items(attempt_id, wrong_only=True, db_path=db_path)
    has_mistakes = len(wrong_items) > 0
    assert quiz is not None
    text = fmt.build_result_text(quiz, attempt, review_items, auto_expired=auto_expired)
    markup = kb.result_keyboard(attempt_id=attempt_id, quiz_id=int(quiz["id"]), has_mistakes=has_mistakes)
    return EngineResponse(text=text, keyboard=markup, toast=toast)


async def _render_question_at_index(
    attempt_id: int,
    index: int,
    db_path: Path | str | None = None,
    practice_feedback: dict[str, Any] | None = None,
    toast: str | None = None,
) -> EngineResponse:
    attempt = await db.get_attempt(attempt_id, db_path=db_path)
    if not attempt:
        return EngineResponse(text="❌ <b>Test urinishi topilmadi.</b>", keyboard=kb.back_to_menu_keyboard())

    if attempt["is_completed"]:
        return await _render_attempt_result(attempt_id, db_path=db_path, toast="Test allaqachon yakunlangan")

    quiz = await db.get_quiz(int(attempt["quiz_id"]), db_path=db_path)
    if not quiz:
        return EngineResponse(text="❌ <b>Test topilmadi.</b>", keyboard=kb.back_to_menu_keyboard())

    questions = await db.list_questions(int(quiz["id"]), db_path=db_path)
    if not questions:
        return EngineResponse(
            text="📭 <b>Bu testda hozircha savollar mavjud emas.</b>",
            keyboard=kb.quiz_info_keyboard(int(quiz["id"]), int(quiz["category_id"]), 0),
        )

    elapsed, remaining = _compute_remaining_sec(attempt, quiz)
    if attempt["mode"] == "exam" and remaining <= 0:
        await db.finalize_attempt(attempt_id, duration_sec=int(quiz["time_limit_sec"]), db_path=db_path)
        return await _render_attempt_result(attempt_id, auto_expired=True, db_path=db_path, toast="⏰ Vaqt tugadi!")

    safe_idx = max(0, min(index, len(questions) - 1))
    if attempt["current_index"] != safe_idx:
        await db.update_attempt_index(attempt_id, safe_idx, db_path=db_path)

    question = questions[safe_idx]
    answers = await db.get_attempt_answers(attempt_id, db_path=db_path)
    existing_ans = answers.get(int(question["id"]))
    selected_option = existing_ans["selected_option"] if existing_ans else None

    if attempt["mode"] == "practice" and practice_feedback is None and existing_ans is not None:
        practice_feedback = {
            "selected_option": existing_ans["selected_option"],
            "is_correct": bool(existing_ans["is_correct"]),
            "correct_option": question["correct_option"],
            "explanation": question["explanation"],
        }

    correct_so_far = sum(1 for a in answers.values() if a["is_correct"])
    wrong_so_far = sum(1 for a in answers.values() if not a["is_correct"])

    text = fmt.build_question_text(
        quiz=quiz,
        question=question,
        index=safe_idx,
        total=len(questions),
        mode=attempt["mode"],
        remaining_sec=remaining,
        answered_count=len(answers),
        selected_option=selected_option,
        practice_feedback=practice_feedback,
        correct_so_far=correct_so_far,
        wrong_so_far=wrong_so_far,
    )
    markup = kb.question_keyboard(
        attempt_id=attempt_id,
        question=question,
        index=safe_idx,
        total=len(questions),
        mode=attempt["mode"],
        selected_option=selected_option,
        answered_in_practice=(attempt["mode"] == "practice" and practice_feedback is not None),
    )
    return EngineResponse(text=text, keyboard=markup, toast=toast)


def _describe_callback_action(data: str) -> str:
    """Convert raw callback_data into a human-readable Uzbek action label for chat history."""
    raw = (data or "").strip()
    parts = raw.split(":")
    action = parts[0] if parts else ""

    if raw == "m:main":
        return "🏠 Bosh menyu"
    if raw in {"c:list", "qz:start_main"}:
        return "📝 Test ishlash"
    if action == "c" and len(parts) >= 3 and parts[1] == "v":
        return f"📚 Fan tanlandi (#{parts[2]})"
    if action == "qz" and len(parts) >= 3:
        sub = parts[1]
        if sub == "i":
            return f"ℹ️ Test ma'lumotlari (#{parts[2]})"
        if sub == "s" and len(parts) >= 4:
            mode_lbl = "Imtihon rejimi" if parts[3] == "e" else "Mashq rejimi"
            return f"▶️ Testni boshlash ({mode_lbl})"
        if sub == "n" and len(parts) >= 4 and parts[3].lstrip("-").isdigit():
            return f"➡️ {int(parts[3]) + 1}-savolga o'tish"
        if sub == "a" and len(parts) >= 5:
            return f"✍️ Javob belgilandi: {parts[4].upper()} varianti"
        if sub == "map":
            return "🗺 Savollar xaritasi"
        if sub == "f":
            return "🏁 Testni topshirish"
        if sub == "fc":
            return "🚪 Testni yakunlash va natijani ko'rish"
        if sub == "res":
            return "📊 Test natijasi"
        if sub == "r":
            return "🔍 Savollar tahlili"
    if raw == "rnd:s":
        return "🎲 Tasodifiy test"
    if raw == "code:p":
        return "🔑 Kod orqali kirish"
    if raw == "st:me":
        return "📊 Statistikam"
    if action == "lb":
        return "🏆 Reyting jadvali"
    if raw == "hp:v":
        return "ℹ️ Qoidalar"
    if action == "adm":
        return f"⚙️ Admin panel ({raw})"
    return f"📲 Tugma bosildi: {raw}"


async def handle_callback(
    telegram_id: int,
    full_name: str,
    username: str | None,
    data: str,
    is_admin: bool = False,
    db_path: Path | str | None = None,
) -> EngineResponse:
    """Process any inline button callback_data, log chat history, and return the next EngineResponse."""
    await db.get_or_create_user(telegram_id, full_name, username, db_path=db_path)
    await db.log_chat_message(
        telegram_id=telegram_id,
        sender="user",
        content=_describe_callback_action(data),
        action_type="callback",
        db_path=db_path,
    )
    resp = await _handle_callback_inner(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username,
        data=data,
        is_admin=is_admin,
        db_path=db_path,
    )
    await db.log_chat_message(
        telegram_id=telegram_id,
        sender="bot",
        content=resp.text,
        action_type="reply",
        db_path=db_path,
    )
    return resp


async def _handle_callback_inner(
    telegram_id: int,
    full_name: str,
    username: str | None,
    data: str,
    is_admin: bool = False,
    db_path: Path | str | None = None,
) -> EngineResponse:
    user = await db.get_or_create_user(telegram_id, full_name, username, db_path=db_path)
    parts = (data or "").split(":")
    action = parts[0] if parts else ""

    if data == "m:main":
        return await render_main_menu(telegram_id, full_name, username, is_admin=is_admin, db_path=db_path)

    if data in {"c:list", "qz:start_main"}:
        quizzes = await db.list_quizzes(active_only=True, db_path=db_path)
        return EngineResponse(
            text=fmt.build_quizzes_list_text(quizzes),
            keyboard=kb.quizzes_list_keyboard(quizzes),
        )

    if action == "c" and len(parts) >= 3 and parts[1] == "v":
        cat_id = int(parts[2])
        cat = await db.get_category(cat_id, db_path=db_path)
        if not cat:
            return EngineResponse(text="❌ <b>Fan topilmadi.</b>", keyboard=kb.back_to_menu_keyboard())
        quizzes = await db.list_quizzes(category_id=cat_id, active_only=True, db_path=db_path)
        return EngineResponse(
            text=fmt.build_category_quizzes_text(cat, quizzes),
            keyboard=kb.category_quizzes_keyboard(quizzes, cat_id),
        )

    if action == "qz" and len(parts) >= 3:
        sub = parts[1]
        if sub == "i":
            return await render_quiz_info_by_id(int(parts[2]), db_path=db_path)

        if sub == "s" and len(parts) >= 4:
            quiz_id = int(parts[2])
            mode = "exam" if parts[3] == "e" else "practice"
            questions = await db.list_questions(quiz_id, db_path=db_path)
            if not questions:
                return await render_quiz_info_by_id(
                    quiz_id, db_path=db_path, toast="Bu testda hali savollar yo'q"
                )
            attempt = await db.create_attempt(int(user["id"]), quiz_id, mode=mode, db_path=db_path)
            toast_msg = "⚡️ Mashq rejimi boshlandi!" if mode == "practice" else "🎓 Imtihon boshlandi! Omad!"
            return await _render_question_at_index(int(attempt["id"]), 0, db_path=db_path, toast=toast_msg)

        if sub == "n" and len(parts) >= 4:
            return await _render_question_at_index(int(parts[2]), int(parts[3]), db_path=db_path)

        if sub == "a" and len(parts) >= 5:
            attempt_id = int(parts[2])
            question_id = int(parts[3])
            selected = parts[4].upper()

            attempt = await db.get_attempt(attempt_id, db_path=db_path)
            if not attempt:
                return EngineResponse(text="❌ <b>Test urinishi topilmadi.</b>", keyboard=kb.back_to_menu_keyboard())
            if attempt["is_completed"]:
                return await _render_attempt_result(attempt_id, db_path=db_path, toast="Test allaqachon yakunlangan")

            quiz = await db.get_quiz(int(attempt["quiz_id"]), db_path=db_path)
            assert quiz is not None
            _, remaining = _compute_remaining_sec(attempt, quiz)
            if attempt["mode"] == "exam" and remaining <= 0:
                await db.finalize_attempt(attempt_id, duration_sec=int(quiz["time_limit_sec"]), db_path=db_path)
                return await _render_attempt_result(attempt_id, auto_expired=True, db_path=db_path, toast="⏰ Vaqt tugadi!")

            questions = await db.list_questions(int(quiz["id"]), db_path=db_path)
            q_index = next((i for i, q in enumerate(questions) if int(q["id"]) == question_id), int(attempt["current_index"]))

            feedback = await db.save_attempt_answer(attempt_id, question_id, selected, db_path=db_path)
            if attempt["mode"] == "practice":
                toast_msg = "✅ To'g'ri!" if feedback["is_correct"] else f"❌ Noto'g'ri! To'g'ri: {feedback['correct_option']}"
                return await _render_question_at_index(
                    attempt_id,
                    q_index,
                    db_path=db_path,
                    practice_feedback=feedback,
                    toast=toast_msg,
                )

            # Exam mode: advance smoothly to next question, or stay on last question with selected marker
            next_idx = q_index + 1 if q_index + 1 < len(questions) else q_index
            toast_msg = f"🔵 {selected} varianti belgilandi"
            return await _render_question_at_index(attempt_id, next_idx, db_path=db_path, toast=toast_msg)

        if sub == "map":
            attempt_id = int(parts[2])
            page = int(parts[3]) if len(parts) >= 4 else None
            attempt = await db.get_attempt(attempt_id, db_path=db_path)
            if not attempt:
                return EngineResponse(text="❌ <b>Test urinishi topilmadi.</b>", keyboard=kb.back_to_menu_keyboard())
            if attempt["is_completed"]:
                return await _render_attempt_result(attempt_id, db_path=db_path)
            quiz = await db.get_quiz(int(attempt["quiz_id"]), db_path=db_path)
            assert quiz is not None
            _, remaining = _compute_remaining_sec(attempt, quiz)
            if attempt["mode"] == "exam" and remaining <= 0:
                await db.finalize_attempt(attempt_id, duration_sec=int(quiz["time_limit_sec"]), db_path=db_path)
                return await _render_attempt_result(attempt_id, auto_expired=True, db_path=db_path, toast="⏰ Vaqt tugadi!")
            questions = await db.list_questions(int(quiz["id"]), db_path=db_path)
            answers = await db.get_attempt_answers(attempt_id, db_path=db_path)
            cur_idx = int(attempt["current_index"])
            target_page = page if page is not None else (cur_idx // 40)
            return EngineResponse(
                text=fmt.build_question_map_text(quiz, questions, answers, remaining),
                keyboard=kb.question_map_keyboard(attempt_id, questions, answers, cur_idx, page=target_page),
            )

        if sub == "f":
            attempt_id = int(parts[2])
            attempt = await db.get_attempt(attempt_id, db_path=db_path)
            if not attempt:
                return EngineResponse(text="❌ <b>Test urinishi topilmadi.</b>", keyboard=kb.back_to_menu_keyboard())
            if attempt["is_completed"]:
                return await _render_attempt_result(attempt_id, db_path=db_path)
            quiz = await db.get_quiz(int(attempt["quiz_id"]), db_path=db_path)
            assert quiz is not None
            _, remaining = _compute_remaining_sec(attempt, quiz)
            questions = await db.list_questions(int(quiz["id"]), db_path=db_path)
            answers = await db.get_attempt_answers(attempt_id, db_path=db_path)
            return EngineResponse(
                text=fmt.build_finish_confirm_text(len(answers), len(questions), remaining),
                keyboard=kb.finish_confirm_keyboard(attempt_id, int(attempt["current_index"])),
            )

        if sub == "fc":
            attempt_id = int(parts[2])
            await db.finalize_attempt(attempt_id, db_path=db_path)
            return await _render_attempt_result(attempt_id, db_path=db_path, toast="🎉 Test yakunlandi!")

        if sub == "res":
            return await _render_attempt_result(int(parts[2]), db_path=db_path)

        if sub == "r" and len(parts) >= 5:
            attempt_id = int(parts[2])
            idx = int(parts[3])
            wrong_only = parts[4] == "1"
            attempt = await db.get_attempt(attempt_id, db_path=db_path)
            if not attempt:
                return EngineResponse(text="❌ <b>Natija topilmadi.</b>", keyboard=kb.back_to_menu_keyboard())
            quiz = await db.get_quiz(int(attempt["quiz_id"]), db_path=db_path)
            assert quiz is not None
            items = await db.get_attempt_review_items(attempt_id, wrong_only=wrong_only, db_path=db_path)
            if not items:
                return await _render_attempt_result(
                    attempt_id,
                    db_path=db_path,
                    toast="🎉 Sizda birorta ham xato yo'q!",
                )
            safe_idx = max(0, min(idx, len(items) - 1))
            return EngineResponse(
                text=fmt.build_review_text(quiz, items[safe_idx], safe_idx, len(items), wrong_only),
                keyboard=kb.review_keyboard(attempt_id, safe_idx, len(items), 1 if wrong_only else 0),
            )

    if data == "rnd:s":
        quiz = await db.get_random_quiz(db_path=db_path)
        if not quiz:
            return EngineResponse(
                text="📭 <b>Hozircha tasodifiy test uchun savollar mavjud emas.</b>",
                keyboard=kb.back_to_menu_keyboard(),
            )
        return await render_quiz_info_by_id(int(quiz["id"]), db_path=db_path, toast="🎲 Tasodifiy test tanlandi!")

    if data == "code:p":
        return EngineResponse(
            text=(
                "🔑 <b>Test kodi orqali kirish</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Test kodini xabar sifatida yozib yuboring.\n\n"
                "💡 <i>Masalan:</i> <code>2000</code> (Falsafa — 175 ta savol)"
            ),
            keyboard=kb.back_to_menu_keyboard(),
            awaiting_input="code",
        )

    if data == "st:me":
        stats = await db.get_user_stats(telegram_id, db_path=db_path)
        assert stats is not None
        return EngineResponse(text=fmt.build_stats_text(stats), keyboard=kb.back_to_menu_keyboard())

    if action == "lb" and len(parts) >= 3 and parts[1] == "v":
        cat_id = int(parts[2])
        cats = await db.list_categories(active_only=True, db_path=db_path)
        active_cat = await db.get_category(cat_id, db_path=db_path) if cat_id > 0 else None
        leaders = await db.get_leaderboard(limit=10, category_id=(cat_id if cat_id > 0 else None), db_path=db_path)
        return EngineResponse(
            text=fmt.build_leaderboard_text(leaders, category=active_cat),
            keyboard=kb.leaderboard_keyboard(cats, cat_id if active_cat else 0),
        )

    if data == "hp:v":
        return EngineResponse(text=fmt.build_help_text(), keyboard=kb.back_to_menu_keyboard())

    if action == "adm":
        if not is_admin:
            return await render_main_menu(
                telegram_id, full_name, username, is_admin=False, db_path=db_path, toast="⛔️ Faqat adminlar uchun!"
            )
        sub = parts[1] if len(parts) > 1 else "m"
        if sub == "m":
            d_stats = await db.get_dashboard_stats(db_path=db_path)
            return EngineResponse(text=fmt.build_admin_menu_text(d_stats), keyboard=kb.admin_menu_keyboard())
        if sub == "quizzes":
            quizzes = await db.list_quizzes(active_only=False, db_path=db_path)
            lines = ["📚 <b>Barcha testlar ro'yxati:</b>\n━━━━━━━━━━━━━━━━━━━━"]
            for qz in quizzes:
                lines.append(
                    f"• {fmt.esc(qz['category_icon'])} <b>{fmt.esc(qz['title'])}</b> — Kod: <code>{fmt.esc(qz['code'])}</code> ({qz['question_count']} savol)"
                )
            return EngineResponse(
                text="\n".join(lines),
                keyboard=[[kb.btn("🔙 Admin Panel", "adm:m")]],
            )
        if sub == "bulk_pick":
            quizzes = await db.list_quizzes(active_only=False, db_path=db_path)
            return EngineResponse(
                text="📥 <b>Qaysi testga savollar qo'shmoqchisiz?</b>\nTanlang:",
                keyboard=kb.admin_quiz_pick_keyboard(quizzes, action_prefix="adm:bulk"),
            )
        if sub in {"add_cat", "add_quiz", "bulk"}:
            return EngineResponse(
                text=(
                    "🛠 <b>Admin amali</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Bot ichida /admin buyrug'i orqali bosqichma-bosqich qo'shishingiz "
                    "yoki chap tarafdagi <b>Admin Panel (Web UI)</b> dan yanada qulay tarzda boshqarishingiz mumkin!"
                ),
                keyboard=[[kb.btn("🔙 Admin Panel", "adm:m")]],
            )

    return await render_main_menu(telegram_id, full_name, username, is_admin=is_admin, db_path=db_path)


async def handle_text_message(
    telegram_id: int,
    full_name: str,
    username: str | None,
    text: str,
    is_admin: bool = False,
    db_path: Path | str | None = None,
) -> EngineResponse:
    """Process text commands (/start, /help, /stats, /top, /admin), quiz codes, and log chat history."""
    raw = (text or "").strip()
    await db.get_or_create_user(telegram_id, full_name, username, db_path=db_path)
    await db.log_chat_message(
        telegram_id=telegram_id,
        sender="user",
        content=raw or "/start",
        action_type="text",
        db_path=db_path,
    )
    resp = await _handle_text_message_inner(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username,
        raw=raw,
        is_admin=is_admin,
        db_path=db_path,
    )
    await db.log_chat_message(
        telegram_id=telegram_id,
        sender="bot",
        content=resp.text,
        action_type="reply",
        db_path=db_path,
    )
    return resp


async def _handle_text_message_inner(
    telegram_id: int,
    full_name: str,
    username: str | None,
    raw: str,
    is_admin: bool = False,
    db_path: Path | str | None = None,
) -> EngineResponse:
    if raw.startswith("/start"):
        args = raw.split(maxsplit=1)
        if len(args) == 2 and args[1].strip():
            code_quiz = await db.get_quiz_by_code(args[1].strip(), db_path=db_path)
            if code_quiz:
                return await render_quiz_info_by_id(int(code_quiz["id"]), db_path=db_path)
        return await render_main_menu(telegram_id, full_name, username, is_admin=is_admin, db_path=db_path)

    if raw.startswith("/help"):
        return EngineResponse(text=fmt.build_help_text(), keyboard=kb.back_to_menu_keyboard())

    if raw.startswith("/stats"):
        stats = await db.get_user_stats(telegram_id, db_path=db_path)
        assert stats is not None
        return EngineResponse(text=fmt.build_stats_text(stats), keyboard=kb.back_to_menu_keyboard())

    if raw.startswith("/top"):
        cats = await db.list_categories(active_only=True, db_path=db_path)
        leaders = await db.get_leaderboard(limit=10, db_path=db_path)
        return EngineResponse(
            text=fmt.build_leaderboard_text(leaders),
            keyboard=kb.leaderboard_keyboard(cats, 0),
        )

    if raw.startswith("/admin"):
        if not is_admin:
            return EngineResponse(
                text="⛔️ <b>Kechirasiz, sizda admin huquqi mavjud emas.</b>",
                keyboard=kb.back_to_menu_keyboard(),
            )
        d_stats = await db.get_dashboard_stats(db_path=db_path)
        return EngineResponse(text=fmt.build_admin_menu_text(d_stats), keyboard=kb.admin_menu_keyboard())

    # Check if text is a quiz code (e.g. "2000" or "2001")
    quiz = await db.get_quiz_by_code(raw, db_path=db_path)
    if quiz:
        return await render_quiz_info_by_id(int(quiz["id"]), db_path=db_path, toast=f"🔑 #{quiz['code']} testi topildi!")

    return EngineResponse(
        text=(
            f"🤔 <code>{fmt.esc(raw)}</code> bo'yicha test kodi topilmadi.\n\n"
            "Mavjud test kodini kiriting (masalan: <code>2000</code>) "
            "yoki quyidagi menyudan foydalaning:"
        ),
        keyboard=kb.main_menu_keyboard(is_admin=is_admin),
    )
