"""End-to-end automated tests for Falsafa-only DB, test-name menu, sequential 1-to-end quiz engine, early exit, and Web UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
import database as db
from bot import engine
from web.app import app


def _assert_all_callbacks_under_64_bytes(keyboard: list[list[dict[str, str]]]) -> None:
    for row in keyboard:
        for button in row:
            cb = button["callback_data"]
            assert len(cb.encode("utf-8")) <= 64, f"Callback data exceeds 64 bytes: {cb}"


@pytest.mark.asyncio
async def test_falsafa_only_seed_cleanup_and_html_escaping(tmp_path: Path) -> None:
    db_file = tmp_path / "test_seed.db"
    await db.init_db(db_file)

    cats = await db.list_categories(db_path=db_file)
    quizzes = await db.list_quizzes(db_path=db_file)
    leaders = await db.get_leaderboard(db_path=db_file)

    assert len(cats) == 1
    assert cats[0]["name"] == "Falsafa va Mantiq"
    assert len(quizzes) == 1
    assert quizzes[0]["code"] == "2000"
    assert quizzes[0]["title"] == "Falsafa"
    assert quizzes[0]["question_count"] == 175
    assert len(leaders) == 0

    # Verify legacy categories, split sub-quizzes, and fake users get cleaned up automatically on init_db
    await db.get_or_create_user(700001, "Sardorbek Alimov", "sardor_dev", db_path=db_file)
    old_cat = await db.create_category("Matematika", "📐", "Eski fan", db_path=db_file)
    await db.create_quiz(int(old_cat["id"]), "Algebra", code="1001", db_path=db_file)
    await db.create_quiz(int(cats[0]["id"]), "Falsafa 1-qism", code="2001", db_path=db_file)
    await db.init_db(db_file)
    cats_after = await db.list_categories(db_path=db_file)
    assert len(cats_after) == 1
    assert await db.get_quiz_by_code("1001", db_path=db_file) is None
    assert await db.get_quiz_by_code("2001", db_path=db_file) is None
    assert await db.get_user_stats(700001, db_path=db_file) is None

    # Verify HTML angle brackets in questions/options are escaped cleanly
    falsafa_cat = cats_after[0]
    html_quiz = await db.create_quiz(int(falsafa_cat["id"]), "HTML Test", code="9001", db_path=db_file)
    await db.create_question(
        int(html_quiz["id"]),
        "Quyidagi <tag> nima?",
        "<class 'int'>",
        "<class 'str'>",
        "Option C",
        "Option D",
        "A",
        db_path=db_file,
    )
    att_resp = await engine.handle_callback(111222, "Ali", "ali", f"qz:s:{html_quiz['id']}:p", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(att_resp.keyboard)
    assert "&lt;tag&gt;" in att_resp.text
    assert "&lt;class 'int'&gt;" in att_resp.text
    assert "<class 'int'>" not in att_resp.text


@pytest.mark.asyncio
async def test_test_ishlash_shows_test_name_and_runs_sequential_with_early_exit(tmp_path: Path) -> None:
    db_file = tmp_path / "test_seq.db"
    await db.init_db(db_file)

    menu_resp = await engine.handle_text_message(555000, "Sardor", "sardor", "/start", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(menu_resp.keyboard)
    assert any(b["text"] == "📝 Test ishlash" and b["callback_data"] == "c:list" for row in menu_resp.keyboard for b in row)

    # Clicking "📝 Test ishlash" displays the test name button "🦉 Falsafa (175 ta savol)"
    list_resp = await engine.handle_callback(555000, "Sardor", "sardor", "c:list", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(list_resp.keyboard)
    assert "Testlar ro'yxati" in list_resp.text
    falsafa_btn = next(
        (b for row in list_resp.keyboard for b in row if b["text"] == "🦉 Falsafa (175 ta savol)"),
        None,
    )
    assert falsafa_btn is not None

    # Clicking the test name button starts Question 1/175 sequentially
    q1_resp = await engine.handle_callback(555000, "Sardor", "sardor", falsafa_btn["callback_data"], db_path=db_file)
    _assert_all_callbacks_under_64_bytes(q1_resp.keyboard)
    assert "Savol <b>1/175</b>" in q1_resp.text
    assert any(b["text"].startswith("🚪 Chiqish") for row in q1_resp.keyboard for b in row)

    quiz_2000 = await db.get_quiz_by_code("2000", db_path=db_file)
    assert quiz_2000 is not None
    questions = await db.list_questions(int(quiz_2000["id"]), db_path=db_file)
    att_id = int(q1_resp.keyboard[0][0]["callback_data"].split(":")[2])
    q1_corr = questions[0]["correct_option"]
    assert any(
        line.startswith(f"<b>{q1_corr})</b>") and line.endswith(" ✅")
        for line in q1_resp.text.splitlines()
    )
    assert any(
        b["callback_data"].endswith(f":{q1_corr}") and b["text"].endswith(" ✅")
        for row in q1_resp.keyboard
        for b in row
    )

    # Answer Q1 wrong -> instant wrong feedback + Next + Exit buttons
    wrong_opt = "A" if questions[0]["correct_option"] != "A" else "B"
    ans1 = await engine.handle_callback(
        555000, "Sardor", "sardor", f"qz:a:{att_id}:{questions[0]['id']}:{wrong_opt}", db_path=db_file
    )
    _assert_all_callbacks_under_64_bytes(ans1.keyboard)
    assert "Noto'g'ri javob!" in ans1.text
    assert f"To'g'ri javob: <b>{questions[0]['correct_option']}</b>" in ans1.text
    assert "❌ Noto'g'ri: <b>1</b>" in ans1.text
    assert any(b["callback_data"] == f"qz:n:{att_id}:1" for row in ans1.keyboard for b in row)
    assert any(b["callback_data"] == f"qz:fc:{att_id}" for row in ans1.keyboard for b in row)

    # Move sequentially to Q2 and answer right
    q2_resp = await engine.handle_callback(555000, "Sardor", "sardor", f"qz:n:{att_id}:1", db_path=db_file)
    assert "Savol <b>2/175</b>" in q2_resp.text
    ans2 = await engine.handle_callback(
        555000, "Sardor", "sardor", f"qz:a:{att_id}:{questions[1]['id']}:{questions[1]['correct_option']}", db_path=db_file
    )
    assert "To'g'ri javob!" in ans2.text
    assert "✅ To'g'ri: <b>1</b>" in ans2.text

    # Move sequentially to Q3 and answer right
    q3_resp = await engine.handle_callback(555000, "Sardor", "sardor", f"qz:n:{att_id}:2", db_path=db_file)
    assert "Savol <b>3/175</b>" in q3_resp.text
    ans3 = await engine.handle_callback(
        555000, "Sardor", "sardor", f"qz:a:{att_id}:{questions[2]['id']}:{questions[2]['correct_option']}", db_path=db_file
    )
    assert "To'g'ri javob!" in ans3.text
    assert "✅ To'g'ri: <b>2</b>" in ans3.text

    # Exit and finish immediately on Q3
    res1 = await engine.handle_callback(555000, "Sardor", "sardor", f"qz:fc:{att_id}", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(res1.keyboard)
    assert "Ishlangan savollar: <b>3 / 175</b>" in res1.text
    assert "✅ To'g'ri javoblar: <b>2</b>" in res1.text
    assert "❌ Noto'g'ri javoblar: <b>1</b>" in res1.text
    assert "66.7%" in res1.text
    assert "4.⏭" not in res1.text  # trailing unanswered items hidden from map

    # Second finalize must not double award XP
    await db.finalize_attempt(att_id, db_path=db_file)
    stats = await db.get_user_stats(555000, db_path=db_file)
    assert stats is not None
    assert stats["xp"] == 20
    assert stats["tests_completed"] == 1
    assert stats["total_questions"] == 3

    # Mistake review shows only the 1 wrong question
    rev = await engine.handle_callback(555000, "Sardor", "sardor", f"qz:r:{att_id}:0:1", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(rev.keyboard)
    assert "Xatolar tahlili (1/1)" in rev.text


@pytest.mark.asyncio
async def test_practice_mode_and_mistake_review(tmp_path: Path) -> None:
    db_file = tmp_path / "test_practice.db"
    await db.init_db(db_file)

    cats = await db.list_categories(db_path=db_file)
    quiz = await db.create_quiz(int(cats[0]["id"]), "Falsafa Amaliy", code="3001", db_path=db_file)
    sample_qs = await db.list_questions((await db.get_quiz_by_code("2000", db_path=db_file))["id"], db_path=db_file)
    for item in sample_qs[:8]:
        await db.create_question(
            int(quiz["id"]),
            item["question_text"],
            item["option_a"],
            item["option_b"],
            item["option_c"],
            item["option_d"],
            item["correct_option"],
            db_path=db_file,
        )

    info_resp = await engine.handle_text_message(555001, "Dilshod", "dilshod", "3001", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(info_resp.keyboard)
    assert "Falsafa Amaliy" in info_resp.text

    questions = await db.list_questions(int(quiz["id"]), db_path=db_file)
    start_resp = await engine.handle_callback(555001, "Dilshod", "dilshod", f"qz:s:{quiz['id']}:p", db_path=db_file)
    att_id = int(start_resp.keyboard[0][0]["callback_data"].split(":")[2])

    for idx, q in enumerate(questions):
        if idx > 0:
            await engine.handle_callback(555001, "Dilshod", "dilshod", f"qz:n:{att_id}:{idx}", db_path=db_file)
        pick = "A" if idx == 0 and q["correct_option"] != "A" else q["correct_option"]
        ans = await engine.handle_callback(555001, "Dilshod", "dilshod", f"qz:a:{att_id}:{q['id']}:{pick}", db_path=db_file)
        if idx == 0:
            assert "Noto'g'ri javob!" in ans.text
        else:
            assert "To'g'ri javob!" in ans.text

    res1 = await engine.handle_callback(555001, "Dilshod", "dilshod", f"qz:fc:{att_id}", db_path=db_file)
    assert "87.5%" in res1.text
    assert "+90 XP" in res1.text

    rev = await engine.handle_callback(555001, "Dilshod", "dilshod", f"qz:r:{att_id}:0:1", db_path=db_file)
    assert "Xatolar tahlili (1/1)" in rev.text


@pytest.mark.asyncio
async def test_exam_mode_navigation_and_timeout(tmp_path: Path) -> None:
    db_file = tmp_path / "test_exam.db"
    await db.init_db(db_file)

    quiz = await db.get_quiz_by_code("2000", db_path=db_file)
    assert quiz is not None
    questions = await db.list_questions(int(quiz["id"]), db_path=db_file)

    start_resp = await engine.handle_callback(555002, "Madina", "madina", f"qz:s:{quiz['id']}:e", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(start_resp.keyboard)
    att_id = int(start_resp.keyboard[0][0]["callback_data"].split(":")[2])

    # Answer question 1 -> advances to question 2
    after_q1 = await engine.handle_callback(
        555002, "Madina", "madina", f"qz:a:{att_id}:{questions[0]['id']}:{questions[0]['correct_option']}", db_path=db_file
    )
    assert f"Savol <b>2/{len(questions)}</b>" in after_q1.text

    # Open question map
    map_resp = await engine.handle_callback(555002, "Madina", "madina", f"qz:map:{att_id}", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(map_resp.keyboard)
    assert "Savollar xaritasi" in map_resp.text

    # Simulate exam timeout by shifting started_at back past time_limit_sec
    expired_iso = (datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat()
    async with db.get_db(db_file) as conn:
        await conn.execute("UPDATE attempts SET started_at = ? WHERE id = ?", (expired_iso, att_id))
        await conn.commit()

    timeout_resp = await engine.handle_callback(555002, "Madina", "madina", f"qz:n:{att_id}:2", db_path=db_file)
    assert "Ajratilgan vaqt tugadi" in timeout_resp.text


def test_fastapi_endpoints_and_simulator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_db = tmp_path / "web_test.db"
    temp_env = tmp_path / ".env"
    temp_env.write_text("", encoding="utf-8")

    monkeypatch.setattr(config, "ENV_PATH", temp_env)
    monkeypatch.setenv("DATABASE_PATH", str(test_db))
    monkeypatch.setenv("BOT_TOKEN", "")
    monkeypatch.setenv("ADMIN_IDS", "")
    monkeypatch.setenv("ADMIN_LOGIN", "muxandis")
    monkeypatch.setenv("ADMIN_PASSWORD", "muxandis2026")
    config.reload_settings()

    try:
        with TestClient(app) as client:
            home = client.get("/")
            assert home.status_code == 200
            assert "TestMaster Bot Studio" in home.text

            # Telegram Mini App (/webapp) is publicly accessible without studio admin login
            webapp_page = client.get("/webapp")
            assert webapp_page.status_code == 200
            assert "telegram-web-app.js" in webapp_page.text

            tma_init = client.post(
                "/api/webapp/init",
                json={"telegram_id": 777001, "full_name": "MiniApp User", "username": "tma_user"},
            )
            assert tma_init.status_code == 200
            assert len(tma_init.json()["quizzes"]) == 1
            falsafa_qid = tma_init.json()["quizzes"][0]["id"]

            tma_start = client.post(
                "/api/webapp/start",
                json={"quiz_id": falsafa_qid, "mode": "practice", "telegram_id": 777001, "full_name": "MiniApp User"},
            )
            assert tma_start.status_code == 200
            tma_att_id = tma_start.json()["attempt"]["id"]
            tma_first_q = tma_start.json()["questions"][0]

            tma_ans = client.post(
                "/api/webapp/answer",
                json={
                    "attempt_id": tma_att_id,
                    "question_id": tma_first_q["id"],
                    "selected_option": tma_first_q["correct_option"],
                },
            )
            assert tma_ans.status_code == 200
            assert tma_ans.json()["is_correct"] is True

            tma_fin = client.post(
                "/api/webapp/finish",
                json={"attempt_id": tma_att_id, "duration_sec": 12},
            )
            assert tma_fin.status_code == 200
            assert tma_fin.json()["attempt"]["percentage"] == 100.0

            # Protected endpoints must reject unauthenticated requests
            assert client.get("/api/stats").status_code == 401
            assert client.get("/api/users").status_code == 401
            me_before = client.get("/api/auth/me")
            assert me_before.status_code == 200
            assert me_before.json() == {"authenticated": False, "username": None}

            # Invalid login fails; valid login sets session cookie
            bad_login = client.post("/api/auth/login", json={"username": "muxandis", "password": "wrong"})
            assert bad_login.status_code == 401

            good_login = client.post("/api/auth/login", json={"username": "muxandis", "password": "muxandis2026"})
            assert good_login.status_code == 200
            assert good_login.json()["authenticated"] is True
            assert good_login.json()["username"] == "muxandis"

            me_after = client.get("/api/auth/me")
            assert me_after.status_code == 200
            assert me_after.json() == {"authenticated": True, "username": "muxandis"}

            stats = client.get("/api/stats").json()
            assert stats["categories_count"] == 1
            assert stats["quizzes_count"] == 1
            assert stats["questions_count"] == 175
            assert stats["bot_status"]["mode"] == "simulator"

            # Create category, quiz, and bulk questions
            cat_res = client.post("/api/categories", json={"name": "Mantiq Plus", "icon": "🧠", "description": "Qo'shimcha"})
            assert cat_res.status_code == 200
            cat_id = cat_res.json()["id"]

            qz_res = client.post(
                "/api/quizzes",
                json={
                    "category_id": cat_id,
                    "title": "Silogizm Testi",
                    "code": "7777",
                    "difficulty": "oson",
                    "time_limit_sec": 180,
                },
            )
            assert qz_res.status_code == 200
            quiz_id = qz_res.json()["id"]

            bulk_res = client.post(
                f"/api/quizzes/{quiz_id}/questions/bulk",
                json={"raw_text": "Silogizm nechta hukmdan iborat? | 2 ta | 3 ta | 4 ta | 5 ta | B | Ikki asos va bir xulosa."},
            )
            assert bulk_res.status_code == 200
            assert bulk_res.json()["created_count"] == 1

            # Edit category, quiz, and question via PUT endpoints
            cat_upd = client.put(
                f"/api/categories/{cat_id}",
                json={"name": "Mantiq Pro", "icon": "💡", "description": "Yangilandi", "is_active": True},
            )
            assert cat_upd.status_code == 200
            assert cat_upd.json()["name"] == "Mantiq Pro"

            qz_upd = client.put(
                f"/api/quizzes/{quiz_id}",
                json={
                    "category_id": cat_id,
                    "title": "Silogizm Testi Pro",
                    "code": "7777",
                    "description": "Tahrirlangan",
                    "difficulty": "orta",
                    "time_limit_sec": 240,
                    "is_active": True,
                },
            )
            assert qz_upd.status_code == 200
            assert qz_upd.json()["title"] == "Silogizm Testi Pro"

            qs = client.get(f"/api/quizzes/{quiz_id}/questions").json()["questions"]
            first_q_id = qs[0]["id"]
            q_upd = client.put(
                f"/api/questions/{first_q_id}",
                json={
                    "question_text": "Silogizm nechta hukmdan tuziladi?",
                    "option_a": "2 ta",
                    "option_b": "3 ta",
                    "option_c": "4 ta",
                    "option_d": "5 ta",
                    "correct_option": "B",
                    "explanation": "Qayta tekshirildi",
                    "points": 15,
                },
            )
            assert q_upd.status_code == 200
            assert q_upd.json()["points"] == 15

            # Test Simulator API: /start -> c:list shows test names
            sim_start = client.post("/api/simulator/action", json={"text": "/start"})
            assert sim_start.status_code == 200
            assert "Falsafa Test Botga xush kelibsiz" in sim_start.json()["text"]

            sim_list = client.post("/api/simulator/action", json={"callback_data": "c:list"})
            assert sim_list.status_code == 200
            assert any(
                b["text"] == "🦉 Falsafa (175 ta savol)"
                for row in sim_list.json()["keyboard"]
                for b in row
            )

            sim_code = client.post("/api/simulator/action", json={"text": "7777"})
            assert sim_code.status_code == 200
            assert "Silogizm Testi Pro" in sim_code.json()["text"]

            # Test Web Quiz Player API
            w_start = client.post("/api/web-quiz/start", json={"quiz_id": quiz_id, "mode": "practice"})
            assert w_start.status_code == 200
            w_data = w_start.json()
            att_id = w_data["attempt"]["id"]
            q_id = w_data["questions"][0]["id"]

            w_ans = client.post("/api/web-quiz/answer", json={"attempt_id": att_id, "question_id": q_id, "selected_option": "B"})
            assert w_ans.status_code == 200
            assert w_ans.json()["is_correct"] is True

            w_fin = client.post("/api/web-quiz/finish", json={"attempt_id": att_id, "duration_sec": 15})
            assert w_fin.status_code == 200
            assert w_fin.json()["attempt"]["percentage"] == 100.0

            # User CRUD & Admin role toggle
            u_create = client.post(
                "/api/users",
                json={"telegram_id": 555001, "full_name": "Test Admin", "username": "tadmin", "xp": 50, "is_admin": True},
            )
            assert u_create.status_code == 200
            created_uid = u_create.json()["id"]
            assert u_create.json()["is_admin"] is True

            users_list = client.get("/api/users").json()
            assert any(u["telegram_id"] == 555001 and u["is_admin"] is True for u in users_list)

            u_upd = client.put(
                f"/api/users/{created_uid}",
                json={
                    "telegram_id": 555001,
                    "full_name": "Updated User",
                    "username": "updated_u",
                    "xp": 120,
                    "tests_completed": 2,
                    "correct_answers": 8,
                    "total_questions": 10,
                    "is_admin": False,
                },
            )
            assert u_upd.status_code == 200
            assert u_upd.json()["full_name"] == "Updated User"
            assert u_upd.json()["xp"] == 120
            assert u_upd.json()["is_admin"] is False

            u_reset = client.post(f"/api/users/{created_uid}/reset")
            assert u_reset.status_code == 200
            assert u_reset.json()["xp"] == 0
            assert u_reset.json()["tests_completed"] == 0

            # User Chat History: simulate user actions, admin message, fetch & clear history
            client.post(
                "/api/simulator/action",
                json={"telegram_id": 555001, "full_name": "Updated User", "username": "updated_u", "text": "/start"},
            )
            client.post(
                "/api/bot/broadcast",
                json={"text": "Admin test xabari", "telegram_id": 555001},
            )
            chats_res = client.get(f"/api/users/{created_uid}/chats")
            assert chats_res.status_code == 200
            chats_data = chats_res.json()
            assert chats_data["user"]["id"] == created_uid
            senders = [m["sender"] for m in chats_data["messages"]]
            assert "user" in senders
            assert "bot" in senders
            assert "admin" in senders

            clear_chats_res = client.delete(f"/api/users/{created_uid}/chats")
            assert clear_chats_res.status_code == 200
            assert clear_chats_res.json()["deleted_count"] >= 3
            assert client.get(f"/api/users/{created_uid}/chats").json()["messages"] == []

            u_del = client.delete(f"/api/users/{created_uid}")
            assert u_del.status_code == 200
            assert u_del.json()["deleted"] is True

            # Attempt delete & clear
            att_del = client.delete(f"/api/attempts/{att_id}")
            assert att_del.status_code == 200
            assert att_del.json()["deleted"] is True

            att_clear = client.delete("/api/attempts")
            assert att_clear.status_code == 200
            assert "deleted_count" in att_clear.json()

            # Credentials update & re-login verification
            cred_res = client.post(
                "/api/auth/credentials",
                json={"current_password": "muxandis2026", "new_username": "superadmin", "new_password": "newpass2026"},
            )
            assert cred_res.status_code == 200
            assert cred_res.json()["username"] == "superadmin"

            client.post("/api/auth/logout")
            assert client.get("/api/stats").status_code == 401
            assert client.post("/api/auth/login", json={"username": "muxandis", "password": "muxandis2026"}).status_code == 401
            assert client.post("/api/auth/login", json={"username": "superadmin", "password": "newpass2026"}).status_code == 200
            assert client.get("/api/stats").status_code == 200
    finally:
        config.reload_settings()


@pytest.mark.asyncio
async def test_falsafa_quizzes_map_pagination_and_hash_plus_import(tmp_path: Path) -> None:
    db_file = tmp_path / "falsafa_test.db"
    await db.init_db(db_file)

    full_quiz = await db.get_quiz_by_code("2000", db_path=db_file)
    assert full_quiz is not None
    assert full_quiz["question_count"] == 175

    # Ensure 175-question exam map paginates cleanly (< 100 inline buttons)
    start_resp = await engine.handle_callback(888001, "FalsafaUser", "fuser", f"qz:s:{full_quiz['id']}:e", db_path=db_file)
    att_id = int(start_resp.keyboard[0][0]["callback_data"].split(":")[2])

    map_p0 = await engine.handle_callback(888001, "FalsafaUser", "fuser", f"qz:map:{att_id}:0", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(map_p0.keyboard)
    btn_count_p0 = sum(len(r) for r in map_p0.keyboard)
    assert btn_count_p0 <= 45

    map_p4 = await engine.handle_callback(888001, "FalsafaUser", "fuser", f"qz:map:{att_id}:4", db_path=db_file)
    _assert_all_callbacks_under_64_bytes(map_p4.keyboard)
    assert any(b["text"].startswith("175 ") for row in map_p4.keyboard for b in row)

    # Test '#' / '+' block bulk import format
    hash_raw = """
# Falsafa so'zi qanday ma'noni anglatadi?
A. Bilimdonlik
+ B. Donishmandlikni sevish
C. Tabiatshunoslik
- Mantiqiy fikrlash
"""
    created, errors = await db.bulk_create_questions(int(full_quiz["id"]), hash_raw, db_path=db_file)
    assert len(created) == 1
    assert not errors
    assert created[0]["correct_option"] == "B"
    assert created[0]["option_b"] == "Donishmandlikni sevish"
