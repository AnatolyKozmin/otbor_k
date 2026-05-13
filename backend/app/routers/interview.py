"""
Собеседования: назначение двух проверяющих + live-заметки + итоговое сохранение.
"""
import json
import math
import random
import time
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.interview_form import INTERVIEW_FORM
from app.models import InterviewAssignment, Review, SheetRow, User, Role

router = APIRouter(prefix="/interview", tags=["interview"])

# ---------- Redis (same lazy pattern as reviews.py) ---------------------------
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


def _note_key(row_number: int, reviewer_id: int, field_key: str) -> str:
    return f"interview_note:{row_number}:{reviewer_id}:{field_key}"


def _get_live_notes(row_number: int, reviewer_id: int) -> Dict[str, str]:
    if _rc is None:
        return {}
    try:
        pattern = f"interview_note:{row_number}:{reviewer_id}:*"
        keys = _rc.keys(pattern)
        notes: Dict[str, str] = {}
        for key in keys:
            field_key = (key.decode() if isinstance(key, bytes) else key).rsplit(":", 1)[-1]
            raw = _rc.get(key)
            if raw is not None:
                notes[field_key] = raw.decode() if isinstance(raw, bytes) else raw
        return notes
    except Exception:
        return {}


def _get_db_notes(row_number: int, reviewer_id: int, db: Session) -> Dict[str, str]:
    review = (
        db.query(Review)
        .filter(
            Review.sheet == "interview",
            Review.row_number == row_number,
            Review.reviewer_id == reviewer_id,
        )
        .first()
    )
    return dict(review.scores) if review else {}


def _resolve_notes(row_number: int, reviewer_id: int, db: Session) -> Dict[str, str]:
    live = _get_live_notes(row_number, reviewer_id)
    return live if live else _get_db_notes(row_number, reviewer_id, db)


# ---------- Column detection helpers (mirrors admin_ops.py) -------------------
FIO_KEYWORDS = ["фио", "имя", "фамилия", "ф.и.о"]
STUDENT_ID_KEYWORDS = ["студ", "билет"]


def _detect_col(rows: List, keywords: List[str]) -> Optional[str]:
    if not rows:
        return None
    for col in rows[0].data.keys():
        if col.startswith("_"):
            continue
        col_lower = col.lower()
        if all(kw in col_lower for kw in keywords):
            return col
    for col in rows[0].data.keys():
        if col.startswith("_"):
            continue
        if any(kw in col.lower() for kw in keywords):
            return col
    return None


# ---------- Endpoints ---------------------------------------------------------

@router.get("/form")
def get_form():
    return {"sections": INTERVIEW_FORM}


@router.get("/my")
def get_my_interviews(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список собеседований, назначенных текущему пользователю."""
    assignments = (
        db.query(InterviewAssignment)
        .filter(
            (InterviewAssignment.reviewer1_id == user.id)
            | (InterviewAssignment.reviewer2_id == user.id)
        )
        .all()
    )
    if not assignments:
        return {"interviews": []}

    row_numbers = [a.row_number for a in assignments]
    rows = {
        r.row_number: r
        for r in db.query(SheetRow)
        .filter(SheetRow.sheet == "interview", SheetRow.row_number.in_(row_numbers))
        .all()
    }

    all_rows = list(rows.values())
    fio_col = _detect_col(all_rows, FIO_KEYWORDS)

    users_map = {u.id: u.name for u in db.query(User).all()}

    result = []
    for a in assignments:
        row = rows.get(a.row_number)
        my_slot = 1 if a.reviewer1_id == user.id else 2
        result.append(
            {
                "row_number": a.row_number,
                "fio": row.data.get(fio_col, "") if row and fio_col else "",
                "reviewer1": users_map.get(a.reviewer1_id) if a.reviewer1_id else None,
                "reviewer2": users_map.get(a.reviewer2_id) if a.reviewer2_id else None,
                "my_slot": my_slot,
                "slot_date": a.slot_date,
                "slot_hour": a.slot_hour,
            }
        )

    # Запланированные (с датой) — по возрастанию даты/часа; без даты — в конце
    result.sort(key=lambda x: (x["slot_date"] is None, x["slot_date"] or "", x["slot_hour"] or 0))

    return {"interviews": result}


@router.get("/assignments")
def get_all_assignments(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Админ: строки собесов + слоты брони + подсказки по доступности проверяющих.

    Для каждой брони со слотом отдаём:
      slot_date, slot_hour, faculty (кандидата),
      available_coord_ids — у кого Availability на этот час и кто не занят другой бронью,
      same_faculty_coord_ids — у кого среди available факультет совпадает с кандидатом.
    """
    # Lazy import во избежание циклов
    from app.routers.admin_ops import (
        _build_id_to_faculty_map,
        _normalize_student_id,
    )
    from app.models import Availability

    rows = (
        db.query(SheetRow)
        .filter(SheetRow.sheet == "interview")
        .order_by(SheetRow.row_number)
        .all()
    )
    assignments = {
        a.row_number: a for a in db.query(InterviewAssignment).all()
    }
    users_map = {u.id: u.name for u in db.query(User).all()}
    coords = (
        db.query(User).filter(User.role == Role.coordinator).order_by(User.name).all()
    )
    coords_by_id = {u.id: u for u in coords}

    # avail: (date, hour) → set(user_id)
    avail_by_slot: dict[tuple[str, int], set[int]] = {}
    for a in db.query(Availability).all():
        avail_by_slot.setdefault((a.slot_date, a.slot_hour), set()).add(a.user_id)

    # busy: координатор уже стоит на другую бронь в этот час
    busy_by_slot: dict[tuple[str, int], set[int]] = {}
    for ia in db.query(InterviewAssignment).filter(
        InterviewAssignment.slot_date.isnot(None)
    ).all():
        key = (ia.slot_date, ia.slot_hour)
        for rid in (ia.reviewer1_id, ia.reviewer2_id):
            if rid:
                busy_by_slot.setdefault(key, set()).add(rid)

    id_to_faculty = _build_id_to_faculty_map(db)

    fio_col = _detect_col(rows, FIO_KEYWORDS)
    sid_col = _detect_col(rows, STUDENT_ID_KEYWORDS)

    result = []
    for row in rows:
        a = assignments.get(row.row_number)
        student_id = row.data.get(sid_col, "") if sid_col else ""
        norm_sid = _normalize_student_id(student_id)
        faculty = id_to_faculty.get(norm_sid, "") if norm_sid else ""

        slot_date = a.slot_date if a else None
        slot_hour = a.slot_hour if a else None
        available_ids: list[int] = []
        same_faculty_ids: list[int] = []
        if slot_date is not None and slot_hour is not None:
            key = (slot_date, slot_hour)
            slot_avail = avail_by_slot.get(key, set())
            slot_busy = busy_by_slot.get(key, set())
            # У занятых исключаем самих себя из «занятого» — они уже стоят на этот же row
            current_pair = {a.reviewer1_id, a.reviewer2_id} - {None}
            slot_busy = slot_busy - current_pair
            for uid in slot_avail:
                if uid in coords_by_id and uid not in slot_busy:
                    available_ids.append(uid)
                    if faculty and faculty in (coords_by_id[uid].faculties or []):
                        same_faculty_ids.append(uid)

        result.append(
            {
                "row_number": row.row_number,
                "fio": row.data.get(fio_col, "") if fio_col else "",
                "student_id": student_id,
                "faculty": faculty,
                "slot_date": slot_date,
                "slot_hour": slot_hour,
                "reviewer1_id": a.reviewer1_id if a else None,
                "reviewer2_id": a.reviewer2_id if a else None,
                "reviewer1": users_map.get(a.reviewer1_id) if a and a.reviewer1_id else None,
                "reviewer2": users_map.get(a.reviewer2_id) if a and a.reviewer2_id else None,
                "available_coord_ids": available_ids,
                "same_faculty_coord_ids": same_faculty_ids,
            }
        )

    # Сортировка: сначала записанные (по дате/часу), потом без слота
    result.sort(key=lambda r: (
        r["slot_date"] is None,
        r["slot_date"] or "",
        r["slot_hour"] if r["slot_hour"] is not None else 0,
        r["row_number"],
    ))

    coordinators = [{"id": u.id, "name": u.name} for u in coords]
    return {"rows": result, "total": len(result), "coordinators": coordinators}


class AssignPayload(BaseModel):
    reviewer1_id: Optional[int] = None
    reviewer2_id: Optional[int] = None


@router.post("/assignments/{row_number}")
def set_assignment(
    row_number: int,
    payload: AssignPayload,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    a = (
        db.query(InterviewAssignment)
        .filter(InterviewAssignment.row_number == row_number)
        .first()
    )
    if a:
        a.reviewer1_id = payload.reviewer1_id
        a.reviewer2_id = payload.reviewer2_id
    else:
        a = InterviewAssignment(
            row_number=row_number,
            reviewer1_id=payload.reviewer1_id,
            reviewer2_id=payload.reviewer2_id,
        )
        db.add(a)
    db.commit()
    return {"ok": True}


class ManualEntryPayload(BaseModel):
    fio: str
    student_id: str = ""


@router.post("/manual")
def create_manual_entry(
    payload: ManualEntryPayload,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Ручное создание записи собеседования (для тестовых «оков»)."""
    existing = db.query(SheetRow).filter(SheetRow.sheet == "interview").all()
    max_rn = max((r.row_number for r in existing), default=10000)
    new_rn = max(max_rn + 1, 10001)

    db.add(
        SheetRow(
            sheet="interview",
            row_number=new_rn,
            data={
                "ФИО": payload.fio,
                "Номер студенческого билета": payload.student_id,
                "_row": new_rn,
                "_manual": True,
            },
        )
    )
    db.commit()
    return {"ok": True, "row_number": new_rn}


@router.get("/{row_number}/info")
def get_interview_info(
    row_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Метаданные собеса: ФИО кандидата, имена проверяющих, слот текущего пользователя."""
    row = db.query(SheetRow).filter(
        SheetRow.sheet == "interview", SheetRow.row_number == row_number
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    a = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == row_number
    ).first()

    users_map = {u.id: u.name for u in db.query(User).all()}
    fio_col = _detect_col([row], FIO_KEYWORDS)

    my_slot = None
    if a:
        if a.reviewer1_id == user.id:
            my_slot = 1
        elif a.reviewer2_id == user.id:
            my_slot = 2

    return {
        "row_number": row_number,
        "fio": row.data.get(fio_col, "") if fio_col else "",
        "my_slot": my_slot,
        "reviewer1": {"id": a.reviewer1_id, "name": users_map.get(a.reviewer1_id)} if a and a.reviewer1_id else None,
        "reviewer2": {"id": a.reviewer2_id, "name": users_map.get(a.reviewer2_id)} if a and a.reviewer2_id else None,
    }


@router.get("/{row_number}/notes")
def get_notes(
    row_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live-заметки обоих проверяющих (Redis → DB fallback)."""
    a = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == row_number
    ).first()

    r1_id = a.reviewer1_id if a else None
    r2_id = a.reviewer2_id if a else None
    users_map = {u.id: u.name for u in db.query(User).all()}

    my_slot = None
    if a:
        if a.reviewer1_id == user.id:
            my_slot = 1
        elif a.reviewer2_id == user.id:
            my_slot = 2

    return {
        "my_slot": my_slot,
        "reviewer1": {
            "id": r1_id,
            "name": users_map.get(r1_id) if r1_id else None,
            "notes": _resolve_notes(row_number, r1_id, db) if r1_id else {},
        },
        "reviewer2": {
            "id": r2_id,
            "name": users_map.get(r2_id) if r2_id else None,
            "notes": _resolve_notes(row_number, r2_id, db) if r2_id else {},
        },
    }


class NotePayload(BaseModel):
    field_key: str
    value: str


@router.post("/{row_number}/note")
def save_note_live(
    row_number: int,
    payload: NotePayload,
    user: User = Depends(get_current_user),
):
    """Автосохранение одного поля в Redis."""
    if _rc is None:
        return {"ok": False, "redis": False}
    try:
        _rc.setex(_note_key(row_number, user.id, payload.field_key), 86400, payload.value)
        return {"ok": True, "redis": True}
    except Exception:
        return {"ok": False, "redis": False}


@router.post("/{row_number}/save")
def save_interview_final(
    row_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Финальное сохранение всех Redis-заметок в БД."""
    notes = _get_live_notes(row_number, user.id)
    if not notes:
        notes = _get_db_notes(row_number, user.id, db)

    review = (
        db.query(Review)
        .filter(
            Review.sheet == "interview",
            Review.row_number == row_number,
            Review.reviewer_id == user.id,
        )
        .first()
    )

    now = datetime.utcnow()
    if review:
        review.scores = notes
        review.synced_to_sheets = False
        review.saved_at = now
    else:
        review = Review(
            sheet="interview",
            row_number=row_number,
            reviewer_id=user.id,
            scores=notes,
            synced_to_sheets=False,
            saved_at=now,
        )
        db.add(review)
    db.commit()
    return {"ok": True, "saved_fields": len(notes)}


# =============================================================================
# Fun panel: эмодзи, счётчик, ракетка
# =============================================================================

def _emoji_key(row_number: int, reviewer_id: int) -> str:
    return f"interview_emoji:{row_number}:{reviewer_id}"

def _counter_key(row_number: int, reviewer_id: int) -> str:
    return f"interview_counter:{row_number}:{reviewer_id}"

def _rocket_key(row_number: int) -> str:
    return f"interview_rocket:{row_number}"

def _chat_key(row_number: int) -> str:
    return f"interview_chat:{row_number}"

def _ttt_key(row_number: int) -> str:
    return f"interview_ttt:{row_number}"

_TTT_WIN_LINES = [
    [0,1,2],[3,4,5],[6,7,8],
    [0,3,6],[1,4,7],[2,5,8],
    [0,4,8],[2,4,6],
]

def _check_ttt_winner(board: list) -> Optional[str]:
    for a, b, c in _TTT_WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(cell != "" for cell in board):
        return "draw"
    return None


def _rocket_current_mult(started_at: float) -> float:
    elapsed = time.time() - started_at
    return round(math.exp(elapsed * 0.1), 2)


@router.get("/{row_number}/fun")
def get_fun(
    row_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Состояние всех fun-активностей: эмодзи, счётчики, ракетка."""
    a = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == row_number
    ).first()
    r1_id = a.reviewer1_id if a else None
    r2_id = a.reviewer2_id if a else None
    users_map = {u.id: u.name for u in db.query(User).filter(
        User.id.in_([x for x in [r1_id, r2_id] if x])
    ).all()}

    # Emojis: читаем очередь для текущего юзера и очищаем
    emojis = []
    if _rc:
        try:
            raw = _rc.get(_emoji_key(row_number, user.id))
            if raw:
                emojis = json.loads(raw)
                _rc.delete(_emoji_key(row_number, user.id))
        except Exception:
            pass

    # Counters
    def _get_count(rid):
        if not rid or not _rc:
            return 0
        try:
            v = _rc.get(_counter_key(row_number, rid))
            return int(v) if v else 0
        except Exception:
            return 0

    counters = {
        "reviewer1": {"id": r1_id, "name": users_map.get(r1_id), "count": _get_count(r1_id)},
        "reviewer2": {"id": r2_id, "name": users_map.get(r2_id), "count": _get_count(r2_id)},
    }

    # Rocket
    rocket: Dict = {"status": "idle"}
    if _rc:
        try:
            raw = _rc.get(_rocket_key(row_number))
            if raw:
                state = json.loads(raw)
                if state["status"] == "flying":
                    cur = _rocket_current_mult(state["started_at"])
                    if cur >= state["crash_mult"]:
                        state["status"] = "crashed"
                        _rc.setex(_rocket_key(row_number), 300, json.dumps(state))
                rocket = {
                    "status": state["status"],
                    "started_at_ms": int(state["started_at"] * 1000),
                    "cashouts": state.get("cashouts", {}),
                }
                if state["status"] == "crashed":
                    rocket["crash_mult"] = state["crash_mult"]
        except Exception:
            pass

    # Chat: read all messages (persistent, not cleared)
    chat_messages = []
    if _rc:
        try:
            raw = _rc.get(_chat_key(row_number))
            if raw:
                chat_messages = json.loads(raw)
        except Exception:
            pass

    # Tic-tac-toe
    ttt = {"board": [""]*9, "turn": "X", "winner": None}
    if _rc:
        try:
            raw = _rc.get(_ttt_key(row_number))
            if raw:
                ttt = json.loads(raw)
        except Exception:
            pass

    my_slot = None
    if a:
        if a.reviewer1_id == user.id:
            my_slot = 1
        elif a.reviewer2_id == user.id:
            my_slot = 2

    return {
        "emojis": emojis,
        "counters": counters,
        "rocket": rocket,
        "chat": chat_messages,
        "ttt": ttt,
        "my_slot": my_slot,
        "my_id": user.id,
    }


class EmojiPayload(BaseModel):
    emoji: str


@router.post("/{row_number}/fun/emoji")
def send_emoji(
    row_number: int,
    payload: EmojiPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if _rc is None:
        return {"ok": False}
    a = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == row_number
    ).first()
    if not a:
        return {"ok": False}
    target_id = a.reviewer2_id if a.reviewer1_id == user.id else a.reviewer1_id
    if not target_id:
        return {"ok": False}
    try:
        key = _emoji_key(row_number, target_id)
        raw = _rc.get(key)
        items = json.loads(raw) if raw else []
        items.append({"emoji": payload.emoji, "from_name": user.name, "ts": time.time()})
        items = items[-10:]
        _rc.setex(key, 60, json.dumps(items))
        return {"ok": True}
    except Exception:
        return {"ok": False}


@router.post("/{row_number}/fun/counter/tap")
def tap_counter(row_number: int, user: User = Depends(get_current_user)):
    if _rc is None:
        return {"ok": False, "count": 0}
    try:
        key = _counter_key(row_number, user.id)
        count = _rc.incr(key)
        _rc.expire(key, 86400)
        return {"ok": True, "count": int(count)}
    except Exception:
        return {"ok": False, "count": 0}


@router.post("/{row_number}/fun/counter/reset")
def reset_counter(row_number: int, user: User = Depends(get_current_user)):
    if _rc is None:
        return {"ok": False}
    try:
        _rc.set(_counter_key(row_number, user.id), 0, ex=86400)
        return {"ok": True}
    except Exception:
        return {"ok": False}


@router.post("/{row_number}/fun/rocket/start")
def start_rocket(row_number: int, user: User = Depends(get_current_user)):
    if _rc is None:
        return {"ok": False}
    try:
        # Классическая crash-формула: выигрыш дома ~5%
        r = random.random()
        if r < 0.05:
            crash_mult = 1.0
        else:
            crash_mult = round(1.0 / (1.0 - r), 2)
            crash_mult = max(1.01, min(crash_mult, 20.0))
        state = {
            "status": "flying",
            "started_at": time.time(),
            "crash_mult": crash_mult,
            "cashouts": {},
        }
        _rc.setex(_rocket_key(row_number), 300, json.dumps(state))
        return {"ok": True}
    except Exception:
        return {"ok": False}


class CashoutPayload(BaseModel):
    multiplier: float


@router.post("/{row_number}/fun/rocket/cashout")
def cashout_rocket(
    row_number: int,
    payload: CashoutPayload,
    user: User = Depends(get_current_user),
):
    if _rc is None:
        return {"ok": False}
    try:
        raw = _rc.get(_rocket_key(row_number))
        if not raw:
            return {"ok": False, "reason": "no_game"}
        state = json.loads(raw)
        if state["status"] != "flying":
            return {"ok": False, "reason": "not_flying"}
        cur = _rocket_current_mult(state["started_at"])
        if cur >= state["crash_mult"]:
            state["status"] = "crashed"
            _rc.setex(_rocket_key(row_number), 300, json.dumps(state))
            return {"ok": False, "reason": "crashed"}
        actual = round(min(payload.multiplier, cur), 2)
        state["cashouts"][str(user.id)] = actual
        _rc.setex(_rocket_key(row_number), 300, json.dumps(state))
        return {"ok": True, "multiplier": actual}
    except Exception:
        return {"ok": False}


class TttMovePayload(BaseModel):
    cell: int  # 0-8


@router.post("/{row_number}/fun/ttt/move")
def ttt_move(
    row_number: int,
    payload: TttMovePayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if _rc is None:
        return {"ok": False}
    if not (0 <= payload.cell <= 8):
        return {"ok": False, "reason": "invalid_cell"}

    a = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == row_number
    ).first()
    if not a:
        return {"ok": False, "reason": "no_assignment"}

    if a.reviewer1_id == user.id:
        symbol = "X"
    elif a.reviewer2_id == user.id:
        symbol = "O"
    else:
        return {"ok": False, "reason": "not_assigned"}

    try:
        raw = _rc.get(_ttt_key(row_number))
        state = json.loads(raw) if raw else {"board": [""]*9, "turn": "X", "winner": None}

        if state.get("winner"):
            return {"ok": False, "reason": "game_over"}
        if state["turn"] != symbol:
            return {"ok": False, "reason": "not_your_turn"}
        if state["board"][payload.cell] != "":
            return {"ok": False, "reason": "cell_taken"}

        state["board"][payload.cell] = symbol
        winner = _check_ttt_winner(state["board"])
        state["winner"] = winner
        if not winner:
            state["turn"] = "O" if symbol == "X" else "X"

        _rc.setex(_ttt_key(row_number), 86400, json.dumps(state))
        return {"ok": True, "state": state}
    except Exception:
        return {"ok": False}


@router.post("/{row_number}/fun/ttt/reset")
def ttt_reset(row_number: int, user: User = Depends(get_current_user)):
    if _rc is None:
        return {"ok": False}
    try:
        state = {"board": [""]*9, "turn": "X", "winner": None}
        _rc.setex(_ttt_key(row_number), 86400, json.dumps(state))
        return {"ok": True, "state": state}
    except Exception:
        return {"ok": False}


class ChatPayload(BaseModel):
    text: str


@router.post("/{row_number}/fun/chat")
def send_chat(
    row_number: int,
    payload: ChatPayload,
    user: User = Depends(get_current_user),
):
    if _rc is None:
        return {"ok": False}
    text = payload.text.strip()[:300]
    if not text:
        return {"ok": False}
    try:
        key = _chat_key(row_number)
        raw = _rc.get(key)
        messages = json.loads(raw) if raw else []
        messages.append({
            "id": f"{time.time()}-{user.id}",
            "user_id": user.id,
            "name": user.name,
            "text": text,
            "ts": time.time(),
        })
        messages = messages[-100:]
        _rc.setex(key, 86400, json.dumps(messages))
        return {"ok": True}
    except Exception:
        return {"ok": False}


@router.post("/{row_number}/fun/rocket/reset")
def reset_rocket(row_number: int, user: User = Depends(get_current_user)):
    if _rc is None:
        return {"ok": False}
    try:
        _rc.delete(_rocket_key(row_number))
        return {"ok": True}
    except Exception:
        return {"ok": False}
