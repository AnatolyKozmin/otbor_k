"""
Финальные результаты: баллы по всем этапам + комментарии собесов + финальный выбор.
"""
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import (
    Assignment, FinalSelection, InterviewAssignment,
    Review, SheetRow, User,
)
from app.routers.reviews import ANKETA_CRITERIA, HOMEWORK_CRITERIA

router = APIRouter(prefix="/results", tags=["results"])

# Числовые ключи по листу
_ANKETA_NUM: Set[str] = {c["key"] for c in ANKETA_CRITERIA if "options" in c}
_HW_NUM: Set[str]     = {c["key"] for c in HOMEWORK_CRITERIA if "options" in c}

# Текстовые ключи (метки) по листу
_ANKETA_TEXT:   List[dict] = [c for c in ANKETA_CRITERIA   if "options" not in c]
_HOMEWORK_TEXT: List[dict] = [c for c in HOMEWORK_CRITERIA if "options" not in c]


def _sum_numeric(scores: dict, keys: Set[str]) -> Optional[int]:
    total = 0
    found = False
    for k in keys:
        v = scores.get(k)
        if v is not None:
            try:
                total += int(v)
                found = True
            except (ValueError, TypeError):
                pass
    return total if found else None


def _text_comments(scores: dict, criteria: List[dict]) -> dict:
    """Возвращает только непустые текстовые поля из Review.scores."""
    out = {}
    for c in criteria:
        v = str(scores.get(c["key"], "") or "").strip()
        if v:
            out[c["label"]] = v
    return out


def _interview_text_notes(scores: dict) -> dict:
    """Все непустые строковые значения из заметок собеса (ключ → значение)."""
    return {k: v for k, v in scores.items() if isinstance(v, str) and v.strip()}


# ---------------------------------------------------------------------------

@router.get("/")
def get_results(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Финальные результаты всех кандидатов по этапам.

    Для каждого кандидата (строки листа «interview»):
    - ФИО и факультет (с fallback из анкеты)
    - Баллы анкеты / ДЗ / собеса + комментарии
    - Флаг «неполный» (собес запланирован, но не все сохранили заметки)
    - Статус «выбран» из таблицы final_selections
    """
    from app.routers.admin_ops import (
        _build_id_to_faculty_map,
        _build_id_to_fio_map,
        _detect_student_id_col,
        _normalize_student_id,
    )

    # ---- Загружаем всё одним проходом -----------------------------------
    interview_rows = (
        db.query(SheetRow)
        .filter(SheetRow.sheet == "interview")
        .order_by(SheetRow.row_number)
        .all()
    )
    if not interview_rows:
        return {"candidates": [], "faculties": []}

    anketa_rows = db.query(SheetRow).filter(SheetRow.sheet == "anketa").all()
    hw_rows = db.query(SheetRow).filter(SheetRow.sheet == "homework").all()

    id_to_fio = _build_id_to_fio_map(db)
    id_to_faculty = _build_id_to_faculty_map(db)

    # norm_sid → anketa row_number
    ank_sid_col = _detect_student_id_col(anketa_rows) if anketa_rows else None
    anketa_rn_by_sid: Dict[str, int] = {}
    if ank_sid_col:
        for r in anketa_rows:
            sid = _normalize_student_id(r.data.get(ank_sid_col, ""))
            if sid:
                anketa_rn_by_sid[sid] = r.row_number

    # norm_sid → latest homework row_number
    hw_sid_col = _detect_student_id_col(hw_rows) if hw_rows else None
    hw_rn_by_sid: Dict[str, int] = {}
    if hw_sid_col:
        for r in hw_rows:
            sid = _normalize_student_id(r.data.get(hw_sid_col, ""))
            if sid:
                if sid not in hw_rn_by_sid or r.row_number > hw_rn_by_sid[sid]:
                    hw_rn_by_sid[sid] = r.row_number

    # Assignments: row_number → reviewer_id
    ank_asgn: Dict[int, int] = {
        a.row_number: a.reviewer_id
        for a in db.query(Assignment).filter(Assignment.sheet == "anketa").all()
    }
    hw_asgn: Dict[int, int] = {
        a.row_number: a.reviewer_id
        for a in db.query(Assignment).filter(Assignment.sheet == "homework").all()
    }

    # InterviewAssignments: row_number → ia
    int_asgn: Dict[int, InterviewAssignment] = {
        a.row_number: a for a in db.query(InterviewAssignment).all()
    }

    # All reviews: (sheet, row_number, reviewer_id) → Review
    reviews_map: Dict[tuple, Review] = {
        (rv.sheet, rv.row_number, rv.reviewer_id): rv
        for rv in db.query(Review).all()
    }

    users_map: Dict[int, str] = {u.id: u.name for u in db.query(User).all()}

    selections: Dict[int, bool] = {
        s.row_number: s.selected
        for s in db.query(FinalSelection).all()
    }

    def _row_sid(data: dict) -> str:
        """Extract normalized student ID from a single row's data dict."""
        for col, val in data.items():
            if col.startswith("_"):
                continue
            cl = col.lower()
            if ("студ" in cl and "билет" in cl) or "билет" in cl:
                return _normalize_student_id(str(val or ""))
        return ""

    def _row_fio(data: dict) -> str:
        """Extract FIO string from a single row's data dict."""
        for col, val in data.items():
            if col.startswith("_"):
                continue
            cl = col.lower()
            if "фио" in cl or "имя" in cl or "фамилия" in cl:
                return str(val or "").strip()
        return ""

    # ---- Строим результат -----------------------------------------------
    result = []
    faculties_seen: set = set()

    for row in interview_rows:
        norm_sid = _row_sid(row.data)

        fio_raw = _row_fio(row.data)
        fio = fio_raw if (fio_raw and fio_raw != "—") else (id_to_fio.get(norm_sid, "") if norm_sid else "")
        faculty = id_to_faculty.get(norm_sid, "") if norm_sid else ""
        if faculty:
            faculties_seen.add(faculty)

        ia = int_asgn.get(row.row_number)

        # Anketa
        ank_rn = anketa_rn_by_sid.get(norm_sid) if norm_sid else None
        ank_rid = ank_asgn.get(ank_rn) if ank_rn else None
        ank_rv = reviews_map.get(("anketa", ank_rn, ank_rid)) if ank_rn and ank_rid else None
        ank_score = _sum_numeric(ank_rv.scores, _ANKETA_NUM) if ank_rv else None
        ank_comments = _text_comments(ank_rv.scores, _ANKETA_TEXT) if ank_rv else {}

        # Homework
        hw_rn = hw_rn_by_sid.get(norm_sid) if norm_sid else None
        hw_rid = hw_asgn.get(hw_rn) if hw_rn else None
        hw_rv = reviews_map.get(("homework", hw_rn, hw_rid)) if hw_rn and hw_rid else None
        hw_score = _sum_numeric(hw_rv.scores, _HW_NUM) if hw_rv else None
        hw_comments = _text_comments(hw_rv.scores, _HOMEWORK_TEXT) if hw_rv else {}

        # Interview
        r1_id = ia.reviewer1_id if ia else None
        r2_id = ia.reviewer2_id if ia else None
        r1_rv = reviews_map.get(("interview", row.row_number, r1_id)) if r1_id else None
        r2_rv = reviews_map.get(("interview", row.row_number, r2_id)) if r2_id else None
        r1_score = _sum_numeric(r1_rv.scores, _ANKETA_NUM) if r1_rv else None
        r2_score = _sum_numeric(r2_rv.scores, _ANKETA_NUM) if r2_rv else None

        # Incomplete flag
        has_slot = ia is not None and ia.slot_date is not None
        r1_saved = r1_rv is not None
        r2_saved = r2_rv is not None
        if has_slot and (r1_id or r2_id):
            if (r1_id and not r1_saved) and (r2_id and not r2_saved):
                incomplete = "both"
            elif (r1_id and not r1_saved) or (r2_id and not r2_saved):
                incomplete = "one"
            else:
                incomplete = "ok"
        elif has_slot:
            incomplete = "no_reviewers"
        else:
            incomplete = "none"  # не записан

        # Total score (сумма числовых из всех этапов)
        numeric_parts = [x for x in [ank_score, hw_score, r1_score, r2_score] if x is not None]
        total = sum(numeric_parts) if numeric_parts else None

        result.append({
            "row_number": row.row_number,
            "fio": fio,
            "faculty": faculty,
            "slot_date": ia.slot_date if ia else None,
            "slot_hour": ia.slot_hour if ia else None,
            "anketa": {
                "row_number": ank_rn,
                "score": ank_score,
                "reviewer": users_map.get(ank_rid) if ank_rid else None,
                "comments": ank_comments,
                "saved": ank_rv is not None,
            },
            "homework": {
                "row_number": hw_rn,
                "score": hw_score,
                "reviewer": users_map.get(hw_rid) if hw_rid else None,
                "comments": hw_comments,
                "saved": hw_rv is not None,
            },
            "interview": {
                "reviewer1": {
                    "id": r1_id,
                    "name": users_map.get(r1_id) if r1_id else None,
                    "score": r1_score,
                    "notes": _interview_text_notes(r1_rv.scores) if r1_rv else None,
                    "saved": r1_saved,
                } if r1_id else None,
                "reviewer2": {
                    "id": r2_id,
                    "name": users_map.get(r2_id) if r2_id else None,
                    "score": r2_score,
                    "notes": _interview_text_notes(r2_rv.scores) if r2_rv else None,
                    "saved": r2_saved,
                } if r2_id else None,
            },
            "total_score": total,
            "incomplete": incomplete,
            "selected": selections.get(row.row_number, False),
        })

    result.sort(key=lambda r: (r["faculty"] or "ЯЯЯ", r["fio"] or "ЯЯЯ"))
    return {"candidates": result, "faculties": sorted(faculties_seen)}


@router.post("/{row_number}/select")
def toggle_selection(
    row_number: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Переключает финальный статус кандидата (выбран/нет). Только для админов."""
    sel = db.query(FinalSelection).filter(FinalSelection.row_number == row_number).first()
    if sel:
        sel.selected = not sel.selected
    else:
        sel = FinalSelection(row_number=row_number, selected=True)
        db.add(sel)
    db.commit()
    return {"ok": True, "selected": sel.selected}


@router.get("/selected-summary")
def selected_summary(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Количество отобранных кандидатов по факультетам."""
    from app.routers.admin_ops import (
        _build_id_to_faculty_map,
        _detect_student_id_col,
        _normalize_student_id,
    )

    selected_rns = {
        s.row_number
        for s in db.query(FinalSelection).filter(FinalSelection.selected == True).all()  # noqa: E712
    }
    if not selected_rns:
        return {"by_faculty": {}, "total": 0}

    interview_rows = (
        db.query(SheetRow)
        .filter(SheetRow.sheet == "interview", SheetRow.row_number.in_(selected_rns))
        .all()
    )

    id_to_faculty = _build_id_to_faculty_map(db)

    by_faculty: Dict[str, int] = {}
    no_faculty = 0
    for row in interview_rows:
        norm_sid = ""
        for col, val in row.data.items():
            if col.startswith("_"):
                continue
            cl = col.lower()
            if ("студ" in cl and "билет" in cl) or "билет" in cl:
                norm_sid = _normalize_student_id(str(val or ""))
                break
        faculty = id_to_faculty.get(norm_sid, "") if norm_sid else ""
        if faculty:
            by_faculty[faculty] = by_faculty.get(faculty, 0) + 1
        else:
            no_faculty += 1

    if no_faculty:
        by_faculty["Без факультета"] = no_faculty

    return {"by_faculty": by_faculty, "total": len(interview_rows)}
