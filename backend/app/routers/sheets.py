from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Assignment, SheetRow, SHEET_KEYS, User, Role
from app.sheets import GoogleSheetsEngine

router = APIRouter(prefix="/sheets", tags=["sheets"])


@router.post("/load", response_model=Dict[str, int])
def load_sheets(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Загружает все три листа из Google Sheets и сохраняет в БД."""
    try:
        engine = GoogleSheetsEngine()
        all_data = engine.load_all()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка Google Sheets: {exc}")

    counts: Dict[str, int] = {}
    for sheet_key, (_, rows) in all_data.items():
        if sheet_key == "interview":
            # Удаляем только строки из Google Sheets (row_number < 10000).
            # Синтетические строки бронирования (≥ 10000) сохраняем —
            # на них ссылаются InterviewAssignment записи кандидатов.
            db.query(SheetRow).filter(
                SheetRow.sheet == sheet_key,
                SheetRow.row_number < 10000,
            ).delete()
        else:
            db.query(SheetRow).filter(SheetRow.sheet == sheet_key).delete()

        for row in rows:
            rn = row.get("_row", 0)
            # Для interview пропускаем строки, которые уже есть как синтетические
            if sheet_key == "interview" and rn >= 10000:
                continue
            db.add(SheetRow(sheet=sheet_key, row_number=rn, data=row))
        counts[sheet_key] = len(rows)

    db.commit()
    return counts


@router.get("/{sheet}", response_model=Dict[str, Any])
def get_sheet(
    sheet: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Возвращает строки для листа.

    Администратор видит все строки.
    Координатор видит только назначенные ему (если распределение уже выполнено).
    """
    if sheet not in SHEET_KEYS:
        raise HTTPException(status_code=404, detail="Лист не найден")

    query = db.query(SheetRow).filter(SheetRow.sheet == sheet)

    if user.role == Role.coordinator:
        # Проверяем: есть ли вообще распределение для этого листа
        has_assignments = (
            db.query(Assignment).filter(Assignment.sheet == sheet).limit(1).count() > 0
        )
        if has_assignments:
            assigned_rows_select = (
                select(Assignment.row_number)
                .where(Assignment.sheet == sheet, Assignment.reviewer_id == user.id)
            )
            query = query.filter(SheetRow.row_number.in_(assigned_rows_select))

    rows = query.order_by(SheetRow.row_number).all()

    if not rows:
        return {"headers": [], "rows": [], "total": 0}

    headers: List[str] = [k for k in rows[0].data.keys() if not k.startswith("_")]

    return {
        "headers": headers,
        "rows": [r.data for r in rows],
        "total": len(rows),
    }


@router.get("/{sheet}/{row_number}", response_model=Dict[str, Any])
def get_sheet_row(
    sheet: str,
    row_number: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Возвращает одну строку по номеру."""
    if sheet not in SHEET_KEYS:
        raise HTTPException(status_code=404, detail="Лист не найден")

    row = (
        db.query(SheetRow)
        .filter(SheetRow.sheet == sheet, SheetRow.row_number == row_number)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    return {"row": row.data}
