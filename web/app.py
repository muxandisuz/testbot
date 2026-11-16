"""FastAPI backend powering the Telegram Bot Simulator, Web Quiz Player, and Admin Panel."""

from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
import hmac
from pathlib import Path
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import database as db
from bot import engine
from bot.manager import bot_manager
from config import get_settings, update_env_settings

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

SESSION_COOKIE_NAME = "tm_session"
SESSION_TTL_SEC = 86400 * 7


def _session_secret(login: str, password: str) -> bytes:
    return hashlib.sha256(f"testmaster-studio:{login}:{password}".encode("utf-8")).digest()


def _make_session_token(login: str, password: str) -> str:
    exp = int(time.time()) + SESSION_TTL_SEC
    payload = f"{login}:{exp}"
    sig = hmac.new(_session_secret(login, password), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_session_token(token: str | None, login: str, password: str) -> bool:
    if not token:
        return False
    parts = token.split(":")
    if len(parts) < 3:
        return False
    sig = parts[-1]
    exp_str = parts[-2]
    token_login = ":".join(parts[:-2])
    if token_login != login or not exp_str.isdigit():
        return False
    if int(exp_str) < int(time.time()):
        return False
    expected_payload = f"{token_login}:{exp_str}"
    expected_sig = hmac.new(
        _session_secret(login, password),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def _extract_request_token(request: Request) -> str | None:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.cookies.get(SESSION_COOKIE_NAME)


async def _is_request_authenticated(request: Request) -> tuple[bool, str]:
    login, password = await db.get_admin_credentials()
    token = _extract_request_token(request)
    return _verify_session_token(token, login, password), login


async def require_studio_auth(request: Request) -> str:
    """FastAPI dependency protecting all Studio/Admin API endpoints."""
    ok, login = await _is_request_authenticated(request)
    if not ok:
        raise HTTPException(status_code=401, detail="Tizimga kirish talab qilinadi")
    return login


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SEC,
        path="/",
    )


def _set_user_admin_flag(telegram_id: int, make_admin: bool) -> str:
    id_set = set(get_settings().admin_id_list)
    if make_admin:
        id_set.add(int(telegram_id))
    else:
        id_set.discard(int(telegram_id))
    new_ids = ",".join(str(x) for x in sorted(id_set))
    update_env_settings(admin_ids=new_ids)
    return new_ids


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init_db()
    await bot_manager.start_or_restart()
    try:
        yield
    finally:
        await bot_manager.stop_bot()


app = FastAPI(title="TestMaster Bot Studio", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class CredentialsUpdate(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_username: str = Field(..., min_length=2, max_length=64)
    new_password: str = Field(..., min_length=4, max_length=128)


class UserCreateModel(BaseModel):
    telegram_id: int
    full_name: str = Field(..., min_length=1, max_length=120)
    username: str = Field(default="", max_length=80)
    xp: int = Field(default=0, ge=0)
    is_admin: bool = False


class UserUpdateModel(BaseModel):
    telegram_id: int
    full_name: str = Field(..., min_length=1, max_length=120)
    username: str = Field(default="", max_length=80)
    xp: int = Field(default=0, ge=0)
    tests_completed: int = Field(default=0, ge=0)
    correct_answers: int = Field(default=0, ge=0)
    total_questions: int = Field(default=0, ge=0)
    is_admin: bool | None = None


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    icon: str = Field(default="📚", max_length=16)
    description: str = Field(default="", max_length=300)


class CategoryUpdate(CategoryCreate):
    is_active: bool = True


class QuizCreate(BaseModel):
    category_id: int
    title: str = Field(..., min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=16)
    description: str = Field(default="", max_length=400)
    difficulty: str = Field(default="orta")
    time_limit_sec: int = Field(default=300, ge=30, le=7200)


class QuizUpdate(BaseModel):
    category_id: int
    title: str = Field(..., min_length=2, max_length=120)
    code: str = Field(..., min_length=1, max_length=16)
    description: str = Field(default="", max_length=400)
    difficulty: str = Field(default="orta")
    time_limit_sec: int = Field(default=300, ge=30, le=7200)
    is_active: bool = True


class QuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=2)
    option_a: str = Field(..., min_length=1)
    option_b: str = Field(..., min_length=1)
    option_c: str = Field(..., min_length=1)
    option_d: str = Field(..., min_length=1)
    correct_option: str = Field(..., pattern="^[A-Da-d]$")
    explanation: str = Field(default="")
    points: int = Field(default=10, ge=1, le=100)


class QuestionUpdate(QuestionCreate):
    pass


class BulkQuestionsCreate(BaseModel):
    raw_text: str = Field(..., min_length=5)


class SimulatorAction(BaseModel):
    telegram_id: int = 999000111
    full_name: str = "Mehmon Foydalanuvchi"
    username: str = "demo_user"
    is_admin: bool = True
    callback_data: str | None = None
    text: str | None = None


class WebQuizStart(BaseModel):
    quiz_id: int
    mode: str = "practice"
    telegram_id: int = 999000111
    full_name: str = "Web Foydalanuvchi"


class WebQuizAnswer(BaseModel):
    attempt_id: int
    question_id: int
    selected_option: str = Field(..., pattern="^[A-Da-d]$")


class WebQuizFinish(BaseModel):
    attempt_id: int
    duration_sec: int | None = None


class BotTokenUpdate(BaseModel):
    bot_token: str = ""
    admin_ids: str | None = None


class BroadcastRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    telegram_id: int | None = None


class WebAppInitRequest(BaseModel):
    telegram_id: int = 999000111
    full_name: str = "Telegram Foydalanuvchi"
    username: str = ""


class WebAppQuizStart(BaseModel):
    quiz_id: int
    mode: str = "practice"
    telegram_id: int = 999000111
    full_name: str = "Telegram Foydalanuvchi"
    username: str = ""


# ---------------------------------------------------------------------------
# Pages & Authentication
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "index.html")


@app.get("/webapp", response_class=HTMLResponse)
@app.get("/miniapp", response_class=HTMLResponse)
async def webapp_page(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "webapp.html")


@app.post("/api/auth/login")
async def api_auth_login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    login, password = await db.get_admin_credentials()
    user_ok = hmac.compare_digest(payload.username.strip(), login)
    pass_ok = hmac.compare_digest(payload.password, password)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Login yoki parol noto'g'ri")
    token = _make_session_token(login, password)
    _set_session_cookie(response, token)
    return {"authenticated": True, "username": login, "token": token}


@app.post("/api/auth/logout")
async def api_auth_logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"authenticated": False}


@app.get("/api/auth/me")
async def api_auth_me(request: Request) -> dict[str, Any]:
    ok, login = await _is_request_authenticated(request)
    return {"authenticated": ok, "username": login if ok else None}


@app.post("/api/auth/credentials")
async def api_auth_update_credentials(
    payload: CredentialsUpdate,
    response: Response,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    active_login, active_password = await db.get_admin_credentials()
    if not hmac.compare_digest(payload.current_password, active_password):
        raise HTTPException(status_code=400, detail="Joriy parol noto'g'ri")
    new_login = payload.new_username.strip()
    try:
        await db.set_admin_credentials(new_login, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    update_env_settings(admin_login=new_login, admin_password=payload.new_password)
    token = _make_session_token(new_login, payload.new_password)
    _set_session_cookie(response, token)
    return {"updated": True, "username": new_login, "token": token}


@app.get("/api/stats")
async def api_stats(_: str = Depends(require_studio_auth)) -> dict[str, Any]:
    stats = await db.get_dashboard_stats()
    stats["bot_status"] = bot_manager.get_status()
    stats["admin_ids"] = get_settings().admin_ids
    return stats


# ---------------------------------------------------------------------------
# User Management CRUD
# ---------------------------------------------------------------------------

def _attach_admin_flag(user: dict[str, Any]) -> dict[str, Any]:
    item = dict(user)
    item["is_admin"] = int(item["telegram_id"]) in get_settings().admin_id_list
    return item


@app.get("/api/users")
async def api_list_users(_: str = Depends(require_studio_auth)) -> list[dict[str, Any]]:
    users = await db.list_users()
    return [_attach_admin_flag(u) for u in users]


@app.post("/api/users")
async def api_create_user(
    payload: UserCreateModel,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    try:
        user = await db.create_user(
            telegram_id=payload.telegram_id,
            full_name=payload.full_name,
            username=payload.username,
            xp=payload.xp,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.is_admin:
        _set_user_admin_flag(int(user["telegram_id"]), True)
    return _attach_admin_flag(user)


@app.put("/api/users/{user_id}")
async def api_update_user(
    user_id: int,
    payload: UserUpdateModel,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    old_user = await db.get_user_by_id(user_id)
    if not old_user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    try:
        updated = await db.update_user(
            user_id=user_id,
            full_name=payload.full_name,
            username=payload.username,
            telegram_id=payload.telegram_id,
            xp=payload.xp,
            tests_completed=payload.tests_completed,
            correct_answers=payload.correct_answers,
            total_questions=payload.total_questions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    if payload.is_admin is not None:
        if int(old_user["telegram_id"]) != int(updated["telegram_id"]):
            _set_user_admin_flag(int(old_user["telegram_id"]), False)
        _set_user_admin_flag(int(updated["telegram_id"]), payload.is_admin)
    return _attach_admin_flag(updated)


@app.post("/api/users/{user_id}/reset")
async def api_reset_user_stats(
    user_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    updated = await db.reset_user_stats(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return _attach_admin_flag(updated)


@app.delete("/api/users/{user_id}")
async def api_delete_user(
    user_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, bool]:
    existing = await db.get_user_by_id(user_id)
    deleted = await db.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    if existing:
        _set_user_admin_flag(int(existing["telegram_id"]), False)
    return {"deleted": True}


@app.get("/api/users/{user_id}/chats")
async def api_get_user_chats(
    user_id: int,
    limit: int = 200,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    messages = await db.list_user_chat_history(user_id=user_id, limit=limit)
    attempts = await db.list_user_attempts(user_id=user_id, limit=30)
    return {
        "user": _attach_admin_flag(user),
        "messages": messages,
        "attempts": attempts,
    }


@app.delete("/api/users/{user_id}/chats")
async def api_clear_user_chats(
    user_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, int]:
    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    deleted_count = await db.clear_user_chat_history(user_id=user_id)
    return {"deleted_count": deleted_count}


# ---------------------------------------------------------------------------
# Categories & Quizzes & Questions CRUD
# ---------------------------------------------------------------------------

@app.get("/api/categories")
async def api_list_categories(_: str = Depends(require_studio_auth)) -> list[dict[str, Any]]:
    return await db.list_categories(active_only=False)


@app.post("/api/categories")
async def api_create_category(
    payload: CategoryCreate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    return await db.create_category(
        name=payload.name,
        icon=payload.icon,
        description=payload.description,
    )


@app.put("/api/categories/{cat_id}")
async def api_update_category(
    cat_id: int,
    payload: CategoryUpdate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    updated = await db.update_category(
        category_id=cat_id,
        name=payload.name,
        icon=payload.icon,
        description=payload.description,
        is_active=payload.is_active,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Fan topilmadi")
    return updated


@app.delete("/api/categories/{cat_id}")
async def api_delete_category(
    cat_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, bool]:
    deleted = await db.delete_category(cat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fan topilmadi")
    return {"deleted": True}


@app.get("/api/quizzes")
async def api_list_quizzes(
    category_id: int | None = Query(default=None),
    _: str = Depends(require_studio_auth),
) -> list[dict[str, Any]]:
    return await db.list_quizzes(category_id=category_id, active_only=False)


@app.post("/api/quizzes")
async def api_create_quiz(
    payload: QuizCreate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    try:
        return await db.create_quiz(
            category_id=payload.category_id,
            title=payload.title,
            code=payload.code,
            description=payload.description,
            difficulty=payload.difficulty,
            time_limit_sec=payload.time_limit_sec,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/quizzes/{quiz_id}")
async def api_update_quiz(
    quiz_id: int,
    payload: QuizUpdate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    try:
        updated = await db.update_quiz(
            quiz_id=quiz_id,
            category_id=payload.category_id,
            title=payload.title,
            code=payload.code,
            description=payload.description,
            difficulty=payload.difficulty,
            time_limit_sec=payload.time_limit_sec,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    return updated


@app.delete("/api/quizzes/{quiz_id}")
async def api_delete_quiz(
    quiz_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, bool]:
    deleted = await db.delete_quiz(quiz_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    return {"deleted": True}


@app.get("/api/quizzes/{quiz_id}/questions")
async def api_list_questions(
    quiz_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    quiz = await db.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    questions = await db.list_questions(quiz_id)
    return {"quiz": quiz, "questions": questions}


@app.post("/api/quizzes/{quiz_id}/questions")
async def api_create_question(
    quiz_id: int,
    payload: QuestionCreate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    quiz = await db.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    try:
        return await db.create_question(
            quiz_id=quiz_id,
            question_text=payload.question_text,
            option_a=payload.option_a,
            option_b=payload.option_b,
            option_c=payload.option_c,
            option_d=payload.option_d,
            correct_option=payload.correct_option,
            explanation=payload.explanation,
            points=payload.points,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/quizzes/{quiz_id}/questions/bulk")
async def api_bulk_questions(
    quiz_id: int,
    payload: BulkQuestionsCreate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    quiz = await db.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    created, errors = await db.bulk_create_questions(quiz_id, payload.raw_text)
    return {"created_count": len(created), "created": created, "errors": errors}


@app.put("/api/questions/{question_id}")
async def api_update_question(
    question_id: int,
    payload: QuestionUpdate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    try:
        updated = await db.update_question(
            question_id=question_id,
            question_text=payload.question_text,
            option_a=payload.option_a,
            option_b=payload.option_b,
            option_c=payload.option_c,
            option_d=payload.option_d,
            correct_option=payload.correct_option,
            explanation=payload.explanation,
            points=payload.points,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Savol topilmadi")
    return updated


@app.delete("/api/questions/{question_id}")
async def api_delete_question(
    question_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, bool]:
    deleted = await db.delete_question(question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Savol topilmadi")
    return {"deleted": True}


@app.get("/api/leaderboard")
async def api_leaderboard(
    category_id: int | None = Query(default=None),
    _: str = Depends(require_studio_auth),
) -> list[dict[str, Any]]:
    return await db.get_leaderboard(limit=20, category_id=category_id)


@app.delete("/api/attempts/{attempt_id}")
async def api_delete_attempt(
    attempt_id: int,
    _: str = Depends(require_studio_auth),
) -> dict[str, bool]:
    deleted = await db.delete_attempt(attempt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Natija topilmadi")
    return {"deleted": True}


@app.delete("/api/attempts")
async def api_clear_attempts(_: str = Depends(require_studio_auth)) -> dict[str, int]:
    deleted_count = await db.clear_all_attempts()
    return {"deleted_count": deleted_count}


# ---------------------------------------------------------------------------
# Telegram Simulator & Web Quiz Player
# ---------------------------------------------------------------------------

@app.post("/api/simulator/action")
async def api_simulator_action(
    payload: SimulatorAction,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    if payload.callback_data:
        resp = await engine.handle_callback(
            telegram_id=payload.telegram_id,
            full_name=payload.full_name,
            username=payload.username,
            data=payload.callback_data,
            is_admin=payload.is_admin,
        )
    else:
        resp = await engine.handle_text_message(
            telegram_id=payload.telegram_id,
            full_name=payload.full_name,
            username=payload.username,
            text=payload.text or "/start",
            is_admin=payload.is_admin,
        )
    return {
        "text": resp.text,
        "keyboard": resp.keyboard,
        "toast": resp.toast,
        "awaiting_input": resp.awaiting_input,
    }


@app.post("/api/web-quiz/start")
async def api_web_quiz_start(
    payload: WebQuizStart,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    quiz = await db.get_quiz(payload.quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    questions = await db.list_questions(payload.quiz_id)
    if not questions:
        raise HTTPException(status_code=400, detail="Ushbu testda savollar mavjud emas")

    user = await db.get_or_create_user(payload.telegram_id, payload.full_name, "web_user")
    attempt = await db.create_attempt(int(user["id"]), payload.quiz_id, mode=payload.mode)
    safe_questions = []
    for q in questions:
        safe_questions.append({
            "id": q["id"],
            "question_text": q["question_text"],
            "option_a": q["option_a"],
            "option_b": q["option_b"],
            "option_c": q["option_c"],
            "option_d": q["option_d"],
            "correct_option": q["correct_option"],
            "points": q["points"],
            "order_num": q["order_num"],
        })
    return {"attempt": attempt, "quiz": quiz, "questions": safe_questions}


@app.post("/api/web-quiz/answer")
async def api_web_quiz_answer(
    payload: WebQuizAnswer,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    attempt = await db.get_attempt(payload.attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Urinish topilmadi")
    if attempt["is_completed"]:
        raise HTTPException(status_code=400, detail="Test allaqachon yakunlangan")
    result = await db.save_attempt_answer(payload.attempt_id, payload.question_id, payload.selected_option)
    if attempt["mode"] == "exam":
        return {"saved": True, "selected_option": result["selected_option"]}
    return result


@app.post("/api/web-quiz/finish")
async def api_web_quiz_finish(
    payload: WebQuizFinish,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    try:
        attempt = await db.finalize_attempt(payload.attempt_id, duration_sec=payload.duration_sec)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    quiz = await db.get_quiz(int(attempt["quiz_id"]))
    review_items = await db.get_attempt_review_items(payload.attempt_id, wrong_only=False)
    return {"attempt": attempt, "quiz": quiz, "review_items": review_items}


# ---------------------------------------------------------------------------
# Telegram Mini App (WebApp) Public Player Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/webapp/init")
async def api_webapp_init(payload: WebAppInitRequest) -> dict[str, Any]:
    user = await db.get_or_create_user(
        telegram_id=payload.telegram_id,
        full_name=payload.full_name or "Telegram Foydalanuvchi",
        username=payload.username or "",
    )
    stats = await db.get_user_stats(payload.telegram_id)
    attempts = await db.list_user_attempts(int(user["id"]), limit=20)
    categories = await db.list_categories(active_only=True)
    quizzes = await db.list_quizzes(active_only=True)
    leaderboard = await db.get_leaderboard(limit=20)
    return {
        "user": stats or user,
        "attempts": attempts,
        "categories": categories,
        "quizzes": quizzes,
        "leaderboard": leaderboard,
    }


@app.post("/api/webapp/start")
async def api_webapp_start(payload: WebAppQuizStart) -> dict[str, Any]:
    quiz = await db.get_quiz(payload.quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    questions = await db.list_questions(payload.quiz_id)
    if not questions:
        raise HTTPException(status_code=400, detail="Ushbu testda savollar mavjud emas")

    user = await db.get_or_create_user(
        telegram_id=payload.telegram_id,
        full_name=payload.full_name or "Telegram Foydalanuvchi",
        username=payload.username or "",
    )
    attempt = await db.create_attempt(int(user["id"]), payload.quiz_id, mode=payload.mode)
    mode_lbl = "Imtihon rejimi" if payload.mode == "exam" else "Mashq rejimi"
    await db.log_chat_message(
        telegram_id=payload.telegram_id,
        sender="user",
        content=f"📱 Mini App: {quiz['title']} (#{quiz['code']} · {mode_lbl}) boshlandi",
        action_type="callback",
    )
    safe_questions = [
        {
            "id": q["id"],
            "question_text": q["question_text"],
            "option_a": q["option_a"],
            "option_b": q["option_b"],
            "option_c": q["option_c"],
            "option_d": q["option_d"],
            "correct_option": q["correct_option"],
            "points": q["points"],
            "order_num": q["order_num"],
        }
        for q in questions
    ]
    return {"attempt": attempt, "quiz": quiz, "questions": safe_questions}


@app.post("/api/webapp/answer")
async def api_webapp_answer(payload: WebQuizAnswer) -> dict[str, Any]:
    attempt = await db.get_attempt(payload.attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Urinish topilmadi")
    if attempt["is_completed"]:
        raise HTTPException(status_code=400, detail="Test allaqachon yakunlangan")
    result = await db.save_attempt_answer(
        payload.attempt_id, payload.question_id, payload.selected_option
    )
    user = await db.get_user_by_id(int(attempt["user_id"]))
    if user:
        await db.log_chat_message(
            telegram_id=int(user["telegram_id"]),
            sender="user",
            content=f"📱 Mini App javob: {result['selected_option']} ({'✅ To`g`ri' if result['is_correct'] else '❌ Xato'})",
            action_type="callback",
        )
    if attempt["mode"] == "exam":
        return {"saved": True, "selected_option": result["selected_option"]}
    return result


@app.post("/api/webapp/finish")
async def api_webapp_finish(payload: WebQuizFinish) -> dict[str, Any]:
    try:
        attempt = await db.finalize_attempt(payload.attempt_id, duration_sec=payload.duration_sec)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    quiz = await db.get_quiz(int(attempt["quiz_id"]))
    review_items = await db.get_attempt_review_items(payload.attempt_id, wrong_only=False)
    user = await db.get_user_by_id(int(attempt["user_id"]))
    if user and quiz:
        await db.log_chat_message(
            telegram_id=int(user["telegram_id"]),
            sender="bot",
            content=(
                f"📱 <b>Mini App natijasi — {quiz['title']}</b>\n"
                f"📊 Natija: <b>{attempt['percentage']}%</b> "
                f"(✅ To'g'ri: {attempt['correct_count']} · ❌ Xato: {attempt['wrong_count']})"
            ),
            action_type="reply",
        )
    return {"attempt": attempt, "quiz": quiz, "review_items": review_items}


# ---------------------------------------------------------------------------
# Bot Token, Broadcast & Status Management
# ---------------------------------------------------------------------------

@app.get("/api/bot/status")
async def api_bot_status(_: str = Depends(require_studio_auth)) -> dict[str, Any]:
    status = bot_manager.get_status()
    status["admin_ids"] = get_settings().admin_ids
    return status


@app.post("/api/bot/token")
async def api_update_bot_token(
    payload: BotTokenUpdate,
    _: str = Depends(require_studio_auth),
) -> dict[str, Any]:
    settings = update_env_settings(bot_token=payload.bot_token, admin_ids=payload.admin_ids)
    status = await bot_manager.start_or_restart(settings.bot_token)
    status["admin_ids"] = settings.admin_ids
    return status


@app.post("/api/bot/broadcast")
async def api_bot_broadcast(
    payload: BroadcastRequest,
    _: str = Depends(require_studio_auth),
) -> dict[str, int]:
    if payload.telegram_id is not None:
        target_ids = [int(payload.telegram_id)]
    else:
        users = await db.list_users()
        target_ids = [int(u["telegram_id"]) for u in users if int(u["telegram_id"]) != 999000111]
    if not target_ids:
        return {"sent": 0, "failed": 0, "total": 0}

    for tid in target_ids:
        await db.log_chat_message(
            telegram_id=tid,
            sender="admin",
            content=payload.text,
            action_type="admin_message",
        )

    if not get_settings().bot_token.strip():
        return {"sent": len(target_ids), "failed": 0, "total": len(target_ids)}

    try:
        res = await bot_manager.send_message_to_users(target_ids, payload.text)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"sent": res["sent"], "failed": res["failed"], "total": len(target_ids)}
