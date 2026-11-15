"""HTML card formatters, progress bars, rank badges, and visual helpers for Telegram UI."""

from __future__ import annotations

import html
from typing import Any


def esc(value: Any) -> str:
    """Escape text safely for Telegram HTML parse_mode."""
    return html.escape(str(value or ""), quote=False)


def render_progress_bar(current: int, total: int, width: int = 10, show_percent: bool = True) -> str:
    """Render a crisp Unicode block progress bar like ▰▰▰▰▱▱▱▱▱▱ 40%."""
    if total <= 0:
        bar = "▱" * width
        return f"{bar} 0%" if show_percent else bar
    ratio = max(0.0, min(1.0, current / total))
    filled = round(ratio * width)
    pct = round(ratio * 100)
    bar = f"{'▰' * filled}{'▱' * (width - filled)}"
    return f"{bar} {pct}%" if show_percent else bar


def get_rank_badge(xp: int) -> str:
    """Return an Uzbek achievement rank badge based on user XP."""
    if xp >= 700:
        return "👑 Grossmeyster"
    if xp >= 300:
        return "🔥 Ekspert"
    if xp >= 100:
        return "⚡️ Bilimdon"
    return "🌱 Boshlovchi"


def get_difficulty_badge(diff: str) -> str:
    mapping = {
        "oson": "🟢 Oson",
        "orta": "🟡 O'rta",
        "qiyin": "🔴 Qiyin",
    }
    return mapping.get((diff or "orta").lower(), "🟡 O'rta")


def format_duration(seconds: int) -> str:
    """Format seconds as MM:SS."""
    sec = max(0, int(seconds))
    mins, rem = divmod(sec, 60)
    return f"{mins:02d}:{rem:02d}"


def build_welcome_text(user: dict[str, Any], accuracy: float) -> str:
    rank = get_rank_badge(int(user.get("xp", 0)))
    return (
        "🦉 <b>Falsafa Test Botga xush kelibsiz!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Foydalanuvchi: <b>{esc(user.get('full_name'))}</b>\n"
        f"🏅 Daraja: <b>{rank}</b> · <code>{int(user.get('xp', 0))} XP</code>\n"
        f"📊 Ishlangan testlar: <b>{int(user.get('tests_completed', 0))} ta</b> · Aniqlik: <b>{accuracy}%</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 <b>Test ishlash</b> tugmasini bosing — mavjud test nomi chiqadi, ustiga bosib <b>1-savoldan 175-savolgacha</b> ishlang.\n"
        "✅ Har bir javobdan so'ng to'g'ri yoki noto'g'ri ekani darhol ko'rsatiladi.\n"
        "🚪 Istalgan savolda <b>Chiqish va testni yakunlash</b> tugmasi orqali testni tugatishingiz mumkin."
    )


def build_quizzes_list_text(quizzes: list[dict[str, Any]]) -> str:
    if not quizzes:
        return (
            "📝 <b>Mavjud testlar</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📭 Hozircha faol testlar mavjud emas."
        )
    total_questions = sum(int(q.get("question_count", 0)) for q in quizzes)
    lines = [
        "📝 <b>Testlar ro'yxati</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Jami <b>{len(quizzes)} ta</b> test · <b>{total_questions} ta</b> savol.",
        "",
        "👇 Test ishlash uchun quyidagi test nomini bosing:",
    ]
    return "\n".join(lines)


def build_categories_text(categories: list[dict[str, Any]]) -> str:
    total_quizzes = sum(int(c.get("quiz_count", 0)) for c in categories)
    total_questions = sum(int(c.get("question_count", 0)) for c in categories)
    return (
        "📚 <b>Fanlar va Yo'nalishlar</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Jami <b>{len(categories)} ta</b> fan, <b>{total_quizzes} ta</b> test va <b>{total_questions} ta</b> savol mavjud.\n\n"
        "👇 O'zingizga kerakli fanni tanlang:"
    )


def build_category_quizzes_text(category: dict[str, Any], quizzes: list[dict[str, Any]]) -> str:
    if not quizzes:
        return (
            f"{esc(category['icon'])} <b>{esc(category['name'])}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📭 Ushbu fanda hozircha faol testlar yo'q."
        )
    lines = [
        f"{esc(category['icon'])} <b>{esc(category['name'])}</b>",
        f"<i>{esc(category.get('description', ''))}</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        "👇 Ishlamoqchi bo'lgan testni tanlang:",
    ]
    return "\n".join(lines)


def build_quiz_info_text(quiz: dict[str, Any]) -> str:
    q_count = int(quiz.get("question_count", 0))
    total_pts = int(quiz.get("total_points", 0))
    diff_badge = get_difficulty_badge(quiz.get("difficulty", "orta"))
    time_fmt = format_duration(int(quiz.get("time_limit_sec", 300)))
    return (
        f"{esc(quiz.get('category_icon', '🦉'))} <b>{esc(quiz['title'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 Fan: <b>{esc(quiz.get('category_name', ''))}</b>\n"
        f"🔑 Test kodi: <code>{esc(quiz['code'])}</code>\n"
        f"📈 Qiyinlik: {diff_badge}\n"
        f"❓ Savollar soni: <b>{q_count} ta</b> (Maks: <b>{total_pts} ball</b>)\n"
        f"⏱ Ajratilgan vaqt: <b>{time_fmt}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <i>{esc(quiz.get('description') or 'Barcha savollarga diqqat bilan javob bering.')}</i>\n\n"
        f"▶️ <b>Testni boshlash (1–{q_count})</b> — 1-savoldan oxirigacha ketma-ket ishlaydi, har bir javob darhol tekshiriladi va istalgan savolda yakunlash mumkin."
    )


def build_question_text(
    quiz: dict[str, Any],
    question: dict[str, Any],
    index: int,
    total: int,
    mode: str,
    remaining_sec: int,
    answered_count: int,
    selected_option: str | None = None,
    practice_feedback: dict[str, Any] | None = None,
    correct_so_far: int = 0,
    wrong_so_far: int = 0,
) -> str:
    mode_badge = "▶️ Ketma-ket test" if mode == "practice" else "🎓 Imtihon rejimi"
    progress = render_progress_bar(index + 1, total)
    time_str = format_duration(remaining_sec)

    header = (
        f"📝 <b>{esc(quiz['title'])}</b>  |  {mode_badge}\n"
        f"📊 Savol <b>{index + 1}/{total}</b>  {progress}\n"
    )
    if mode == "exam":
        header += f"⏱ Qolgan vaqt: <b>{time_str}</b>  ·  Belgilangan: <b>{answered_count}/{total}</b>\n"
    else:
        header += f"✅ To'g'ri: <b>{correct_so_far}</b>  ·  ❌ Noto'g'ri: <b>{wrong_so_far}</b>  ·  ⏱ <b>{time_str}</b>\n"

    opts = [
        ("A", question["option_a"]),
        ("B", question["option_b"]),
        ("C", question["option_c"]),
        ("D", question["option_d"]),
    ]

    option_lines: list[str] = []
    corr_letter = (question.get("correct_option") or "").strip().upper()
    for letter, opt_text in opts:
        marker = ""
        if practice_feedback is not None:
            corr = practice_feedback["correct_option"]
            picked = practice_feedback["selected_option"]
            if letter == corr:
                marker = "✅ "
            elif letter == picked and picked != corr:
                marker = "❌ "
        elif mode == "exam" and selected_option == letter:
            marker = "🔵 "
        suffix = " ✅" if letter == corr_letter else ""
        option_lines.append(f"{marker}<b>{letter})</b> {esc(opt_text)}{suffix}")

    body = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{index + 1}. {esc(question['question_text'])}</b>\n\n"
        + "\n".join(option_lines)
    )

    footer = ""
    if practice_feedback is not None:
        pts = int(question.get("points", 10))
        if practice_feedback["is_correct"]:
            footer = f"\n\n✅ <b>To'g'ri javob!</b> (+{pts} ball)"
        else:
            footer = (
                f"\n\n❌ <b>Noto'g'ri javob!</b> "
                f"Sizning javobingiz: <b>{practice_feedback['selected_option']}</b> · "
                f"To'g'ri javob: <b>{practice_feedback['correct_option']}</b>"
            )
        expl = (practice_feedback.get("explanation") or "").strip()
        if expl:
            footer += f"\n💡 <b>Izoh:</b> <i>{esc(expl)}</i>"

    return header + body + footer


def build_question_map_text(
    quiz: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: dict[int, dict[str, Any]],
    remaining_sec: int,
) -> str:
    answered = len(answers)
    total = len(questions)
    return (
        f"🗺 <b>Savollar xaritasi — {esc(quiz['title'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Qolgan vaqt: <b>{format_duration(remaining_sec)}</b>\n"
        f"📌 Belgilangan savollar: <b>{answered} / {total}</b>\n\n"
        "📍 — Joriy savol  |  🔵 — Javob belgilangan  |  ⚪️ — Bo'sh\n"
        "👇 O'tmoqchi bo'lgan savol raqamini bosing:"
    )


def build_finish_confirm_text(answered: int, total: int, remaining_sec: int) -> str:
    unanswered = max(0, total - answered)
    warning = (
        f"⚠️ Sizda hali <b>{unanswered} ta</b> javob berilmagan savol bor!\n\n"
        if unanswered > 0
        else "✅ Barcha savollarga javob berdingiz!\n\n"
    )
    return (
        "🏁 <b>Testni yakunlashni tasdiqlaysizmi?</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Javob berilgan: <b>{answered} / {total}</b>\n"
        f"⏱ Qolgan vaqt: <b>{format_duration(remaining_sec)}</b>\n\n"
        f"{warning}"
        "Yakunlagandan so'ng natijangiz hisoblanadi va XP qo'shiladi."
    )


def build_result_text(
    quiz: dict[str, Any],
    attempt: dict[str, Any],
    review_items: list[dict[str, Any]],
    auto_expired: bool = False,
) -> str:
    pct = float(attempt.get("percentage", 0.0))
    if pct >= 90:
        medal = "🏆 A'lo natija! (Oltin medal)"
    elif pct >= 70:
        medal = "🥈 Yaxshi natija! (Kumush medal)"
    elif pct >= 50:
        medal = "🥉 Qoniqarli natija (Bronza medal)"
    else:
        medal = "📚 Yana mashq qiling!"

    bar = render_progress_bar(round(pct), 100, show_percent=False)
    score = int(attempt.get("score", 0))
    total_pts = int(attempt.get("total_points", 0))
    correct_c = int(attempt.get("correct_count", 0))
    wrong_c = int(attempt.get("wrong_count", 0))
    skip_c = int(attempt.get("skipped_count", 0))
    total_q = len(review_items)
    answered_c = correct_c + wrong_c
    dur = format_duration(int(attempt.get("duration_sec", 0)))
    bonus_xp = 20 if pct >= 80 and answered_c > 0 else 0
    earned_xp = int(attempt.get("earned_xp", score + bonus_xp))

    last_answered_idx = max(
        (i for i, item in enumerate(review_items) if item["selected_option"] is not None),
        default=-1,
    )
    if last_answered_idx >= 0:
        visible_items = review_items[: last_answered_idx + 1]
    else:
        visible_items = review_items[:10]

    map_tokens: list[str] = []
    truncated_prefix = False
    if len(visible_items) > 50:
        visible_items = visible_items[-50:]
        truncated_prefix = True
    for item in visible_items:
        num = item["number"]
        if item["selected_option"] is None:
            map_tokens.append(f"{num}.⏭")
        elif item["is_correct"]:
            map_tokens.append(f"{num}.✅")
        else:
            map_tokens.append(f"{num}.❌")
    map_line = ("...  " if truncated_prefix else "") + "  ".join(map_tokens)

    timeout_banner = "⏰ <b>Ajratilgan vaqt tugadi! Test avtomatik yakunlandi.</b>\n\n" if auto_expired else ""
    bonus_note = " (shu jumladan +20 bonus!)" if bonus_xp > 0 else ""

    return (
        f"{timeout_banner}"
        f"🎉 <b>Test yakunlandi — {esc(quiz['title'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏅 Baho: <b>{medal}</b>\n"
        f"📊 Natija: <code>{bar}</code> <b>{pct}%</b>\n\n"
        f"📌 Ishlangan savollar: <b>{answered_c} / {total_q}</b>\n"
        f"✅ To'g'ri javoblar: <b>{correct_c}</b>\n"
        f"❌ Noto'g'ri javoblar: <b>{wrong_c}</b>\n"
        f"⏭ Qolgan (ishlanmagan): <b>{skip_c}</b>\n"
        f"💎 Ball: <b>{score} / {total_pts}</b>\n"
        f"⏱ Sarflangan vaqt: <b>{dur}</b>\n"
        f"⚡️ Qo'shilgan tajriba: <b>+{earned_xp} XP</b>{bonus_note}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🗺 <b>Savollar xaritasi:</b>\n<code>{map_line}</code>"
    )


def build_review_text(
    quiz: dict[str, Any],
    item: dict[str, Any],
    index: int,
    total_items: int,
    wrong_only: bool,
) -> str:
    q = item["question"]
    selected = item["selected_option"]
    is_corr = item["is_correct"]
    title = "🔍 Xatolar tahlili" if wrong_only else "📋 Barcha javoblar tahlili"
    status = "✅ To'g'ri" if is_corr else ("⏭ Javob berilmagan" if selected is None else "❌ Noto'g'ri")

    opts = [
        ("A", q["option_a"]),
        ("B", q["option_b"]),
        ("C", q["option_c"]),
        ("D", q["option_d"]),
    ]
    opt_lines: list[str] = []
    for letter, text in opts:
        tag = ""
        if letter == q["correct_option"]:
            tag = "✅ "
        elif letter == selected and not is_corr:
            tag = "❌ "
        opt_lines.append(f"{tag}<b>{letter})</b> {esc(text)}")

    expl = (q.get("explanation") or "").strip() or "Izoh kiritilmagan."

    return (
        f"{title} ({index + 1}/{total_items})\n"
        f"📝 <b>{esc(quiz['title'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{item['number']}-savol:</b> {esc(q['question_text'])}\n\n"
        + "\n".join(opt_lines)
        + "\n━━━━━━━━━━━━━━━━━━━━\n"
        f"Holat: <b>{status}</b>\n"
        f"Sizning javobingiz: <b>{selected or '—'}</b>  |  To'g'ri javob: <b>{q['correct_option']}</b>\n"
        f"💡 <b>Izoh:</b> <i>{esc(expl)}</i>"
    )


def build_stats_text(stats: dict[str, Any]) -> str:
    xp = int(stats.get("xp", 0))
    rank = get_rank_badge(xp)
    recent = stats.get("recent_attempts") or []
    recent_lines: list[str] = []
    for att in recent:
        mode_icon = "⚡️" if att["mode"] == "practice" else "🎓"
        recent_lines.append(
            f"• {mode_icon} <b>{esc(att['quiz_title'])}</b> — {att['percentage']}% ({att['correct_count']}/{att['correct_count'] + att['wrong_count'] + att['skipped_count']})"
        )
    recent_block = "\n".join(recent_lines) if recent_lines else "<i>Hali birorta test yakunlanmagan.</i>"

    return (
        "📊 <b>Shaxsiy Statistika va Profil</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Ism: <b>{esc(stats.get('full_name'))}</b>\n"
        f"🏅 Daraja: <b>{rank}</b>\n"
        f"⚡️ Umumiy tajriba: <b>{xp} XP</b>\n"
        f"🏆 Umumiy reytingdagi o'rni: <b>#{stats.get('rank_pos', 1)}</b> / {stats.get('total_users', 1)}\n"
        f"📝 Yakunlangan testlar: <b>{stats.get('tests_completed', 0)} ta</b>\n"
        f"🎯 To'g'ri javoblar: <b>{stats.get('correct_answers', 0)} / {stats.get('total_questions', 0)}</b> (<b>{stats.get('accuracy', 0)}%</b>)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🕒 <b>Oxirgi natijalar:</b>\n"
        f"{recent_block}"
    )


def build_leaderboard_text(
    leaders: list[dict[str, Any]],
    category: dict[str, Any] | None = None,
) -> str:
    header = (
        f"🏆 <b>Eng yaxshi ishtirokchilar — {esc(category['icon'])} {esc(category['name'])}</b>\n"
        if category
        else "🏆 <b>Umumiy Reyting (Top 10)</b>\n"
    )
    medals = ["🥇", "🥈", "🥉"]
    lines: list[str] = []
    for idx, row in enumerate(leaders, start=1):
        place = medals[idx - 1] if idx <= 3 else f"<b>{idx}.</b>"
        name = esc(row["full_name"])
        if category:
            lines.append(
                f"{place} {name} — <b>{int(row['category_score'])} ball</b> ({row['avg_percentage']}%, {row['category_tests']} ta test)"
            )
        else:
            rank = get_rank_badge(int(row["xp"]))
            lines.append(
                f"{place} {name} — <b>{int(row['xp'])} XP</b> · {rank} ({row['tests_completed']} ta test)"
            )
    body = "\n".join(lines) if lines else "<i>Ushbu fan bo'yicha hali natijalar yo'q. Birinchi bo'ling!</i>"
    return f"{header}━━━━━━━━━━━━━━━━━━━━\n{body}"


def build_help_text() -> str:
    return (
        "ℹ️ <b>Falsafa Test Bot — Qo'llanma va Qoidalar</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ <b>Test ishlash:</b> Asosiy menyudan <b>📝 Test ishlash</b> tugmasini bosing va chiqqan test nomini (<b>🦉 Falsafa</b>) tanlang.\n"
        "2️⃣ <b>1 dan oxirigacha va darhol tekshirish:</b> Savollar 1-dan 175-gacha ketma-ket chiqadi; har bir javobingizdan so'ng ✅ to'g'ri yoki ❌ noto'g'ri ekani darhol ko'rsatiladi.\n"
        "3️⃣ <b>Istalgan payt yakunlash:</b> Istalgan savolga kelganda <b>🚪 Chiqish va testni yakunlash</b> tugmasini bosib testni tugatish va natijangizni ko'rish mumkin.\n"
        "4️⃣ <b>Kod orqali kirish:</b> Test kodini (masalan, <code>2000</code>) chatga yuborishingiz ham mumkin.\n"
        "5️⃣ <b>XP va Darajalar:</b>\n"
        "   • Har bir to'g'ri javob uchun <b>+10 XP</b>\n"
        "   • 80%+ natija uchun qo'shimcha <b>+20 Bonus XP</b>\n"
        "   • 🌱 0-99 · ⚡️ 100-299 · 🔥 300-699 · 👑 700+ XP\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Buyruqlar: /start · /stats · /top · /help · /admin"
    )


def build_admin_menu_text(stats: dict[str, Any]) -> str:
    return (
        "⚙️ <b>Admin Boshqaruv Paneli</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 Fanlar: <b>{stats.get('categories_count', 0)}</b>  |  "
        f"📝 Testlar: <b>{stats.get('quizzes_count', 0)}</b>\n"
        f"❓ Savollar: <b>{stats.get('questions_count', 0)}</b>  |  "
        f"👥 Foydalanuvchilar: <b>{stats.get('users_count', 0)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Yangi fan, test yoki savollarni bot ichidan yoki Web Admin paneldan qo'shishingiz mumkin."
    )
