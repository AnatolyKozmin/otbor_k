import json
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Review, SHEET_KEYS, User

# ---------- Redis (lazy + resilient) ------------------------------------------
# Клиент создаём один раз, но НЕ проверяем доступность на старте.
# Каждая операция возвращает реальный статус — если Redis упал в процессе
# или поднялся после старта, мы это сразу заметим.
try:
    import redis as _redis_lib
    _rc = _redis_lib.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=0,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
except Exception:
    _rc = None


def _rkey(sheet: str, row_number: int, user_id: int) -> str:
    return f"autosave:{sheet}:{row_number}:{user_id}"


def _redis_get(sheet: str, row_number: int, user_id: int) -> Optional[Dict]:
    if _rc is None:
        return None
    try:
        raw = _rc.get(_rkey(sheet, row_number, user_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _redis_set(sheet: str, row_number: int, user_id: int, scores: Dict) -> bool:
    """Возвращает True, если запись действительно ушла в Redis."""
    if _rc is None:
        return False
    try:
        _rc.setex(_rkey(sheet, row_number, user_id), 86400, json.dumps(scores))
        return True
    except Exception:
        return False


def _redis_del(sheet: str, row_number: int, user_id: int) -> None:
    if _rc is None:
        return
    try:
        _rc.delete(_rkey(sheet, row_number, user_id))
    except Exception:
        pass


def _redis_alive() -> bool:
    if _rc is None:
        return False
    try:
        return bool(_rc.ping())
    except Exception:
        return False


# ---------- Scoring criteria --------------------------------------------------
SCORE_CRITERIA = [
    {"key": "team_work",             "label": "Работа в команде",          "options": [0, 1, 2, 3]},
    {"key": "efcom",                 "label": "Эфком",                     "options": [0, 1, 2, 3]},
    {"key": "time_mgmt",             "label": "Тайм-менеджмент",           "options": [0, 1, 2, 3]},
    {"key": "project_understanding", "label": "Понимание проекта",          "options": [0, 1, 3]},
    {"key": "interest",              "label": "Заинтересованность",         "options": [0, 2, 3]},
    {"key": "awareness",             "label": "Осознанность",               "type": "text"},
    {"key": "experience",            "label": "Опыт в схожей деятельности", "type": "text"},
    {"key": "leadership",            "label": "Лидерство",                  "type": "text"},
    {"key": "gpt_usage",             "label": "Использование ГПТ",          "type": "text"},
    {"key": "questions",             "label": "Вопросы по анкете",           "type": "text"},
    {"key": "comments",              "label": "Комментарии по анкете",        "type": "text"},
]

# ---------- Router -----------------------------------------------------------
router = APIRouter(prefix="/reviews", tags=["reviews"])


class ScoresPayload(BaseModel):
    scores: Dict[str, Any]


@router.get("/{sheet}/status")
def get_review_status(
    sheet: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Возвращает список row_number-ов, которые текущий пользователь уже проверил."""
    if sheet not in SHEET_KEYS:
        raise HTTPException(status_code=404, detail="Лист не найден")
    rows = (
        db.query(Review.row_number)
        .filter(Review.sheet == sheet, Review.reviewer_id == user.id)
        .all()
    )
    return {"reviewed": [r.row_number for r in rows]}


@router.get("/criteria")
def get_criteria():
    # Проверяем Redis здесь и сейчас, а не значение времени старта.
    return {"criteria": SCORE_CRITERIA, "redis_available": _redis_alive()}


@router.get("/{sheet}/{row_number}")
def get_review(
    sheet: str,
    row_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if sheet not in SHEET_KEYS:
        raise HTTPException(status_code=404, detail="Лист не найден")

    saved = (
        db.query(Review)
        .filter(
            Review.sheet == sheet,
            Review.row_number == row_number,
            Review.reviewer_id == user.id,
        )
        .first()
    )

    saved_scores: Dict = saved.scores if saved else {}
    autosave_scores = _redis_get(sheet, row_number, user.id)

    # Use autosave if it differs from what's already committed
    has_autosave = autosave_scores is not None and autosave_scores != saved_scores
    active_scores = autosave_scores if has_autosave else saved_scores

    return {
        "scores": active_scores,
        "has_autosave": has_autosave,
        "is_saved": saved is not None,
    }


@router.post("/{sheet}/{row_number}/autosave")
def autosave_review(
    sheet: str,
    row_number: int,
    payload: ScoresPayload,
    user: User = Depends(get_current_user),
):
    if sheet not in SHEET_KEYS:
        raise HTTPException(status_code=404, detail="Лист не найден")
    # Возвращаем РЕАЛЬНЫЙ статус — клиент должен знать, попало ли в Redis,
    # чтобы решить, доверять ли только локальному бэкапу.
    redis_ok = _redis_set(sheet, row_number, user.id, payload.scores)
    return {"ok": redis_ok, "redis": redis_ok}


@router.post("/{sheet}/{row_number}")
def save_review(
    sheet: str,
    row_number: int,
    payload: ScoresPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if sheet not in SHEET_KEYS:
        raise HTTPException(status_code=404, detail="Лист не найден")

    review = (
        db.query(Review)
        .filter(
            Review.sheet == sheet,
            Review.row_number == row_number,
            Review.reviewer_id == user.id,
        )
        .first()
    )

    now = datetime.utcnow()
    if review:
        review.scores = payload.scores
        review.synced_to_sheets = False
        review.saved_at = now  # явно — onupdate отсутствует, чтобы не ломать sync
    else:
        review = Review(
            sheet=sheet,
            row_number=row_number,
            reviewer_id=user.id,
            scores=payload.scores,
            synced_to_sheets=False,
            saved_at=now,
        )
        db.add(review)

    db.commit()
    _redis_del(sheet, row_number, user.id)
    return {"ok": True}
