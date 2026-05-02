"""
Административные операции: распределение анкет между проверяющими.
"""
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import Assignment, Review, SheetRow, SHEET_KEYS, User, Role
from app.sync import do_full_export

FACULTY_NAMES = {'НАБ', 'ФЭБ', 'ВШУ', 'ИТиАБД', 'СНиМК', 'МЭО', 'Финфак', 'Юрфак'}
FIO_KEYWORDS = ["фио", "имя", "фамилия", "ф.и.о"]

router = APIRouter(prefix="/admin", tags=["admin"])


def _detect_fio_col(rows: List) -> Optional[str]:
    if not rows:
        return None
    for col in rows[0].data.keys():
        if col.startswith("_"):
            continue
        if any(kw in col.lower() for kw in FIO_KEYWORDS):
            return col
    return None


def _detect_faculty_col(rows: List) -> Optional[str]:
    """Ищет колонку, значения которой чаще всего совпадают с названиями факультетов."""
    if not rows:
        return None
    sample = rows[:min(60, len(rows))]
    best_col, best_score = None, 0
    for col in rows[0].data.keys():
        if col.startswith("_"):
            continue
        score = sum(1 for r in sample if r.data.get(col, "").strip() in FACULTY_NAMES)
        if score > best_score:
            best_score = score
            best_col = col
    threshold = max(1, len(sample) * 0.2)
    return best_col if best_score >= threshold else None


class DistributeRequest(BaseModel):
    sheet: str = "anketa"


@router.post("/distribute")
def distribute(
    req: DistributeRequest = DistributeRequest(),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Равномерно распределяет строки листа между координаторами по их факультетам."""
    sheet = req.sheet

    coordinators = [
        c for c in db.query(User).filter(User.role == Role.coordinator).all()
        if c.faculties
    ]
    if not coordinators:
        raise HTTPException(
            status_code=400,
            detail="Нет координаторов с назначенными факультетами. "
                   "Сначала назначьте факультеты через таблицу пользователей.",
        )

    rows = db.query(SheetRow).filter(SheetRow.sheet == sheet).order_by(SheetRow.row_number).all()
    if not rows:
        raise HTTPException(
            status_code=400,
            detail=f"Нет загруженных данных для листа «{sheet}». "
                   "Сначала загрузите данные из Google Sheets.",
        )

    faculty_col = _detect_faculty_col(rows)
    if not faculty_col:
        raise HTTPException(
            status_code=400,
            detail="Не удалось автоматически определить столбец с факультетом. "
                   "Убедитесь, что данные загружены корректно.",
        )

    # faculty → [coordinator_id, ...]
    faculty_to_coords: Dict[str, List[int]] = defaultdict(list)
    for coord in coordinators:
        for fac in coord.faculties:
            faculty_to_coords[fac].append(coord.id)

    # Очищаем предыдущее распределение
    db.query(Assignment).filter(Assignment.sheet == sheet).delete()
    db.flush()

    coord_counts: Dict[int, int] = defaultdict(int)
    unassigned_faculties: Dict[str, int] = defaultdict(int)
    assigned = 0

    for row in rows:
        faculty = row.data.get(faculty_col, "").strip()
        candidates = faculty_to_coords.get(faculty, [])
        if not candidates:
            unassigned_faculties[faculty or "—"] += 1
            continue
        # Назначаем координатору с наименьшим числом анкет (round-robin по минимуму)
        best_id = min(candidates, key=lambda cid: coord_counts[cid])
        db.add(Assignment(sheet=sheet, row_number=row.row_number, reviewer_id=best_id))
        coord_counts[best_id] += 1
        assigned += 1

    db.commit()

    id_to_name = {c.id: c.name for c in coordinators}
    distribution = {
        id_to_name[cid]: cnt
        for cid, cnt in sorted(coord_counts.items(), key=lambda x: -x[1])
    }

    return {
        "assigned": assigned,
        "unassigned": sum(unassigned_faculties.values()),
        "unassigned_faculties": dict(unassigned_faculties),
        "faculty_column": faculty_col,
        "distribution": distribution,
    }


@router.get("/assignments/{sheet}")
def get_assignments(
    sheet: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Таблица: ФИО, факультет, назначенный проверяющий (для всех строк листа)."""
    rows = (
        db.query(SheetRow)
        .filter(SheetRow.sheet == sheet)
        .order_by(SheetRow.row_number)
        .all()
    )
    if not rows:
        return {"rows": [], "total": 0, "assigned": 0, "fio_column": None, "faculty_column": None}

    fio_col = _detect_fio_col(rows)
    faculty_col = _detect_faculty_col(rows)

    # Загружаем все назначения и пользователей одним запросом
    assignments = {
        a.row_number: a
        for a in db.query(Assignment).filter(Assignment.sheet == sheet).all()
    }
    users_map = {u.id: u.name for u in db.query(User).all()}

    result = []
    for row in rows:
        asgn = assignments.get(row.row_number)
        result.append({
            "row_number": row.row_number,
            "fio": row.data.get(fio_col, "") if fio_col else "",
            "faculty": row.data.get(faculty_col, "") if faculty_col else "",
            "reviewer": users_map.get(asgn.reviewer_id) if asgn else None,
        })

    assigned = sum(1 for r in result if r["reviewer"])
    return {
        "rows": result,
        "total": len(result),
        "assigned": assigned,
        "fio_column": fio_col,
        "faculty_column": faculty_col,
    }


@router.get("/distribution-overview")
def distribution_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Сводка для дашборда: сколько анкет/домашек/собесов назначено каждому координатору
    + сколько уже проверено."""
    coords = (
        db.query(User)
        .filter(User.role == Role.coordinator)
        .order_by(User.name)
        .all()
    )

    # Назначения: (reviewer_id, sheet) → count
    asgn_rows = (
        db.query(Assignment.reviewer_id, Assignment.sheet, func.count(Assignment.id))
        .group_by(Assignment.reviewer_id, Assignment.sheet)
        .all()
    )
    assigned_map: Dict[int, Dict[str, int]] = defaultdict(
        lambda: {k: 0 for k in SHEET_KEYS}
    )
    for rid, sheet, cnt in asgn_rows:
        if sheet in SHEET_KEYS:
            assigned_map[rid][sheet] = cnt

    # Проверено: (reviewer_id, sheet) → count
    rev_rows = (
        db.query(Review.reviewer_id, Review.sheet, func.count(Review.id))
        .group_by(Review.reviewer_id, Review.sheet)
        .all()
    )
    reviewed_map: Dict[int, Dict[str, int]] = defaultdict(
        lambda: {k: 0 for k in SHEET_KEYS}
    )
    for rid, sheet, cnt in rev_rows:
        if sheet in SHEET_KEYS:
            reviewed_map[rid][sheet] = cnt

    coordinators = [
        {
            "id": c.id,
            "name": c.name,
            "faculties": c.faculties or [],
            "assigned": assigned_map[c.id],
            "reviewed": reviewed_map[c.id],
        }
        for c in coords
    ]

    # Totals считаем по ВСЕМ записям (включая проверки админа), а не суммой
    # по координаторам — иначе review админа теряется и счётчик стоит на нуле.
    totals_assigned = {k: 0 for k in SHEET_KEYS}
    totals_reviewed = {k: 0 for k in SHEET_KEYS}
    for _rid, sheet, cnt in asgn_rows:
        if sheet in SHEET_KEYS:
            totals_assigned[sheet] += cnt
    for _rid, sheet, cnt in rev_rows:
        if sheet in SHEET_KEYS:
            totals_reviewed[sheet] += cnt

    return {
        "coordinators": coordinators,
        "totals_assigned": totals_assigned,
        "totals_reviewed": totals_reviewed,
    }


@router.post("/sync-now")
def sync_now(_: User = Depends(require_admin)):
    """Полная выгрузка ВСЕХ Review из БД в Google Sheets + чистка стилых 'None'.

    Используется кнопкой "Выгрузить всё в Google Sheets" в админке.
    Игнорирует флаг synced_to_sheets — пишет всё, даже уже выгруженное.
    """
    return do_full_export()


@router.get("/distribution/{sheet}")
def get_distribution(
    sheet: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Возвращает текущее распределение: сколько строк у каждого координатора."""
    rows = (
        db.query(Assignment.reviewer_id, User.name)
        .join(User, Assignment.reviewer_id == User.id)
        .filter(Assignment.sheet == sheet)
        .all()
    )
    counts: Dict[str, int] = defaultdict(int)
    for _, name in rows:
        counts[name] += 1
    return {
        "total": len(rows),
        "distribution": dict(sorted(counts.items(), key=lambda x: -x[1])),
    }
