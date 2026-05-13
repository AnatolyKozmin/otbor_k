"""Публичная запись кандидатов на собеседование.

Кандидат не аутентифицирован — только знает свой студенческий билет.
Допуск к записи определяется по строкам листа **Анкеты**, загруженным в БД (sheet_rows).
ФИО и факультет берём из этой же строки анкеты.

Для совместимости с модулем собесов у каждой брони есть строка листа **Собес**:
если кандидата там ещё нет (по номеру билета), при первой успешной записи создаём
синтетическую строку «Собес», как при ручном добавлении в админке.

Слоты группируются по приоритету:
- recommended: где ≥2 свободных проверяющих с факультета кандидата
- other:       где ≥2 свободных проверяющих с других факультетов
"""
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Availability,
    InterviewAssignment,
    Role,
    SheetRow,
    SlotCapacity,
    User,
    utc_naive_now,
)
from app.routers.admin_ops import (
    _build_id_to_faculty_map,
    _detect_faculty_col,
    _detect_fio_col,
    _detect_student_id_col,
    _normalize_student_id,
)

router = APIRouter(prefix="/booking", tags=["booking"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_anketa_row(db: Session, norm_sid: str) -> Optional[SheetRow]:
    """Строка анкеты в БД по нормализованному студ. билету."""
    rows = db.query(SheetRow).filter(SheetRow.sheet == "anketa").order_by(SheetRow.row_number).all()
    if not rows:
        return None
    sid_col = _detect_student_id_col(rows)
    if not sid_col:
        return None
    for r in rows:
        if _normalize_student_id(r.data.get(sid_col, "")) == norm_sid:
            return r
    return None


def _find_interview_row_by_ticket(db: Session, norm_sid: str) -> Optional[SheetRow]:
    """Строка листа «Собес» по билету (если уже есть в базе)."""
    rows = db.query(SheetRow).filter(SheetRow.sheet == "interview").all()
    if not rows:
        return None
    sid_col = _detect_student_id_col(rows)
    if not sid_col:
        return None
    for r in rows:
        if _normalize_student_id(r.data.get(sid_col, "")) == norm_sid:
            return r
    return None


def _candidate_faculty(db: Session, anketa_row: SheetRow, norm_sid: str) -> str:
    """Факультет из строки анкеты; если колонку не нашли — fallback через карту анкет."""
    fc = _detect_faculty_col([anketa_row])
    if fc:
        v = str(anketa_row.data.get(fc, "") or "").strip()
        if v:
            return v
    return _build_id_to_faculty_map(db).get(norm_sid, "")


def _candidate_fio(anketa_row: SheetRow) -> str:
    fc = _detect_fio_col([anketa_row])
    if fc:
        return str(anketa_row.data.get(fc, "") or "").strip()
    return ""


def _booking_row_number_display(db: Session, norm_sid: str, anketa_row: SheetRow) -> int:
    """Номер строки для ответа API: приоритет строки «Собес», иначе строка анкеты."""
    hit = _find_interview_row_by_ticket(db, norm_sid)
    return hit.row_number if hit else anketa_row.row_number


def _already_booking_payload(db: Session, norm_sid: str) -> Optional[dict]:
    """Есть ли активная бронь по билету (через строку «Собес» с тем же билетом).

    Проверяющие могут быть ещё не назначены — это нормально (админ сделает позже).
    """
    int_row = _find_interview_row_by_ticket(db, norm_sid)
    if not int_row:
        return None
    existing = (
        db.query(InterviewAssignment)
        .filter(
            InterviewAssignment.row_number == int_row.row_number,
            InterviewAssignment.slot_date.isnot(None),
        )
        .first()
    )
    if not existing:
        return None
    r1 = db.query(User).filter(User.id == existing.reviewer1_id).first() if existing.reviewer1_id else None
    r2 = db.query(User).filter(User.id == existing.reviewer2_id).first() if existing.reviewer2_id else None
    return {
        "slot_date": existing.slot_date,
        "slot_hour": existing.slot_hour,
        "reviewer1": r1.name if r1 else None,
        "reviewer2": r2.name if r2 else None,
        "reviewers_pending": not (r1 and r2),
        "cancel_count": existing.cancel_count or 0,
    }


def _ensure_interview_row_for_booking(db: Session, anketa_row: SheetRow, norm_sid: str) -> SheetRow:
    """Гарантируем строку «Собес» для InterviewAssignment (создаём при отсутствии)."""
    hit = _find_interview_row_by_ticket(db, norm_sid)
    if hit:
        return hit

    rows = db.query(SheetRow).filter(SheetRow.sheet == "interview").all()
    max_rn = max((r.row_number for r in rows), default=10000)
    new_rn = max(max_rn + 1, 10001)

    ar = [anketa_row]
    fio_col = _detect_fio_col(ar)
    sid_col_a = _detect_student_id_col(ar)
    fio_val = str(anketa_row.data.get(fio_col, "") or "").strip() if fio_col else ""
    ticket_raw = str(anketa_row.data.get(sid_col_a, "") or "").strip() if sid_col_a else norm_sid

    row = SheetRow(
        sheet="interview",
        row_number=new_rn,
        data={
            "_row": new_rn,
            "_from_anketa_row": anketa_row.row_number,
            "ФИО": fio_val or "—",
            "Номер студенческого билета": ticket_raw,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _slot_availability_index(db: Session):
    """Строит индексы доступности и бронирований.

    Возвращает:
        - avail_by_slot: (date, hour) → set(user_id)
        - bookings_count_by_slot: (date, hour) → int
        - busy_users_by_slot: (date, hour) → set(user_id)
        - admin_caps: (date, hour) → int | None  (лимит из SlotCapacity, если задан)
    """
    avail_by_slot: dict[tuple[str, int], set[int]] = defaultdict(set)
    for a in db.query(Availability).all():
        avail_by_slot[(a.slot_date, a.slot_hour)].add(a.user_id)

    booked = db.query(InterviewAssignment).filter(
        InterviewAssignment.slot_date.isnot(None)
    ).all()
    bookings_count_by_slot: dict[tuple[str, int], int] = defaultdict(int)
    busy_users_by_slot: dict[tuple[str, int], set[int]] = defaultdict(set)
    for b in booked:
        key = (b.slot_date, b.slot_hour)
        bookings_count_by_slot[key] += 1
        if b.reviewer1_id:
            busy_users_by_slot[key].add(b.reviewer1_id)
        if b.reviewer2_id:
            busy_users_by_slot[key].add(b.reviewer2_id)

    admin_caps: dict[tuple[str, int], int] = {
        (c.slot_date, c.slot_hour): c.capacity
        for c in db.query(SlotCapacity).all()
        if c.capacity > 0
    }

    return avail_by_slot, bookings_count_by_slot, busy_users_by_slot, admin_caps


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/lookup")
def lookup(student_id: str = Query(...), db: Session = Depends(get_db)):
    """Шаг 1: кандидат должен быть в загруженных анкетах; ФИО и факультет — из анкеты."""
    norm_sid = _normalize_student_id(student_id)
    if not norm_sid:
        raise HTTPException(400, "Введите корректный номер студенческого билета")

    anketa_row = _find_anketa_row(db, norm_sid)
    if not anketa_row:
        raise HTTPException(
            404,
            "Не нашли вас среди загруженных анкет. Проверьте номер билета "
            "или дождитесь, когда координаторы обновят данные из таблицы.",
        )

    fio = _candidate_fio(anketa_row)
    faculty = _candidate_faculty(db, anketa_row, norm_sid)
    already_booked = _already_booking_payload(db, norm_sid)

    return {
        "row_number": _booking_row_number_display(db, norm_sid, anketa_row),
        "fio": fio,
        "faculty": faculty,
        "already_booked": already_booked,
    }


@router.get("/slots")
def slots(student_id: str = Query(...), db: Session = Depends(get_db)):
    """Шаг 2: возвращаем доступные слоты, отсортированные и помеченные recommended/other."""
    norm_sid = _normalize_student_id(student_id)
    if not norm_sid:
        raise HTTPException(400, "Некорректный билет")

    anketa_row = _find_anketa_row(db, norm_sid)
    if not anketa_row:
        raise HTTPException(404, "Нет такого билета среди загруженных анкет")

    candidate_faculty = _candidate_faculty(db, anketa_row, norm_sid)

    avail, bookings_count, busy, admin_caps = _slot_availability_index(db)

    # Активные координаторы
    coords = {
        u.id: u for u in db.query(User).filter(User.role == Role.coordinator).all()
    }

    result = []
    now = datetime.now()

    for (date, hour), slot_avail in avail.items():
        # Запись закрывается за 12 часов до начала слота
        slot_start = datetime.strptime(f"{date} {hour}:00", "%Y-%m-%d %H:%M")
        if (slot_start - now).total_seconds() < 12 * 3600:
            continue

        slot_busy = busy.get((date, hour), set())
        free_ids = [uid for uid in slot_avail if uid not in slot_busy and uid in coords]
        if len(free_ids) < 2:
            continue

        # Ёмкость: если админ задал лимит — берём его, иначе авто по коордам
        auto_cap = len(free_ids) // 2
        key = (date, hour)
        capacity = admin_caps[key] if key in admin_caps else auto_cap
        if bookings_count.get(key, 0) >= capacity:
            continue

        same_fac = [uid for uid in free_ids if candidate_faculty and candidate_faculty in (coords[uid].faculties or [])]
        slot_type = "recommended" if len(same_fac) >= 2 else "other"

        result.append({
            "date": date,
            "hour": hour,
            "type": slot_type,
            "free_count": len(free_ids),
            "free_capacity": capacity - bookings_count.get(key, 0),
        })

    result.sort(key=lambda s: (s["date"], s["hour"]))

    # Две секции: рекомендованные (пара 2 коорда с факультетом кандидата) и остальные
    rec_by_date: dict[str, list] = defaultdict(list)
    other_by_date: dict[str, list] = defaultdict(list)
    for s in result:
        bucket = rec_by_date if s["type"] == "recommended" else other_by_date
        bucket[s["date"]].append(s)

    return {
        "candidate_faculty": candidate_faculty,
        "recommended": {
            "dates": [{"date": d, "slots": rec_by_date[d]} for d in sorted(rec_by_date.keys())],
        },
        "other": {
            "dates": [{"date": d, "slots": other_by_date[d]} for d in sorted(other_by_date.keys())],
        },
    }


class BookPayload(BaseModel):
    student_id: str
    slot_date: str
    slot_hour: int


@router.post("/book")
def book(payload: BookPayload, db: Session = Depends(get_db)):
    """Шаг 3: бронируем слот (дата+время). Проверяющих назначает админ позже."""
    norm_sid = _normalize_student_id(payload.student_id)
    if not norm_sid:
        raise HTTPException(400, "Некорректный билет")

    anketa_row = _find_anketa_row(db, norm_sid)
    if not anketa_row:
        raise HTTPException(404, "Нет такого билета среди загруженных анкет")

    interview_row = _ensure_interview_row_for_booking(db, anketa_row, norm_sid)

    # Проверка: до слота >= 12 часов
    slot_start = datetime.strptime(f"{payload.slot_date} {payload.slot_hour}:00", "%Y-%m-%d %H:%M")
    if (slot_start - datetime.now()).total_seconds() < 12 * 3600:
        raise HTTPException(400, "Запись на этот слот закрыта (менее 12 часов до начала)")

    # Проверка: слот всё ещё свободен (достаточно свободных коордов)
    avail, bookings_count_now, busy, admin_caps = _slot_availability_index(db)
    coords = {u.id: u for u in db.query(User).filter(User.role == Role.coordinator).all()}
    key = (payload.slot_date, payload.slot_hour)
    slot_avail = avail.get(key, set())
    slot_busy = busy.get(key, set())
    free_ids = [uid for uid in slot_avail if uid not in slot_busy and uid in coords]
    if len(free_ids) < 2:
        raise HTTPException(409, "В этом слоте не осталось двух свободных проверяющих")

    auto_cap = len(free_ids) // 2
    capacity = admin_caps[key] if key in admin_caps else auto_cap
    booked_count = bookings_count_now.get(key, 0)
    if booked_count >= capacity:
        raise HTTPException(409, "Слот только что заняли, выберите другой")

    # Создаём или обновляем бронь (перезапись разрешена — проверяющих сбрасываем)
    ia = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == interview_row.row_number
    ).first()
    if ia:
        ia.slot_date = payload.slot_date
        ia.slot_hour = payload.slot_hour
        ia.reviewer1_id = None
        ia.reviewer2_id = None
        ia.booked_at = utc_naive_now()
    else:
        ia = InterviewAssignment(
            row_number=interview_row.row_number,
            slot_date=payload.slot_date,
            slot_hour=payload.slot_hour,
            booked_at=utc_naive_now(),
        )
        db.add(ia)

    db.commit()
    db.refresh(ia)

    return {
        "ok": True,
        "slot_date": ia.slot_date,
        "slot_hour": ia.slot_hour,
        "reviewers_pending": True,
    }


class CancelPayload(BaseModel):
    student_id: str


@router.post("/cancel")
def cancel_booking(payload: CancelPayload, db: Session = Depends(get_db)):
    """Кандидат отменяет запись. Разрешено 1 раз, не менее чем за 12 часов."""
    norm_sid = _normalize_student_id(payload.student_id)
    if not norm_sid:
        raise HTTPException(400, "Некорректный билет")

    int_row = _find_interview_row_by_ticket(db, norm_sid)
    if not int_row:
        raise HTTPException(404, "Запись не найдена")

    ia = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == int_row.row_number,
        InterviewAssignment.slot_date.isnot(None),
    ).first()
    if not ia:
        raise HTTPException(404, "Активная запись не найдена")

    if (ia.cancel_count or 0) >= 1:
        raise HTTPException(409, "Отмена уже была использована. Повторная отмена невозможна.")

    slot_start = datetime.strptime(f"{ia.slot_date} {ia.slot_hour}:00", "%Y-%m-%d %H:%M")
    if (slot_start - datetime.now()).total_seconds() < 12 * 3600:
        raise HTTPException(400, "Отменить запись можно не менее чем за 12 часов до собеседования.")

    ia.slot_date = None
    ia.slot_hour = None
    ia.reviewer1_id = None
    ia.reviewer2_id = None
    ia.cancel_count = 1
    db.commit()

    return {"ok": True}
