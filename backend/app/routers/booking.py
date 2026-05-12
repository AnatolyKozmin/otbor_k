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
    """Есть ли активная бронь по билету (через строку «Собес» с тем же билетом)."""
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
    r1 = db.query(User).filter(User.id == existing.reviewer1_id).first()
    r2 = db.query(User).filter(User.id == existing.reviewer2_id).first()
    return {
        "slot_date": existing.slot_date,
        "slot_hour": existing.slot_hour,
        "reviewer1": r1.name if r1 else None,
        "reviewer2": r2.name if r2 else None,
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
    """Строит индексы: что у нас по доступности и бронированиям.

    Возвращает:
        - avail_by_slot: (date, hour) → set(user_id) — кто может в этот час
        - bookings_count_by_slot: (date, hour) → int — сколько собесов уже в час
        - busy_users_by_slot: (date, hour) → set(user_id) — кто уже занят
        - capacities: {(date, hour): capacity}
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

    capacities = {
        (c.slot_date, c.slot_hour): c.capacity
        for c in db.query(SlotCapacity).all()
    }

    return avail_by_slot, bookings_count_by_slot, busy_users_by_slot, capacities


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

    avail, bookings_count, busy, capacities = _slot_availability_index(db)

    # Активные координаторы
    coords = {
        u.id: u for u in db.query(User).filter(User.role == Role.coordinator).all()
    }

    result = []
    today = datetime.now().strftime("%Y-%m-%d")

    for (date, hour), cap in capacities.items():
        if cap <= 0 or date < today:
            continue
        if bookings_count.get((date, hour), 0) >= cap:
            continue

        # Доступные коорды на этот слот
        slot_avail = avail.get((date, hour), set())
        slot_busy = busy.get((date, hour), set())
        free_ids = [uid for uid in slot_avail if uid not in slot_busy and uid in coords]
        if len(free_ids) < 2:
            continue

        same_fac = [uid for uid in free_ids if candidate_faculty and candidate_faculty in (coords[uid].faculties or [])]
        slot_type = "recommended" if len(same_fac) >= 2 else "other"

        result.append({
            "date": date,
            "hour": hour,
            "type": slot_type,
            "free_count": len(free_ids),
            "free_capacity": cap - bookings_count.get((date, hour), 0),
        })

    result.sort(key=lambda s: (s["date"], s["hour"]))

    # Группировка по дате для удобства фронта
    by_date: dict[str, list] = defaultdict(list)
    for s in result:
        by_date[s["date"]].append(s)

    return {
        "candidate_faculty": candidate_faculty,
        "dates": [{"date": d, "slots": by_date[d]} for d in sorted(by_date.keys())],
    }


class BookPayload(BaseModel):
    student_id: str
    slot_date: str
    slot_hour: int


@router.post("/book")
def book(payload: BookPayload, db: Session = Depends(get_db)):
    """Шаг 3: бронируем слот, авто-выбирая 2 проверяющих."""
    norm_sid = _normalize_student_id(payload.student_id)
    if not norm_sid:
        raise HTTPException(400, "Некорректный билет")

    anketa_row = _find_anketa_row(db, norm_sid)
    if not anketa_row:
        raise HTTPException(404, "Нет такого билета среди загруженных анкет")

    interview_row = _ensure_interview_row_for_booking(db, anketa_row, norm_sid)
    candidate_faculty = _candidate_faculty(db, anketa_row, norm_sid)

    # Проверка: уже забронирован?
    existing = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == interview_row.row_number,
        InterviewAssignment.slot_date.isnot(None),
    ).first()
    if existing:
        raise HTTPException(409, "Вы уже записаны. Если хотите перенести — свяжитесь с координатором.")

    # Проверка: слот всё ещё свободен
    cap_row = db.query(SlotCapacity).filter(
        SlotCapacity.slot_date == payload.slot_date,
        SlotCapacity.slot_hour == payload.slot_hour,
    ).first()
    if not cap_row or cap_row.capacity <= 0:
        raise HTTPException(400, "Слот недоступен")

    booked_count = db.query(InterviewAssignment).filter(
        InterviewAssignment.slot_date == payload.slot_date,
        InterviewAssignment.slot_hour == payload.slot_hour,
    ).count()
    if booked_count >= cap_row.capacity:
        raise HTTPException(409, "Слот только что заняли, выберите другой")

    # Доступные проверяющие в этот слот
    avail, _, busy, _ = _slot_availability_index(db)
    coords = {u.id: u for u in db.query(User).filter(User.role == Role.coordinator).all()}
    slot_avail = avail.get((payload.slot_date, payload.slot_hour), set())
    slot_busy = busy.get((payload.slot_date, payload.slot_hour), set())
    free_ids = [uid for uid in slot_avail if uid not in slot_busy and uid in coords]

    if len(free_ids) < 2:
        raise HTTPException(409, "В этом слоте не осталось двух свободных проверяющих")

    # Приоритет — факультет кандидата
    same_fac = [uid for uid in free_ids if candidate_faculty and candidate_faculty in (coords[uid].faculties or [])]
    other = [uid for uid in free_ids if uid not in same_fac]

    picked: list[int] = []
    picked.extend(same_fac[:2])
    if len(picked) < 2:
        picked.extend(other[: 2 - len(picked)])

    if len(picked) < 2:
        raise HTTPException(409, "Не удалось подобрать двух проверяющих")

    # Сохраняем — обновляем существующий assignment или создаём новый
    ia = db.query(InterviewAssignment).filter(
        InterviewAssignment.row_number == interview_row.row_number
    ).first()
    if ia:
        ia.reviewer1_id = picked[0]
        ia.reviewer2_id = picked[1]
        ia.slot_date = payload.slot_date
        ia.slot_hour = payload.slot_hour
        ia.booked_at = utc_naive_now()
    else:
        ia = InterviewAssignment(
            row_number=interview_row.row_number,
            reviewer1_id=picked[0],
            reviewer2_id=picked[1],
            slot_date=payload.slot_date,
            slot_hour=payload.slot_hour,
            booked_at=utc_naive_now(),
        )
        db.add(ia)

    db.commit()
    db.refresh(ia)

    r1 = coords[picked[0]]
    r2 = coords[picked[1]]
    return {
        "ok": True,
        "slot_date": ia.slot_date,
        "slot_hour": ia.slot_hour,
        "reviewer1": r1.name,
        "reviewer2": r2.name,
    }
