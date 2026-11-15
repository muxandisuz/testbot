"""FastAPI backend powering the Telegram Bot Simulator, Web Quiz Player, and Admin Panel."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
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

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    icon: str = Field(default="📚", max_length=16)
    description: str = Field(default="", max_length=300)


class QuizCreate(BaseModel):
    category_id: int
    title: str = Field(..., min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=16)
    description: str = Field(default="", max_length=400)
    difficulty: str = Field(default="orta")
    time_limit_sec: int = Field(default=300, ge=30, le=7200)


class QuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=2)
    option_a: str = Field(..., min_length=1)
    option_b: str = Field(..., min_length=1)
    option_c: str = Field(..., min_length=1)
    option_d: str = Field(..., min_length=1)
    correct_option: str = Field(..., pattern="^[A-Da-d]$")
    explanation: str = Field(default="")
    points: int = Field(default=10, ge=1, le=100)


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


# ---------------------------------------------------------------------------
# Pages & Stats
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, "index.html")


@app.get("/api/stats")
async def api_stats() -> dict[str, Any]:
    stats = await db.get_dashboard_stats()
    stats["bot_status"] = bot_manager.get_status()
    stats["admin_ids"] = get_settings().admin_ids
    return stats


# ---------------------------------------------------------------------------
# Categories & Quizzes & Questions CRUD
# ---------------------------------------------------------------------------

@app.get("/api/categories")
async def api_list_categories() -> list[dict[str, Any]]:
    return await db.list_categories(active_only=False)


@app.post("/api/categories")
async def api_create_category(payload: CategoryCreate) -> dict[str, Any]:
    return await db.create_category(
        name=payload.name,
        icon=payload.icon,
        description=payload.description,
    )


@app.delete("/api/categories/{cat_id}")
async def api_delete_category(cat_id: int) -> dict[str, bool]:
    deleted = await db.delete_category(cat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fan topilmadi")
    return {"deleted": True}


@app.get("/api/quizzes")
async def api_list_quizzes(category_id: int | None = Query(default=None)) -> list[dict[str, Any]]:
    return await db.list_quizzes(category_id=category_id, active_only=False)


@app.post("/api/quizzes")
async def api_create_quiz(payload: QuizCreate) -> dict[str, Any]:
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


@app.delete("/api/quizzes/{quiz_id}")
async def api_delete_quiz(quiz_id: int) -> dict[str, bool]:
    deleted = await db.delete_quiz(quiz_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    return {"deleted": True}


@app.get("/api/quizzes/{quiz_id}/questions")
async def api_list_questions(quiz_id: int) -> dict[str, Any]:
    quiz = await db.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    questions = await db.list_questions(quiz_id)
    return {"quiz": quiz, "questions": questions}


@app.post("/api/quizzes/{quiz_id}/questions")
async def api_create_question(quiz_id: int, payload: QuestionCreate) -> dict[str, Any]:
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
async def api_bulk_questions(quiz_id: int, payload: BulkQuestionsCreate) -> dict[str, Any]:
    quiz = await db.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    created, errors = await db.bulk_create_questions(quiz_id, payload.raw_text)
    return {"created_count": len(created), "created": created, "errors": errors}


@app.delete("/api/questions/{question_id}")
async def api_delete_question(question_id: int) -> dict[str, bool]:
    deleted = await db.delete_question(question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Savol topilmadi")
    return {"deleted": True}


@app.get("/api/leaderboard")
async def api_leaderboard(category_id: int | None = Query(default=None)) -> list[dict[str, Any]]:
    return await db.get_leaderboard(limit=20, category_id=category_id)


# ---------------------------------------------------------------------------
# Telegram Simulator & Web Quiz Player
# ---------------------------------------------------------------------------

@app.post("/api/simulator/action")
async def api_simulator_action(payload: SimulatorAction) -> dict[str, Any]:
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
async def api_web_quiz_start(payload: WebQuizStart) -> dict[str, Any]:
    quiz = await db.get_quiz(payload.quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Test topilmadi")
    questions = await db.list_questions(payload.quiz_id)
    if not questions:
        raise HTTPException(status_code=400, detail="Ushbu testda savollar mavjud emas")

    user = await db.get_or_create_user(payload.telegram_id, payload.full_name, "web_user")
    attempt = await db.create_attempt(int(user["id"]), payload.quiz_id, mode=payload.mode)
    # Strip correct_option & explanation in exam mode until finish
    safe_questions = []
    for q in questions:
        safe_questions.append({
            "id": q["id"],
            "question_text": q["question_text"],
            "option_a": q["option_a"],
            "option_b": q["option_b"],
            "option_c": q["option_c"],
            "option_d": q["option_d"],
            "points": q["points"],
            "order_num": q["order_num"],
        })
    return {"attempt": attempt, "quiz": quiz, "questions": safe_questions}


@app.post("/api/web-quiz/answer")
async def api_web_quiz_answer(payload: WebQuizAnswer) -> dict[str, Any]:
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
async def api_web_quiz_finish(payload: WebQuizFinish) -> dict[str, Any]:
    try:
        attempt = await db.finalize_attempt(payload.attempt_id, duration_sec=payload.duration_sec)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    quiz = await db.get_quiz(int(attempt["quiz_id"]))
    review_items = await db.get_attempt_review_items(payload.attempt_id, wrong_only=False)
    return {"attempt": attempt, "quiz": quiz, "review_items": review_items}


# ---------------------------------------------------------------------------
# Bot Token & Status Management
# ---------------------------------------------------------------------------

@app.get("/api/bot/status")
async def api_bot_status() -> dict[str, Any]:
    status = bot_manager.get_status()
    status["admin_ids"] = get_settings().admin_ids
    return status


@app.post("/api/bot/token")
async def api_update_bot_token(payload: BotTokenUpdate) -> dict[str, Any]:
    settings = update_env_settings(bot_token=payload.bot_token, admin_ids=payload.admin_ids)
    status = await bot_manager.start_or_restart(settings.bot_token)
    status["admin_ids"] = settings.admin_ids
    return status
