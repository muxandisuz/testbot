"""Transport-agnostic inline keyboard builders for both Aiogram and Web Simulator."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


ButtonSpec = dict[str, str]
KeyboardRows = list[list[ButtonSpec]]


def btn(text: str, callback_data: str) -> ButtonSpec:
    """Create a plain serializable inline button specification."""
    return {"text": text, "callback_data": callback_data}


def to_aiogram_markup(rows: KeyboardRows) -> InlineKeyboardMarkup:
    """Convert button rows into an Aiogram InlineKeyboardMarkup."""
    keyboard = [
        [
            InlineKeyboardButton(text=item["text"], callback_data=item["callback_data"])
            for item in row
        ]
        for row in rows
        if row
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def main_menu_keyboard(is_admin: bool = False) -> KeyboardRows:
    rows: KeyboardRows = [
        [btn("📝 Test ishlash", "c:list")],
        [btn("📊 Statistikam", "st:me"), btn("🏆 Reyting", "lb:v:0")],
        [btn("🔑 Kod orqali kirish", "code:p"), btn("ℹ️ Qoidalar", "hp:v")],
    ]
    if is_admin:
        rows.append([btn("⚙️ Admin Panel", "adm:m")])
    return rows


def categories_keyboard(categories: list[dict[str, Any]]) -> KeyboardRows:
    rows: KeyboardRows = []
    for cat in categories:
        q_cnt = int(cat.get("quiz_count", 0))
        label = f"{cat['icon']} {cat['name']} ({q_cnt} ta test)"
        rows.append([btn(label, f"c:v:{cat['id']}")])
    rows.append([btn("🔙 Bosh menyu", "m:main")])
    return rows


def quizzes_list_keyboard(quizzes: list[dict[str, Any]]) -> KeyboardRows:
    rows: KeyboardRows = []
    for qz in quizzes:
        icon = qz.get("category_icon") or "🦉"
        cnt = int(qz.get("question_count", 0))
        rows.append([btn(f"{icon} {qz['title']} ({cnt} ta savol)", f"qz:s:{qz['id']}:p")])
    rows.append([btn("🏠 Bosh menyu", "m:main")])
    return rows


def category_quizzes_keyboard(quizzes: list[dict[str, Any]], category_id: int) -> KeyboardRows:
    rows: KeyboardRows = []
    for qz in quizzes:
        icon = qz.get("category_icon") or "🦉"
        cnt = int(qz.get("question_count", 0))
        rows.append([btn(f"{icon} {qz['title']} ({cnt} ta savol)", f"qz:s:{qz['id']}:p")])
    rows.append([btn("⬅️ Fanlar", "c:list"), btn("🏠 Bosh menyu", "m:main")])
    return rows


def quiz_info_keyboard(quiz_id: int, category_id: int, question_count: int) -> KeyboardRows:
    rows: KeyboardRows = []
    if question_count > 0:
        rows.append([btn(f"▶️ Testni boshlash (1–{question_count})", f"qz:s:{quiz_id}:p")])
        rows.append([btn("🎓 Imtihon rejimi (taymer bilan)", f"qz:s:{quiz_id}:e")])
    rows.append([
        btn("⬅️ Testlar ro'yxati", f"c:v:{category_id}"),
        btn("🏠 Bosh menyu", "m:main"),
    ])
    return rows


def _short_opt_label(letter: str, text: str, prefix: str = "") -> str:
    clean = (text or "").strip().replace("\n", " ")
    if len(clean) > 16:
        clean = clean[:15] + "…"
    return f"{prefix}{letter}) {clean}"


def question_keyboard(
    attempt_id: int,
    question: dict[str, Any],
    index: int,
    total: int,
    mode: str,
    selected_option: str | None = None,
    answered_in_practice: bool = False,
) -> KeyboardRows:
    q_id = int(question["id"])
    rows: KeyboardRows = []

    if mode == "practice" and answered_in_practice:
        if index + 1 < total:
            rows.append([btn(f"➡️ Keyingi savol ({index + 2}-savol)", f"qz:n:{attempt_id}:{index + 1}")])
            rows.append([btn("🚪 Chiqish va testni yakunlash", f"qz:fc:{attempt_id}")])
        else:
            rows.append([btn("🏁 Testni yakunlash va natijani ko'rish", f"qz:fc:{attempt_id}")])
        return rows

    opt_map = [
        ("A", question["option_a"]),
        ("B", question["option_b"]),
        ("C", question["option_c"]),
        ("D", question["option_d"]),
    ]
    row1: list[ButtonSpec] = []
    row2: list[ButtonSpec] = []
    for idx_opt, (letter, text) in enumerate(opt_map):
        prefix = "🔵 " if (mode == "exam" and selected_option == letter) else ""
        b = btn(_short_opt_label(letter, text, prefix=prefix), f"qz:a:{attempt_id}:{q_id}:{letter}")
        if idx_opt < 2:
            row1.append(b)
        else:
            row2.append(b)
    rows.append(row1)
    rows.append(row2)

    if mode == "exam":
        nav_row: list[ButtonSpec] = []
        if index > 0:
            nav_row.append(btn("⬅️ Oldingi", f"qz:n:{attempt_id}:{index - 1}"))
        nav_row.append(btn("🗺 Xarita", f"qz:map:{attempt_id}"))
        if index + 1 < total:
            nav_row.append(btn("Keyingi ➡️", f"qz:n:{attempt_id}:{index + 1}"))
        rows.append(nav_row)
        rows.append([btn("🏁 Testni topshirish", f"qz:f:{attempt_id}")])
    else:
        if index + 1 < total:
            rows.append([btn("⏭ O'tkazib yuborish ➡️", f"qz:n:{attempt_id}:{index + 1}")])
        rows.append([btn("🚪 Chiqish va testni yakunlash", f"qz:fc:{attempt_id}")])

    return rows


def question_map_keyboard(
    attempt_id: int,
    questions: list[dict[str, Any]],
    answers: dict[int, dict[str, Any]],
    current_index: int,
    page: int = 0,
    per_page: int = 40,
) -> KeyboardRows:
    total = len(questions)
    total_pages = max(1, (total + per_page - 1) // per_page)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * per_page
    end = min(total, start + per_page)

    rows: KeyboardRows = []
    current_row: list[ButtonSpec] = []
    for idx in range(start, end):
        q = questions[idx]
        q_id = int(q["id"])
        is_answered = q_id in answers
        if idx == current_index:
            icon = "📍"
        elif is_answered:
            icon = "🔵"
        else:
            icon = "⚪️"
        current_row.append(btn(f"{idx + 1} {icon}", f"qz:n:{attempt_id}:{idx}"))
        if len(current_row) == 4:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    if total_pages > 1:
        pager: list[ButtonSpec] = []
        if safe_page > 0:
            pager.append(btn("⬅️ Oldingi", f"qz:map:{attempt_id}:{safe_page - 1}"))
        pager.append(btn(f"📄 {safe_page + 1}/{total_pages}", f"qz:map:{attempt_id}:{safe_page}"))
        if safe_page + 1 < total_pages:
            pager.append(btn("Keyingi ➡️", f"qz:map:{attempt_id}:{safe_page + 1}"))
        rows.append(pager)

    rows.append([
        btn("🔙 Savolga qaytish", f"qz:n:{attempt_id}:{current_index}"),
        btn("🏁 Topshirish", f"qz:f:{attempt_id}"),
    ])
    return rows


def finish_confirm_keyboard(attempt_id: int, current_index: int) -> KeyboardRows:
    return [
        [
            btn("✅ Ha, yakunlash", f"qz:fc:{attempt_id}"),
            btn("↩️ Testga qaytish", f"qz:n:{attempt_id}:{current_index}"),
        ]
    ]


def result_keyboard(attempt_id: int, quiz_id: int, has_mistakes: bool) -> KeyboardRows:
    rows: KeyboardRows = []
    review_row: list[ButtonSpec] = []
    if has_mistakes:
        review_row.append(btn("🔍 Xatolar tahlili", f"qz:r:{attempt_id}:0:1"))
    review_row.append(btn("📋 Barcha javoblar", f"qz:r:{attempt_id}:0:0"))
    rows.append(review_row)
    rows.append([
        btn("🔄 Shu testni qayta boshlash", f"qz:s:{quiz_id}:p"),
        btn("🏆 Reyting", "lb:v:0"),
    ])
    rows.append([btn("🏠 Bosh menyu", "m:main")])
    return rows


def review_keyboard(attempt_id: int, index: int, total: int, wrong_only: int) -> KeyboardRows:
    rows: KeyboardRows = []
    nav_row: list[ButtonSpec] = []
    if index > 0:
        nav_row.append(btn("⬅️ Oldingi", f"qz:r:{attempt_id}:{index - 1}:{wrong_only}"))
    if index + 1 < total:
        nav_row.append(btn("Keyingi ➡️", f"qz:r:{attempt_id}:{index + 1}:{wrong_only}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([
        btn("🔙 Natijaga qaytish", f"qz:res:{attempt_id}"),
        btn("🏠 Bosh menyu", "m:main"),
    ])
    return rows


def leaderboard_keyboard(categories: list[dict[str, Any]], active_cat_id: int) -> KeyboardRows:
    rows: KeyboardRows = [
        [btn(("• 🌍 Umumiy •" if active_cat_id == 0 else "🌍 Umumiy"), "lb:v:0")]
    ]
    row: list[ButtonSpec] = []
    for cat in categories[:6]:
        cid = int(cat["id"])
        label = f"• {cat['icon']} {cat['name']} •" if cid == active_cat_id else f"{cat['icon']} {cat['name']}"
        row.append(btn(label, f"lb:v:{cid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([btn("🏠 Bosh menyu", "m:main")])
    return rows


def back_to_menu_keyboard() -> KeyboardRows:
    return [[btn("🏠 Bosh menyu", "m:main")]]


def admin_menu_keyboard() -> KeyboardRows:
    return [
        [btn("➕ Yangi fan qo'shish", "adm:add_cat"), btn("📝 Yangi test yaratish", "adm:add_quiz")],
        [btn("📥 Tezkor savol import", "adm:bulk_pick"), btn("📚 Testlar ro'yxati", "adm:quizzes")],
        [btn("🏠 Bosh menyu", "m:main")],
    ]


def admin_quiz_pick_keyboard(quizzes: list[dict[str, Any]], action_prefix: str = "adm:bulk") -> KeyboardRows:
    rows: KeyboardRows = []
    for qz in quizzes[:10]:
        rows.append([btn(f"{qz['category_icon']} {qz['title']} (#{qz['code']})", f"{action_prefix}:{qz['id']}")])
    rows.append([btn("🔙 Admin Panel", "adm:m")])
    return rows
