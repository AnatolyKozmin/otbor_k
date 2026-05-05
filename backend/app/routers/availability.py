"""
Занятость координаторов по часовым слотам в мае 2026.

Каждый юзер видит только свою занятость и может её перезаписать.
Хранится только список слотов «могу»; отсутствие = «не могу».
"""
from collections import defaultdict
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Availability, SlotCapacity, User, Role

# Жёстко зашитые рамки периода — нет смысла принимать их с клиента.
ALLOWED_DATES = {f"2026-05-{d:02d}" for d in range(9, 24)}  # 9..23
ALLOWED_HOURS = set(range(9, 22))                            # 9..21

router = APIRouter(prefix="/availability", tags=["availability"])


class SlotIn(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    hour: int = Field(..., ge=9, le=21)


class AvailabilityPayload(BaseModel):
    slots: List[SlotIn]


@router.get("/me")
def get_my_availability(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.query(Availability).filter(Availability.user_id == user.id).all()
    return {"slots": [{"date": r.slot_date, "hour": r.slot_hour} for r in rows]}


@router.put("/me")
def save_my_availability(
    payload: AvailabilityPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Валидация: даты и часы должны быть из разрешённого периода.
    # Дубликаты схлопываем через set, чтобы UI не мог случайно прислать дважды.
    seen = set()
    for s in payload.slots:
        if s.date not in ALLOWED_DATES:
            raise HTTPException(400, f"Дата вне диапазона 9–23 мая 2026: {s.date}")
        if s.hour not in ALLOWED_HOURS:
            raise HTTPException(400, f"Час вне диапазона 9–21: {s.hour}")
        seen.add((s.date, s.hour))

    # Стратегия replace: проще валидировать и переписывать целиком,
    # чем считать diff. Объёмы маленькие (≤ 195 слотов на юзера).
    db.query(Availability).filter(Availability.user_id == user.id).delete()
    for date, hour in seen:
        db.add(Availability(user_id=user.id, slot_date=date, slot_hour=hour))
    db.commit()
    return {"ok": True, "count": len(seen)}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

class CapacityIn(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    hour: int = Field(..., ge=9, le=21)
    capacity: int = Field(..., ge=0)


@router.get("/admin/overview")
def admin_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Для каждого слота: количество доступных координаторов, их список, ёмкость."""
    # Загружаем всю занятость координаторов
    avail_rows = (
        db.query(Availability, User.name)
        .join(User, Availability.user_id == User.id)
        .filter(User.role == Role.coordinator)
        .all()
    )

    # slot_key → [name, ...]
    slot_people: dict = defaultdict(list)
    for avail, name in avail_rows:
        slot_people[f"{avail.slot_date}:{avail.slot_hour}"].append(name)

    # Загружаем ёмкости
    capacities = {
        f"{c.slot_date}:{c.slot_hour}": c.capacity
        for c in db.query(SlotCapacity).all()
    }

    # Собираем все слоты из периода
    slots = []
    for d in range(9, 24):
        date = f"2026-05-{d:02d}"
        for h in range(9, 22):
            key = f"{date}:{h}"
            people = sorted(slot_people.get(key, []))
            slots.append({
                "date": date,
                "hour": h,
                "count": len(people),
                "people": people,
                "capacity": capacities.get(key, 0),
            })

    return {"slots": slots}


@router.put("/admin/capacity")
def set_capacity(
    payload: CapacityIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if payload.date not in ALLOWED_DATES:
        raise HTTPException(400, f"Дата вне диапазона: {payload.date}")
    if payload.hour not in ALLOWED_HOURS:
        raise HTTPException(400, f"Час вне диапазона: {payload.hour}")

    row = (
        db.query(SlotCapacity)
        .filter(SlotCapacity.slot_date == payload.date, SlotCapacity.slot_hour == payload.hour)
        .first()
    )
    if row:
        row.capacity = payload.capacity
    else:
        db.add(SlotCapacity(slot_date=payload.date, slot_hour=payload.hour, capacity=payload.capacity))
    db.commit()
    return {"ok": True}
