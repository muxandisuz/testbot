"""Async SQLite database layer, schema initialization, and Uzbek quiz seed data."""

from __future__ import annotations

import random
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from config import get_settings
from falsafa_data import FALSAFA_QUESTIONS


def _resolve_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return get_settings().resolved_db_path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


@asynccontextmanager
async def get_db(db_path: Path | str | None = None) -> AsyncIterator[aiosqlite.Connection]:
    """Yield an async SQLite connection with row dict access and foreign keys enabled."""
    resolved = _resolve_db_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(resolved))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        await conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    username TEXT DEFAULT '',
    xp INTEGER NOT NULL DEFAULT 0,
    tests_completed INTEGER NOT NULL DEFAULT 0,
    correct_answers INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '📚',
    description TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'orta',
    time_limit_sec INTEGER NOT NULL DEFAULT 300,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option TEXT NOT NULL CHECK (correct_option IN ('A', 'B', 'C', 'D')),
    explanation TEXT NOT NULL DEFAULT '',
    points INTEGER NOT NULL DEFAULT 10,
    order_num INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    quiz_id INTEGER NOT NULL,
    mode TEXT NOT NULL DEFAULT 'practice' CHECK (mode IN ('practice', 'exam')),
    current_index INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    total_points INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    percentage REAL NOT NULL DEFAULT 0.0,
    duration_sec INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT DEFAULT NULL,
    is_completed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attempt_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    selected_option TEXT NOT NULL CHECK (selected_option IN ('A', 'B', 'C', 'D')),
    is_correct INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    UNIQUE (attempt_id, question_id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    telegram_id INTEGER NOT NULL,
    sender TEXT NOT NULL CHECK (sender IN ('user', 'bot', 'admin')),
    action_type TEXT NOT NULL DEFAULT 'text',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


async def init_db(db_path: Path | str | None = None) -> None:
    """Create database tables if needed, clean legacy non-Falsafa data, and seed Falsafa tests."""
    async with get_db(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    await cleanup_legacy_non_falsafa_data(db_path)
    await seed_database(db_path)
    await ensure_falsafa_seeded(db_path)
    await backfill_chat_history_if_needed(db_path)


async def cleanup_legacy_non_falsafa_data(db_path: Path | str | None = None) -> None:
    """Remove legacy non-Falsafa categories/quizzes, fake demo users, and 0-answer practice attempts."""
    legacy_codes = (
        "1001", "1002", "1003", "1004", "1005", "1006",
        "2001", "2002", "2003", "2004", "2005", "2006",
    )
    legacy_categories = (
        "Matematika",
        "Ingliz tili",
        "Python va IT",
        "O'zbekiston tarixi",
        "Mantiq va IQ",
    )
    async with get_db(db_path) as db:
        await db.execute(
            f"DELETE FROM quizzes WHERE code IN ({','.join('?' for _ in legacy_codes)})",
            legacy_codes,
        )
        await db.execute(
            f"DELETE FROM categories WHERE name IN ({','.join('?' for _ in legacy_categories)})",
            legacy_categories,
        )
        await db.execute(
            """
            DELETE FROM users
            WHERE telegram_id IN (700001, 700002, 700003, 700004, 700005, 999000111)
               OR username IN (
                   'sardor_dev', 'malika_edu', 'jasur_math', 'jasur_f',
                   'dilnoza_eng', 'dilnoza_f', 'aziz_iq', 'aziz_f',
                   'demo_user', 'simulator_user', 'web_user'
               )
            """
        )
        await db.execute(
            """
            DELETE FROM attempts
            WHERE mode = 'practice' AND is_completed = 1 AND correct_count = 0 AND wrong_count = 0
            """
        )
        await _sync_user_totals(db)
        await db.commit()


async def _sync_user_totals(db: aiosqlite.Connection, user_id: int | None = None) -> None:
    """Recompute cached tests_completed, correct_answers, and total_questions from completed attempts."""
    where_sql = "WHERE users.id = ?" if user_id is not None else ""
    params: tuple[Any, ...] = (user_id,) if user_id is not None else ()
    await db.execute(
        f"""
        UPDATE users
        SET tests_completed = (
                SELECT COUNT(*) FROM attempts a
                WHERE a.user_id = users.id AND a.is_completed = 1
            ),
            correct_answers = (
                SELECT COALESCE(SUM(a.correct_count), 0) FROM attempts a
                WHERE a.user_id = users.id AND a.is_completed = 1
            ),
            total_questions = (
                SELECT COALESCE(SUM(
                    CASE WHEN a.mode = 'practice' THEN (a.correct_count + a.wrong_count)
                         ELSE (a.correct_count + a.wrong_count + a.skipped_count)
                    END
                ), 0)
                FROM attempts a
                WHERE a.user_id = users.id AND a.is_completed = 1
            )
        {where_sql}
        """,
        params,
    )


async def get_admin_credentials(db_path: Path | str | None = None) -> tuple[str, str]:
    """Return active (login, password) for TestMaster Bot Studio, falling back to Settings."""
    settings = get_settings()
    login = settings.admin_login
    password = settings.admin_password
    async with get_db(db_path) as db:
        cur = await db.execute(
            "SELECT key, value FROM app_settings WHERE key IN ('admin_login', 'admin_password')"
        )
        rows = {str(r["key"]): str(r["value"]) for r in await cur.fetchall()}
    if rows.get("admin_login"):
        login = rows["admin_login"]
    if rows.get("admin_password"):
        password = rows["admin_password"]
    return login, password


async def set_admin_credentials(login: str, password: str, db_path: Path | str | None = None) -> None:
    """Persist Studio admin login and password in SQLite app_settings."""
    clean_login = login.strip()
    if not clean_login:
        raise ValueError("Login bo'sh bo'lishi mumkin emas.")
    if not password:
        raise ValueError("Parol bo'sh bo'lishi mumkin emas.")
    async with get_db(db_path) as db:
        for key, value in (("admin_login", clean_login), ("admin_password", password)):
            await db.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
        await db.commit()


async def seed_database(db_path: Path | str | None = None) -> None:
    """No-op: fake sample users are disabled."""
    return


async def ensure_falsafa_seeded(db_path: Path | str | None = None) -> None:
    """Idempotently seed the Falsafa va Mantiq category and the full 175-question Falsafa test."""
    async with get_db(db_path) as db:
        cat_cur = await db.execute(
            "SELECT id FROM categories WHERE name = ?",
            ("Falsafa va Mantiq",),
        )
        cat_row = await cat_cur.fetchone()
        if cat_row:
            cat_id = int(cat_row["id"])
        else:
            ins_cat = await db.execute(
                "INSERT INTO categories (name, icon, description, is_active) VALUES (?, ?, ?, 1)",
                (
                    "Falsafa va Mantiq",
                    "🦉",
                    "Falsafa fanidan yakuniy nazorat test savollari (175 ta savol)",
                ),
            )
            cat_id = int(ins_cat.lastrowid)

        now = _utc_now_iso()
        falsafa_quizzes = [
            (
                "2000",
                "Falsafa",
                "Falsafa fanidan yakuniy nazorat test savollari (1–175)",
                "orta",
                3600,
                FALSAFA_QUESTIONS,
            ),
        ]

        for code, title, desc, difficulty, time_limit, q_slice in falsafa_quizzes:
            existing = await db.execute("SELECT id, title, description FROM quizzes WHERE code = ?", (code,))
            ex_row = await existing.fetchone()
            if ex_row is not None:
                if ex_row["title"] != title or ex_row["description"] != desc:
                    await db.execute(
                        "UPDATE quizzes SET title = ?, description = ? WHERE id = ?",
                        (title, desc, int(ex_row["id"])),
                    )
                continue
            q_cur = await db.execute(
                """
                INSERT INTO quizzes (category_id, code, title, description, difficulty, time_limit_sec, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (cat_id, code, title, desc, difficulty, time_limit, now),
            )
            quiz_id = int(q_cur.lastrowid)
            await db.executemany(
                """
                INSERT INTO questions (
                    quiz_id, question_text, option_a, option_b, option_c, option_d,
                    correct_option, explanation, points, order_num
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 10, ?)
                """,
                [
                    (quiz_id, q_text, opt_a, opt_b, opt_c, opt_d, corr, expl, idx)
                    for idx, (q_text, opt_a, opt_b, opt_c, opt_d, corr, expl) in enumerate(q_slice, start=1)
                ],
            )

        await db.commit()


# ---------------------------------------------------------------------------
# Users & Stats
# ---------------------------------------------------------------------------

async def get_or_create_user(
    telegram_id: int,
    full_name: str,
    username: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Fetch user by telegram_id or create if missing, updating profile name if changed."""
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cur.fetchone()
        clean_name = (full_name or "Foydalanuvchi").strip() or "Foydalanuvchi"
        clean_uname = (username or "").strip()
        if row:
            user = dict(row)
            if user["full_name"] != clean_name or user["username"] != clean_uname:
                await db.execute(
                    "UPDATE users SET full_name = ?, username = ? WHERE id = ?",
                    (clean_name, clean_uname, user["id"]),
                )
                await db.commit()
                user["full_name"] = clean_name
                user["username"] = clean_uname
            return user

        now = _utc_now_iso()
        cur = await db.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, xp, tests_completed, correct_answers, total_questions, created_at)
            VALUES (?, ?, ?, 0, 0, 0, 0, ?)
            """,
            (telegram_id, clean_name, clean_uname, now),
        )
        await db.commit()
        cur2 = await db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,))
        created = await cur2.fetchone()
        return dict(created)


async def get_user_stats(telegram_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Return user record enriched with rank position, accuracy, and recent attempts."""
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cur.fetchone()
        if not row:
            return None
        user = dict(row)

        rank_cur = await db.execute(
            "SELECT COUNT(*) + 1 AS rank_pos FROM users WHERE telegram_id != 999000111 AND (xp > ? OR (xp = ? AND id < ?))",
            (user["xp"], user["xp"], user["id"]),
        )
        rank_row = await rank_cur.fetchone()
        user["rank_pos"] = int(rank_row["rank_pos"]) if rank_row else 1

        total_users_cur = await db.execute("SELECT COUNT(*) AS cnt FROM users WHERE telegram_id != 999000111")
        total_users_row = await total_users_cur.fetchone()
        user["total_users"] = max(1, int(total_users_row["cnt"]) if total_users_row else 1)

        tq = user["total_questions"] or 0
        user["accuracy"] = round((user["correct_answers"] / tq) * 100, 1) if tq > 0 else 0.0

        att_cur = await db.execute(
            """
            SELECT a.*, q.title AS quiz_title, q.code AS quiz_code
            FROM attempts a
            JOIN quizzes q ON q.id = a.quiz_id
            WHERE a.user_id = ? AND a.is_completed = 1
            ORDER BY a.finished_at DESC, a.id DESC
            LIMIT 5
            """,
            (user["id"],),
        )
        user["recent_attempts"] = [dict(r) for r in await att_cur.fetchall()]
        return user


async def get_leaderboard(
    limit: int = 10,
    category_id: int | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return top users globally by XP or within a specific category."""
    async with get_db(db_path) as db:
        if category_id is None:
            cur = await db.execute(
                """
                SELECT id, telegram_id, full_name, username, xp, tests_completed, correct_answers, total_questions
                FROM users
                WHERE telegram_id != 999000111 AND (xp > 0 OR tests_completed > 0)
                ORDER BY xp DESC, tests_completed DESC, id ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [dict(r) for r in await cur.fetchall()]
            for r in rows:
                tq = r["total_questions"] or 0
                r["accuracy"] = round((r["correct_answers"] / tq) * 100, 1) if tq > 0 else 0.0
            return rows

        cur = await db.execute(
            """
            SELECT
                u.id,
                u.telegram_id,
                u.full_name,
                u.username,
                COALESCE(SUM(a.score), 0) AS category_score,
                COUNT(a.id) AS category_tests,
                COALESCE(ROUND(AVG(a.percentage), 1), 0) AS avg_percentage,
                u.xp
            FROM attempts a
            JOIN users u ON u.id = a.user_id
            JOIN quizzes q ON q.id = a.quiz_id
            WHERE a.is_completed = 1 AND q.category_id = ? AND u.telegram_id != 999000111
            GROUP BY u.id
            ORDER BY category_score DESC, avg_percentage DESC, category_tests DESC
            LIMIT ?
            """,
            (category_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


def _enrich_user_dict(row: aiosqlite.Row | dict[str, Any]) -> dict[str, Any]:
    user = dict(row)
    tq = int(user.get("total_questions") or 0)
    ca = int(user.get("correct_answers") or 0)
    user["accuracy"] = round((ca / tq) * 100, 1) if tq > 0 else 0.0
    return user


async def list_users(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Return all registered real Telegram/Web users with attempt counts and accuracy."""
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            SELECT
                u.*,
                (
                    SELECT COUNT(*) FROM attempts a
                    WHERE a.user_id = u.id AND a.is_completed = 1
                      AND NOT (a.mode = 'practice' AND a.correct_count = 0 AND a.wrong_count = 0)
                ) AS attempts_count
            FROM users u
            WHERE u.telegram_id != 999000111
            ORDER BY u.xp DESC, u.id DESC
            """
        )
        return [_enrich_user_dict(r) for r in await cur.fetchall()]


async def get_user_by_id(user_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch a single user row by internal primary key ID."""
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            SELECT
                u.*,
                (
                    SELECT COUNT(*) FROM attempts a
                    WHERE a.user_id = u.id AND a.is_completed = 1
                      AND NOT (a.mode = 'practice' AND a.correct_count = 0 AND a.wrong_count = 0)
                ) AS attempts_count
            FROM users u
            WHERE u.id = ?
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        return _enrich_user_dict(row) if row else None


async def create_user(
    telegram_id: int,
    full_name: str,
    username: str = "",
    xp: int = 0,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a user record manually from the Admin Studio."""
    clean_name = (full_name or "").strip()
    if not clean_name:
        raise ValueError("Foydalanuvchi ismi bo'sh bo'lishi mumkin emas.")
    clean_uname = (username or "").strip().lstrip("@")
    async with get_db(db_path) as db:
        dup = await db.execute("SELECT 1 FROM users WHERE telegram_id = ?", (int(telegram_id),))
        if await dup.fetchone() is not None:
            raise ValueError(f"Telegram ID {telegram_id} allaqachon mavjud.")
        cur = await db.execute(
            """
            INSERT INTO users (telegram_id, full_name, username, xp, tests_completed, correct_answers, total_questions, created_at)
            VALUES (?, ?, ?, ?, 0, 0, 0, ?)
            """,
            (int(telegram_id), clean_name, clean_uname, max(0, int(xp)), _utc_now_iso()),
        )
        await db.commit()
        user_id = int(cur.lastrowid)
    created = await get_user_by_id(user_id, db_path=db_path)
    assert created is not None
    return created


async def update_user(
    user_id: int,
    full_name: str,
    username: str,
    telegram_id: int,
    xp: int,
    tests_completed: int,
    correct_answers: int,
    total_questions: int,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update editable user profile fields and stats from Admin Studio."""
    clean_name = (full_name or "").strip()
    if not clean_name:
        raise ValueError("Foydalanuvchi ismi bo'sh bo'lishi mumkin emas.")
    clean_uname = (username or "").strip().lstrip("@")
    async with get_db(db_path) as db:
        dup = await db.execute(
            "SELECT 1 FROM users WHERE telegram_id = ? AND id != ?",
            (int(telegram_id), user_id),
        )
        if await dup.fetchone() is not None:
            raise ValueError(f"Telegram ID {telegram_id} boshqa foydalanuvchiga biriktirilgan.")
        cur = await db.execute(
            """
            UPDATE users
            SET telegram_id = ?, full_name = ?, username = ?, xp = ?,
                tests_completed = ?, correct_answers = ?, total_questions = ?
            WHERE id = ?
            """,
            (
                int(telegram_id),
                clean_name,
                clean_uname,
                max(0, int(xp)),
                max(0, int(tests_completed)),
                max(0, int(correct_answers)),
                max(0, int(total_questions)),
                user_id,
            ),
        )
        await db.commit()
        if cur.rowcount == 0:
            return None
    return await get_user_by_id(user_id, db_path=db_path)


async def reset_user_stats(user_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Delete a user's completed/active attempts and reset all score counters to 0."""
    async with get_db(db_path) as db:
        await db.execute("DELETE FROM attempts WHERE user_id = ?", (user_id,))
        cur = await db.execute(
            """
            UPDATE users
            SET xp = 0, tests_completed = 0, correct_answers = 0, total_questions = 0
            WHERE id = ?
            """,
            (user_id,),
        )
        await db.commit()
        if cur.rowcount == 0:
            return None
    return await get_user_by_id(user_id, db_path=db_path)


async def delete_user(user_id: int, db_path: Path | str | None = None) -> bool:
    """Permanently delete a user record and cascade-delete their attempts."""
    async with get_db(db_path) as db:
        cur = await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

async def list_categories(active_only: bool = True, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """List categories with quiz and question counts."""
    where_clause = "WHERE c.is_active = 1" if active_only else ""
    async with get_db(db_path) as db:
        cur = await db.execute(
            f"""
            SELECT
                c.*,
                COUNT(DISTINCT CASE WHEN q.is_active = 1 THEN q.id END) AS quiz_count,
                COUNT(CASE WHEN q.is_active = 1 AND qs.id IS NOT NULL THEN qs.id END) AS question_count
            FROM categories c
            LEFT JOIN quizzes q ON q.category_id = c.id
            LEFT JOIN questions qs ON qs.quiz_id = q.id
            {where_clause}
            GROUP BY c.id
            ORDER BY c.id ASC
            """
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_category(category_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_category(
    name: str,
    icon: str = "📚",
    description: str = "",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    async with get_db(db_path) as db:
        cur = await db.execute(
            "INSERT INTO categories (name, icon, description, is_active) VALUES (?, ?, ?, 1)",
            (name.strip(), (icon or "📚").strip(), (description or "").strip()),
        )
        await db.commit()
        cur2 = await db.execute("SELECT * FROM categories WHERE id = ?", (cur.lastrowid,))
        return dict(await cur2.fetchone())


async def update_category(
    category_id: int,
    name: str,
    icon: str = "📚",
    description: str = "",
    is_active: bool = True,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update a category's name, icon, description, and active flag."""
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            UPDATE categories
            SET name = ?, icon = ?, description = ?, is_active = ?
            WHERE id = ?
            """,
            (name.strip(), (icon or "📚").strip(), (description or "").strip(), 1 if is_active else 0, category_id),
        )
        await db.commit()
        if cur.rowcount == 0:
            return None
    return await get_category(category_id, db_path=db_path)


async def delete_category(category_id: int, db_path: Path | str | None = None) -> bool:
    async with get_db(db_path) as db:
        cur = await db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        await db.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Quizzes
# ---------------------------------------------------------------------------

async def _generate_unique_quiz_code(db: aiosqlite.Connection) -> str:
    for _ in range(100):
        candidate = str(random.randint(1000, 9999))
        cur = await db.execute("SELECT 1 FROM quizzes WHERE code = ?", (candidate,))
        if await cur.fetchone() is None:
            return candidate
    return str(random.randint(10000, 99999))


async def list_quizzes(
    category_id: int | None = None,
    active_only: bool = True,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List quizzes with category info, question counts, and attempt counts."""
    conditions: list[str] = []
    params: list[Any] = []
    if active_only:
        conditions.append("q.is_active = 1")
    if category_id is not None:
        conditions.append("q.category_id = ?")
        params.append(category_id)
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db(db_path) as db:
        cur = await db.execute(
            f"""
            SELECT
                q.*,
                c.name AS category_name,
                c.icon AS category_icon,
                COUNT(DISTINCT qs.id) AS question_count,
                COALESCE(SUM(qs.points), 0) AS total_points,
                (SELECT COUNT(*) FROM attempts a WHERE a.quiz_id = q.id AND a.is_completed = 1) AS attempt_count
            FROM quizzes q
            JOIN categories c ON c.id = q.category_id
            LEFT JOIN questions qs ON qs.quiz_id = q.id
            {where_sql}
            GROUP BY q.id
            ORDER BY q.id ASC
            """,
            params,
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_quiz(quiz_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            SELECT
                q.*,
                c.name AS category_name,
                c.icon AS category_icon,
                COUNT(DISTINCT qs.id) AS question_count,
                COALESCE(SUM(qs.points), 0) AS total_points
            FROM quizzes q
            JOIN categories c ON c.id = q.category_id
            LEFT JOIN questions qs ON qs.quiz_id = q.id
            WHERE q.id = ?
            GROUP BY q.id
            """,
            (quiz_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_quiz_by_code(code: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    clean = (code or "").strip().upper()
    if not clean:
        return None
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            SELECT
                q.*,
                c.name AS category_name,
                c.icon AS category_icon,
                COUNT(DISTINCT qs.id) AS question_count,
                COALESCE(SUM(qs.points), 0) AS total_points
            FROM quizzes q
            JOIN categories c ON c.id = q.category_id
            LEFT JOIN questions qs ON qs.quiz_id = q.id
            WHERE UPPER(q.code) = ? AND q.is_active = 1
            GROUP BY q.id
            """,
            (clean,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_random_quiz(db_path: Path | str | None = None) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            SELECT q.id
            FROM quizzes q
            JOIN questions qs ON qs.quiz_id = q.id
            WHERE q.is_active = 1
            GROUP BY q.id
            HAVING COUNT(qs.id) > 0
            ORDER BY RANDOM()
            LIMIT 1
            """
        )
        row = await cur.fetchone()
        if not row:
            return None
        quiz_id = int(row["id"])
    return await get_quiz(quiz_id, db_path=db_path)


async def create_quiz(
    category_id: int,
    title: str,
    code: str | None = None,
    description: str = "",
    difficulty: str = "orta",
    time_limit_sec: int = 300,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    diff = (difficulty or "orta").strip().lower()
    if diff not in {"oson", "orta", "qiyin"}:
        diff = "orta"
    time_limit = max(30, int(time_limit_sec or 300))

    async with get_db(db_path) as db:
        final_code = (code or "").strip().upper()
        if not final_code:
            final_code = await _generate_unique_quiz_code(db)
        else:
            existing = await db.execute("SELECT 1 FROM quizzes WHERE UPPER(code) = ?", (final_code,))
            if await existing.fetchone() is not None:
                raise ValueError(f"'{final_code}' kodi allaqachon mavjud. Boshqa kod tanlang.")

        now = _utc_now_iso()
        cur = await db.execute(
            """
            INSERT INTO quizzes (category_id, code, title, description, difficulty, time_limit_sec, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (category_id, final_code, title.strip(), (description or "").strip(), diff, time_limit, now),
        )
        await db.commit()
        quiz_id = int(cur.lastrowid)
    return await get_quiz(quiz_id, db_path=db_path)  # type: ignore[return-value]


async def update_quiz(
    quiz_id: int,
    category_id: int,
    title: str,
    code: str,
    description: str = "",
    difficulty: str = "orta",
    time_limit_sec: int = 300,
    is_active: bool = True,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update quiz metadata while enforcing unique quiz code."""
    clean_code = (code or "").strip().upper()
    if not clean_code:
        raise ValueError("Test kodi bo'sh bo'lishi mumkin emas.")
    diff = (difficulty or "orta").strip().lower()
    if diff not in {"oson", "orta", "qiyin"}:
        diff = "orta"
    time_limit = max(30, int(time_limit_sec or 300))

    async with get_db(db_path) as db:
        existing = await db.execute(
            "SELECT 1 FROM quizzes WHERE UPPER(code) = ? AND id != ?",
            (clean_code, quiz_id),
        )
        if await existing.fetchone() is not None:
            raise ValueError(f"'{clean_code}' kodi allaqachon mavjud. Boshqa kod tanlang.")
        cur = await db.execute(
            """
            UPDATE quizzes
            SET category_id = ?, code = ?, title = ?, description = ?,
                difficulty = ?, time_limit_sec = ?, is_active = ?
            WHERE id = ?
            """,
            (
                category_id,
                clean_code,
                title.strip(),
                (description or "").strip(),
                diff,
                time_limit,
                1 if is_active else 0,
                quiz_id,
            ),
        )
        await db.commit()
        if cur.rowcount == 0:
            return None
    return await get_quiz(quiz_id, db_path=db_path)


async def delete_quiz(quiz_id: int, db_path: Path | str | None = None) -> bool:
    async with get_db(db_path) as db:
        cur = await db.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
        await db.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

async def list_questions(quiz_id: int, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    async with get_db(db_path) as db:
        cur = await db.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY order_num ASC, id ASC",
            (quiz_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_question(question_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_question(
    quiz_id: int,
    question_text: str,
    option_a: str,
    option_b: str,
    option_c: str,
    option_d: str,
    correct_option: str,
    explanation: str = "",
    points: int = 10,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    corr = (correct_option or "").strip().upper()
    if corr not in {"A", "B", "C", "D"}:
        raise ValueError("To'g'ri javob faqat A, B, C yoki D bo'lishi kerak.")

    async with get_db(db_path) as db:
        order_cur = await db.execute(
            "SELECT COALESCE(MAX(order_num), 0) + 1 AS next_order FROM questions WHERE quiz_id = ?",
            (quiz_id,),
        )
        next_order = int((await order_cur.fetchone())["next_order"])
        cur = await db.execute(
            """
            INSERT INTO questions (
                quiz_id, question_text, option_a, option_b, option_c, option_d,
                correct_option, explanation, points, order_num
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quiz_id,
                question_text.strip(),
                option_a.strip(),
                option_b.strip(),
                option_c.strip(),
                option_d.strip(),
                corr,
                (explanation or "").strip(),
                max(1, int(points or 10)),
                next_order,
            ),
        )
        await db.commit()
        cur2 = await db.execute("SELECT * FROM questions WHERE id = ?", (cur.lastrowid,))
        return dict(await cur2.fetchone())


def _parse_hash_plus_blocks(raw_text: str) -> tuple[list[tuple[str, str, str, str, str, str, str]], list[str]]:
    """
    Parse '# Savol' / '+ A.' block format:
    # Savol matni?
    + A. To'g'ri variant
    B. Noto'g'ri variant
    C. Noto'g'ri variant
    D. Noto'g'ri variant
    """
    lines = [re.sub(r"\s+", " ", line).strip() for line in (raw_text or "").splitlines() if line.strip()]
    blocks: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in lines:
        if line.startswith("#"):
            if cur is not None:
                blocks.append(cur)
            cur = {"q": line.lstrip("#").strip(), "raw": []}
        elif cur is not None:
            cur["raw"].append(line)
    if cur is not None:
        blocks.append(cur)

    opt_start_re = re.compile(r"^(\+?\s*[A-Da-d][\.\)]|-\s*)")
    opt_prefix_re = re.compile(r"^(?:\+?\s*[A-Da-d][\.\)]\s*|\+\s*|-\s*)")
    parsed: list[tuple[str, str, str, str, str, str, str]] = []
    errors: list[str] = []

    for idx, b in enumerate(blocks, start=1):
        q_text = str(b["q"])
        opts: list[str] = []
        for line in b["raw"]:
            if not opts and not opt_start_re.match(line):
                q_text = f"{q_text} {line}".strip()
            elif opts and not opt_start_re.match(line):
                opts[-1] = f"{opts[-1]} {line}".strip()
            else:
                opts.append(line)

        if len(opts) != 4:
            errors.append(f"{idx}-savol: 4 ta variant bo'lishi kerak (topildi: {len(opts)}).")
            continue

        corr = ""
        cleaned_opts: list[str] = []
        for o_idx, o_line in enumerate(opts):
            if o_line.lstrip().startswith("+") and not corr:
                corr = ["A", "B", "C", "D"][o_idx]
            cleaned = opt_prefix_re.sub("", o_line).strip()
            cleaned_opts.append(cleaned)

        if not corr:
            errors.append(f"{idx}-savol: to'g'ri javob '+' belgisi bilan ajratilmagan.")
            continue
        if not q_text or not all(cleaned_opts):
            errors.append(f"{idx}-savol: savol matni yoki variantlardan biri bo'sh.")
            continue

        parsed.append((q_text, cleaned_opts[0], cleaned_opts[1], cleaned_opts[2], cleaned_opts[3], corr, ""))

    return parsed, errors


async def bulk_create_questions(
    quiz_id: int,
    raw_text: str,
    db_path: Path | str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse either pipe-delimited lines:
      Savol | A | B | C | D | To'g'ri harf | Izoh (ixtiyoriy)
    or '# Savol' / '+ A.' blocks.
    """
    created: list[dict[str, Any]] = []
    errors: list[str] = []
    lines = [line.strip() for line in (raw_text or "").splitlines() if line.strip()]
    if not lines:
        return created, errors

    if any(line.startswith("#") for line in lines) and "|" not in lines[0]:
        parsed_blocks, errors = _parse_hash_plus_blocks(raw_text)
        for q_text, opt_a, opt_b, opt_c, opt_d, corr, explanation in parsed_blocks:
            q_row = await create_question(
                quiz_id=quiz_id,
                question_text=q_text,
                option_a=opt_a,
                option_b=opt_b,
                option_c=opt_c,
                option_d=opt_d,
                correct_option=corr,
                explanation=explanation,
                db_path=db_path,
            )
            created.append(q_row)
        return created, errors

    for line_no, line in enumerate(lines, start=1):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            errors.append(f"{line_no}-qator: kamida 6 ta bo'lim ('|') bo'lishi kerak.")
            continue
        q_text, opt_a, opt_b, opt_c, opt_d, corr = parts[:6]
        explanation = parts[6] if len(parts) > 6 else ""
        corr = corr.upper()
        if corr not in {"A", "B", "C", "D"}:
            errors.append(f"{line_no}-qator: to'g'ri javob '{corr}' noto'g'ri (A/B/C/D bo'lishi kerak).")
            continue
        if not all([q_text, opt_a, opt_b, opt_c, opt_d]):
            errors.append(f"{line_no}-qator: savol yoki variantlardan biri bo'sh.")
            continue
        q_row = await create_question(
            quiz_id=quiz_id,
            question_text=q_text,
            option_a=opt_a,
            option_b=opt_b,
            option_c=opt_c,
            option_d=opt_d,
            correct_option=corr,
            explanation=explanation,
            db_path=db_path,
        )
        created.append(q_row)
    return created, errors


async def update_question(
    question_id: int,
    question_text: str,
    option_a: str,
    option_b: str,
    option_c: str,
    option_d: str,
    correct_option: str,
    explanation: str = "",
    points: int = 10,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Update a question's text, four options, correct letter, explanation, and points."""
    corr = (correct_option or "").strip().upper()
    if corr not in {"A", "B", "C", "D"}:
        raise ValueError("To'g'ri javob faqat A, B, C yoki D bo'lishi kerak.")
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            UPDATE questions
            SET question_text = ?, option_a = ?, option_b = ?, option_c = ?, option_d = ?,
                correct_option = ?, explanation = ?, points = ?
            WHERE id = ?
            """,
            (
                question_text.strip(),
                option_a.strip(),
                option_b.strip(),
                option_c.strip(),
                option_d.strip(),
                corr,
                (explanation or "").strip(),
                max(1, int(points or 10)),
                question_id,
            ),
        )
        await db.commit()
        if cur.rowcount == 0:
            return None
    return await get_question(question_id, db_path=db_path)


async def delete_question(question_id: int, db_path: Path | str | None = None) -> bool:
    async with get_db(db_path) as db:
        cur = await db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        await db.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Attempts & Answers
# ---------------------------------------------------------------------------

async def create_attempt(
    user_id: int,
    quiz_id: int,
    mode: str = "practice",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    clean_mode = "exam" if mode == "exam" else "practice"
    async with get_db(db_path) as db:
        now = _utc_now_iso()
        cur = await db.execute(
            """
            INSERT INTO attempts (user_id, quiz_id, mode, current_index, started_at, is_completed)
            VALUES (?, ?, ?, 0, ?, 0)
            """,
            (user_id, quiz_id, clean_mode, now),
        )
        await db.commit()
        cur2 = await db.execute("SELECT * FROM attempts WHERE id = ?", (cur.lastrowid,))
        return dict(await cur2.fetchone())


async def get_attempt(attempt_id: int, db_path: Path | str | None = None) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_attempt_index(
    attempt_id: int,
    current_index: int,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE attempts SET current_index = ? WHERE id = ?",
            (max(0, int(current_index)), attempt_id),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_attempt_answers(attempt_id: int, db_path: Path | str | None = None) -> dict[int, dict[str, Any]]:
    async with get_db(db_path) as db:
        cur = await db.execute(
            "SELECT * FROM attempt_answers WHERE attempt_id = ?",
            (attempt_id,),
        )
        rows = await cur.fetchall()
        return {int(r["question_id"]): dict(r) for r in rows}


async def save_attempt_answer(
    attempt_id: int,
    question_id: int,
    selected_option: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Save or update a user's selected option for a question in an active attempt."""
    opt = (selected_option or "").strip().upper()
    if opt not in {"A", "B", "C", "D"}:
        raise ValueError("Variant A, B, C yoki D bo'lishi kerak.")

    async with get_db(db_path) as db:
        q_cur = await db.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        q_row = await q_cur.fetchone()
        if not q_row:
            raise ValueError("Savol topilmadi.")
        question = dict(q_row)
        is_correct = 1 if question["correct_option"] == opt else 0

        await db.execute(
            """
            INSERT INTO attempt_answers (attempt_id, question_id, selected_option, is_correct)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(attempt_id, question_id) DO UPDATE SET
                selected_option = excluded.selected_option,
                is_correct = excluded.is_correct
            """,
            (attempt_id, question_id, opt, is_correct),
        )
        await db.commit()
        return {
            "attempt_id": attempt_id,
            "question_id": question_id,
            "selected_option": opt,
            "is_correct": bool(is_correct),
            "correct_option": question["correct_option"],
            "explanation": question["explanation"],
        }


async def finalize_attempt(
    attempt_id: int,
    duration_sec: int | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Calculate final scores, mark attempt completed, and award XP idempotently."""
    async with get_db(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        att_cur = await db.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,))
        att_row = await att_cur.fetchone()
        if not att_row:
            await db.rollback()
            raise ValueError("Test urinishi topilmadi.")
        attempt = dict(att_row)

        if attempt["is_completed"]:
            await db.commit()
            return attempt

        q_cur = await db.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY order_num ASC, id ASC",
            (attempt["quiz_id"],),
        )
        questions = [dict(r) for r in await q_cur.fetchall()]

        ans_cur = await db.execute(
            "SELECT * FROM attempt_answers WHERE attempt_id = ?",
            (attempt_id,),
        )
        answers = {int(r["question_id"]): dict(r) for r in await ans_cur.fetchall()}

        total_points = sum(int(q["points"]) for q in questions)
        score = 0
        correct_count = 0
        wrong_count = 0
        skipped_count = 0

        for q in questions:
            ans = answers.get(int(q["id"]))
            if ans is None:
                skipped_count += 1
            elif ans["is_correct"]:
                correct_count += 1
                score += int(q["points"])
            else:
                wrong_count += 1

        total_q = len(questions)
        answered_count = correct_count + wrong_count
        is_practice = attempt["mode"] == "practice"
        evaluated_q = answered_count if is_practice else total_q
        percentage = round((correct_count / evaluated_q) * 100, 1) if evaluated_q > 0 else 0.0

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        if duration_sec is not None:
            computed_duration = max(1, int(duration_sec))
        else:
            started_dt = _parse_iso(attempt["started_at"])
            if started_dt:
                computed_duration = max(1, int((now_dt - started_dt).total_seconds()))
            else:
                computed_duration = 1

        await db.execute(
            """
            UPDATE attempts
            SET score = ?, total_points = ?, correct_count = ?, wrong_count = ?,
                skipped_count = ?, percentage = ?, duration_sec = ?,
                finished_at = ?, is_completed = 1
            WHERE id = ?
            """,
            (
                score,
                total_points,
                correct_count,
                wrong_count,
                skipped_count,
                percentage,
                computed_duration,
                now_iso,
                attempt_id,
            ),
        )

        bonus_xp = 20 if percentage >= 80 and evaluated_q > 0 else 0
        earned_xp = score + bonus_xp
        tests_inc = 1 if evaluated_q > 0 else 0
        await db.execute(
            """
            UPDATE users
            SET xp = xp + ?,
                tests_completed = tests_completed + ?,
                correct_answers = correct_answers + ?,
                total_questions = total_questions + ?
            WHERE id = ?
            """,
            (earned_xp, tests_inc, correct_count, evaluated_q, attempt["user_id"]),
        )
        await db.commit()

        updated_cur = await db.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,))
        result = dict(await updated_cur.fetchone())
        result["earned_xp"] = earned_xp
        result["bonus_xp"] = bonus_xp
        return result


async def get_attempt_review_items(
    attempt_id: int,
    wrong_only: bool = False,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return questions in an attempt along with user's selected option and correctness."""
    async with get_db(db_path) as db:
        att_cur = await db.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,))
        att = await att_cur.fetchone()
        if not att:
            return []

        q_cur = await db.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY order_num ASC, id ASC",
            (att["quiz_id"],),
        )
        questions = [dict(r) for r in await q_cur.fetchall()]

        ans_cur = await db.execute(
            "SELECT * FROM attempt_answers WHERE attempt_id = ?",
            (attempt_id,),
        )
        answers = {int(r["question_id"]): dict(r) for r in await ans_cur.fetchall()}

        max_answered_num = max(
            (idx for idx, q in enumerate(questions, start=1) if int(q["id"]) in answers),
            default=0,
        )

        items: list[dict[str, Any]] = []
        for idx, q in enumerate(questions, start=1):
            ans = answers.get(int(q["id"]))
            selected = ans["selected_option"] if ans else None
            is_correct = bool(ans["is_correct"]) if ans else False
            if wrong_only:
                if is_correct:
                    continue
                if len(answers) > 0 and ans is None and idx > max_answered_num:
                    continue
            items.append(
                {
                    "number": idx,
                    "question": q,
                    "selected_option": selected,
                    "is_correct": is_correct,
                }
            )
        return items


async def get_dashboard_stats(db_path: Path | str | None = None) -> dict[str, Any]:
    """Return aggregated metrics and recent completed attempts for the Web Dashboard."""
    async with get_db(db_path) as db:
        counts = {}
        u_cur = await db.execute("SELECT COUNT(*) AS cnt FROM users WHERE telegram_id != 999000111")
        counts["users_count"] = int((await u_cur.fetchone())["cnt"])
        for key, table in [
            ("categories_count", "categories"),
            ("quizzes_count", "quizzes"),
            ("questions_count", "questions"),
        ]:
            cur = await db.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
            counts[key] = int((await cur.fetchone())["cnt"])

        att_cur = await db.execute(
            """
            SELECT
                COUNT(*) AS completed_attempts,
                COALESCE(ROUND(AVG(a.percentage), 1), 0.0) AS avg_percentage
            FROM attempts a
            JOIN users u ON u.id = a.user_id
            WHERE a.is_completed = 1
              AND u.telegram_id != 999000111
              AND NOT (a.mode = 'practice' AND a.correct_count = 0 AND a.wrong_count = 0)
            """
        )
        att_row = await att_cur.fetchone()
        counts["attempts_count"] = int(att_row["completed_attempts"]) if att_row else 0
        counts["avg_percentage"] = float(att_row["avg_percentage"]) if att_row else 0.0

        recent_cur = await db.execute(
            """
            SELECT
                a.id, a.mode, a.score, a.total_points, a.correct_count,
                a.wrong_count, a.skipped_count, a.percentage, a.duration_sec,
                a.finished_at,
                u.full_name AS user_name,
                u.username AS username,
                q.title AS quiz_title,
                q.code AS quiz_code
            FROM attempts a
            JOIN users u ON u.id = a.user_id
            JOIN quizzes q ON q.id = a.quiz_id
            WHERE a.is_completed = 1
              AND u.telegram_id != 999000111
              AND NOT (a.mode = 'practice' AND a.correct_count = 0 AND a.wrong_count = 0)
            ORDER BY a.finished_at DESC, a.id DESC
            LIMIT 10
            """
        )
        counts["recent_attempts"] = [dict(r) for r in await recent_cur.fetchall()]
        return counts


async def delete_attempt(attempt_id: int, db_path: Path | str | None = None) -> bool:
    """Delete an attempt and re-sync the owner's tests_completed, correct_answers, and total_questions."""
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT user_id FROM attempts WHERE id = ?", (attempt_id,))
        row = await cur.fetchone()
        if not row:
            return False
        user_id = int(row["user_id"])
        await db.execute("DELETE FROM attempts WHERE id = ?", (attempt_id,))
        await _sync_user_totals(db, user_id=user_id)
        await db.commit()
        return True


async def clear_all_attempts(db_path: Path | str | None = None) -> int:
    """Delete all quiz attempts and reset all users' XP and question counters to zero."""
    async with get_db(db_path) as db:
        cur = await db.execute("DELETE FROM attempts")
        deleted_count = max(0, int(cur.rowcount or 0))
        await db.execute(
            "UPDATE users SET xp = 0, tests_completed = 0, correct_answers = 0, total_questions = 0"
        )
        await db.commit()
        return deleted_count


# ---------------------------------------------------------------------------
# User Chat History & Attempts History
# ---------------------------------------------------------------------------

async def backfill_chat_history_if_needed(db_path: Path | str | None = None) -> None:
    """Populate initial chat history for pre-existing users who have not yet been logged in chat_messages."""
    async with get_db(db_path) as db:
        flag_cur = await db.execute(
            "SELECT value FROM app_settings WHERE key = 'chat_history_backfilled'"
        )
        if await flag_cur.fetchone():
            return

        users_cur = await db.execute(
            "SELECT * FROM users WHERE telegram_id != 999000111 ORDER BY id ASC"
        )
        users = [dict(r) for r in await users_cur.fetchall()]

        for u in users:
            uid = int(u["id"])
            tid = int(u["telegram_id"])
            cnt_cur = await db.execute(
                "SELECT COUNT(*) AS cnt FROM chat_messages WHERE user_id = ?",
                (uid,),
            )
            if int((await cnt_cur.fetchone())["cnt"]) > 0:
                continue

            created_ts = u.get("created_at") or _utc_now_iso()
            await db.execute(
                """
                INSERT INTO chat_messages (user_id, telegram_id, sender, action_type, content, created_at)
                VALUES (?, ?, 'user', 'text', '/start', ?)
                """,
                (uid, tid, created_ts),
            )
            await db.execute(
                """
                INSERT INTO chat_messages (user_id, telegram_id, sender, action_type, content, created_at)
                VALUES (?, ?, 'bot', 'reply', ?, ?)
                """,
                (
                    uid,
                    tid,
                    f"🦉 <b>Falsafa Test Botga xush kelibsiz!</b>\n👤 Foydalanuvchi: <b>{u['full_name']}</b>",
                    created_ts,
                ),
            )

            att_cur = await db.execute(
                """
                SELECT a.*, q.title AS quiz_title, q.code AS quiz_code
                FROM attempts a
                JOIN quizzes q ON q.id = a.quiz_id
                WHERE a.user_id = ?
                ORDER BY a.id ASC
                """,
                (uid,),
            )
            for att in await att_cur.fetchall():
                a = dict(att)
                started_ts = a.get("started_at") or created_ts
                mode_label = "Mashq rejimi" if a["mode"] == "practice" else "Imtihon rejimi"
                await db.execute(
                    """
                    INSERT INTO chat_messages (user_id, telegram_id, sender, action_type, content, created_at)
                    VALUES (?, ?, 'user', 'callback', ?, ?)
                    """,
                    (
                        uid,
                        tid,
                        f"▶️ Test boshlandi: {a['quiz_title']} (#{a['quiz_code']} · {mode_label})",
                        started_ts,
                    ),
                )
                if a["is_completed"]:
                    fin_ts = a.get("finished_at") or started_ts
                    await db.execute(
                        """
                        INSERT INTO chat_messages (user_id, telegram_id, sender, action_type, content, created_at)
                        VALUES (?, ?, 'bot', 'reply', ?, ?)
                        """,
                        (
                            uid,
                            tid,
                            (
                                f"🎉 <b>Test yakunlandi — {a['quiz_title']}</b>\n"
                                f"📊 Natija: <b>{a['percentage']}%</b> "
                                f"(✅ To'g'ri: {a['correct_count']} · ❌ Xato: {a['wrong_count']} · ⏭ O'tkazilgan: {a['skipped_count']})"
                            ),
                            fin_ts,
                        ),
                    )

        await db.execute(
            """
            INSERT INTO app_settings (key, value) VALUES ('chat_history_backfilled', '1')
            ON CONFLICT(key) DO UPDATE SET value = '1'
            """
        )
        await db.commit()


async def log_chat_message(
    telegram_id: int,
    sender: str,
    content: str,
    action_type: str = "text",
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Record a single chat message ('user', 'bot', or 'admin') in chat_messages."""
    if sender not in {"user", "bot", "admin"}:
        raise ValueError("Invalid sender type")
    clean_content = (content or "").strip()
    if not clean_content:
        return None

    async with get_db(db_path) as db:
        u_cur = await db.execute(
            "SELECT id, telegram_id FROM users WHERE telegram_id = ?",
            (int(telegram_id),),
        )
        u_row = await u_cur.fetchone()
        if not u_row:
            return None
        user_id = int(u_row["id"])
        now_iso = _utc_now_iso()
        cur = await db.execute(
            """
            INSERT INTO chat_messages (user_id, telegram_id, sender, action_type, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, int(telegram_id), sender, action_type, clean_content, now_iso),
        )
        msg_id = int(cur.lastrowid)
        await db.commit()
        row_cur = await db.execute("SELECT * FROM chat_messages WHERE id = ?", (msg_id,))
        row = await row_cur.fetchone()
        return dict(row) if row else None


async def list_user_chat_history(
    user_id: int,
    limit: int = 200,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return chronological chat history messages for a user (up to the most recent `limit` rows)."""
    safe_limit = max(1, min(int(limit), 1000))
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            SELECT * FROM (
                SELECT id, user_id, telegram_id, sender, action_type, content, created_at
                FROM chat_messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) sub
            ORDER BY id ASC
            """,
            (int(user_id), safe_limit),
        )
        return [dict(r) for r in await cur.fetchall()]


async def list_user_attempts(
    user_id: int,
    limit: int = 30,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Return recent quiz attempts for a specific user."""
    safe_limit = max(1, min(int(limit), 200))
    async with get_db(db_path) as db:
        cur = await db.execute(
            """
            SELECT
                a.id, a.quiz_id, a.mode, a.score, a.total_points,
                a.correct_count, a.wrong_count, a.skipped_count,
                a.percentage, a.duration_sec, a.started_at, a.finished_at, a.is_completed,
                q.title AS quiz_title, q.code AS quiz_code
            FROM attempts a
            JOIN quizzes q ON q.id = a.quiz_id
            WHERE a.user_id = ?
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (int(user_id), safe_limit),
        )
        return [dict(r) for r in await cur.fetchall()]


async def clear_user_chat_history(
    user_id: int,
    db_path: Path | str | None = None,
) -> int:
    """Delete all stored chat history rows for a user and return deleted row count."""
    async with get_db(db_path) as db:
        cur = await db.execute("DELETE FROM chat_messages WHERE user_id = ?", (int(user_id),))
        deleted = max(0, int(cur.rowcount or 0))
        await db.commit()
        return deleted
