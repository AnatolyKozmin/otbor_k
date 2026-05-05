"""
Занятость координаторов по часовым слотам в мае 2026.

Каждый юзер видит только свою занятость и может её перезаписать.
Хранится только список слотов «могу»; отсутствие = «не могу».
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Availability, User

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
