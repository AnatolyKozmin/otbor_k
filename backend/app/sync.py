"""
Синхронизация SQLite reviews → Google Sheets.

Два режима:
  - do_sync()         — инкрементальный, вызывается фоновым потоком каждые 3 мин.
                        Пушит только Review с synced_to_sheets=False.
  - do_full_export()  — полный, вызывается кнопкой "Выгрузить всё".
                        Пушит ВСЕ Review (даже уже synced) и подчищает
                        стилые "None" в колонках баллов.
"""
from collections import defaultdict
from typing import Dict

import gspread
import gspread.utils
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Review, User


def do_sync() -> Dict:
    """Один цикл синка с оптимистичной блокировкой по saved_at.

    Помечаем synced=True ТОЛЬКО для тех записей, у которых saved_at
    не изменился между чтением и записью в Sheets. Если координатор
    сохранил заново во время отправки — его новые данные останутся
    synced=False и попадут в следующий цикл.

    Возвращает структуру для отчёта в UI/логи:
        {
            "synced":   {sheet: count, ...},   # успешно записано в Sheets
            "skipped":  {sheet: count, ...},   # перезаписаны во время синка
            "errors":   [{sheet, message}, ...],
            "sheets_available": bool,          # удалось ли подключиться к Sheets
            "total_unsynced": int,             # сколько было unsynced на старте
        }
    """
    from app.sheets import GoogleSheetsEngine

    result = {
        "synced": defaultdict(int),
        "skipped": defaultdict(int),
        "errors": [],
        "sheets_available": True,
        "total_unsynced": 0,
    }

    db = Session(engine)
    try:
        unsynced = (
            db.query(Review.id, Review.sheet, Review.row_number, Review.scores, Review.saved_at, User.name)
            .join(User, Review.reviewer_id == User.id)
            .filter(Review.synced_to_sheets.is_(False))
            .all()
        )
        result["total_unsynced"] = len(unsynced)
        if not unsynced:
            return _finalize(result)

        try:
            gs = GoogleSheetsEngine()
        except Exception as exc:
            result["sheets_available"] = False
            result["errors"].append({"sheet": None, "message": f"Google Sheets недоступен: {exc}"})
            return _finalize(result)

        by_sheet = defaultdict(list)
        for r in unsynced:
            by_sheet[r.sheet].append((r.row_number, r.scores, r.id, r.saved_at, r.name))

        for sheet_key, items in by_sheet.items():
            try:
                updates = [(rn, sc, name) for rn, sc, _, _, name in items]
                gs.batch_update_reviews(sheet_key, updates)

                marked = 0
                for _, _, review_id, snapshot, _ in items:
                    rows_updated = (
                        db.query(Review)
                        .filter(Review.id == review_id, Review.saved_at == snapshot)
                        .update({"synced_to_sheets": True}, synchronize_session=False)
                    )
                    marked += rows_updated
                db.commit()
                result["synced"][sheet_key] = marked
                result["skipped"][sheet_key] = len(items) - marked
                msg = f"[sync] {sheet_key}: записано {len(items)}, помечено synced {marked}"
                if len(items) - marked:
                    msg += f" (пропущено {len(items) - marked} — изменены после снимка)"
                print(msg)
            except Exception as exc:
                db.rollback()
                result["errors"].append({"sheet": sheet_key, "message": str(exc)})
                print(f"[sync] Ошибка для листа {sheet_key}: {exc}")
    finally:
        db.close()

    return _finalize(result)


def _finalize(result: Dict) -> Dict:
    """defaultdict → обычный dict для JSON-сериализации."""
    result["synced"] = dict(result["synced"])
    result["skipped"] = dict(result["skipped"])
    return result


def do_full_export() -> Dict:
    """Полная выгрузка всех Review в Sheets + чистка стилых "None".

    В отличие от do_sync():
      1. Игнорирует флаг synced_to_sheets — пишет всё.
      2. После записи проходит по диапазону баллов на каждом листе и заменяет
         все литеральные "None" (наследие старого бага) на пустые ячейки.

    Возвращает:
        {
            "exported":     {sheet: count, ...},  # сколько Review записано
            "none_cleaned": {sheet: count, ...},  # сколько "None"-ячеек подчищено
            "errors":       [...],
            "sheets_available": bool,
            "total_reviews": int,
        }
    """
    from app.sheets import (
        GoogleSheetsEngine, REVIEW_COL_START, REVIEW_FIELDS, SHEET_LABELS,
    )

    result = {
        "exported": defaultdict(int),
        "none_cleaned": defaultdict(int),
        "errors": [],
        "sheets_available": True,
        "total_reviews": 0,
    }

    db = Session(engine)
    try:
        all_reviews = (
            db.query(Review.id, Review.sheet, Review.row_number, Review.scores, User.name)
            .join(User, Review.reviewer_id == User.id)
            .all()
        )
        result["total_reviews"] = len(all_reviews)

        try:
            gs = GoogleSheetsEngine()
        except Exception as exc:
            result["sheets_available"] = False
            result["errors"].append({"sheet": None, "message": f"Google Sheets недоступен: {exc}"})
            return _finalize_full(result)

        # 1. Выгрузка всех Review
        by_sheet = defaultdict(list)
        for r in all_reviews:
            by_sheet[r.sheet].append((r.row_number, r.scores, r.id, r.name))

        for sheet_key, items in by_sheet.items():
            try:
                updates = [(rn, sc, name) for rn, sc, _, name in items]
                gs.batch_update_reviews(sheet_key, updates)
                ids = [r[2] for r in items]
                db.query(Review).filter(Review.id.in_(ids)).update(
                    {"synced_to_sheets": True}, synchronize_session=False
                )
                db.commit()
                result["exported"][sheet_key] = len(items)
                print(f"[full-export] {sheet_key}: записано {len(items)}")
            except Exception as exc:
                db.rollback()
                result["errors"].append({"sheet": sheet_key, "message": str(exc)})
                print(f"[full-export] Ошибка для листа {sheet_key}: {exc}")

        # 2. Чистка стилых "None" в колонках баллов на всех листах
        end_col = REVIEW_COL_START + len(REVIEW_FIELDS) - 1
        start_letter = gspread.utils.rowcol_to_a1(1, REVIEW_COL_START).rstrip("0123456789")
        end_letter = gspread.utils.rowcol_to_a1(1, end_col).rstrip("0123456789")

        for sheet_key, sheet_name in SHEET_LABELS.items():
            try:
                ws = gs._spreadsheet.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                continue
            try:
                block = ws.get(f"{start_letter}1:{end_letter}")
                batch = []
                for row_idx, row in enumerate(block, start=1):
                    if row_idx == 1:
                        continue  # заголовок
                    for col_offset, cell in enumerate(row):
                        if cell == "None":
                            abs_col = REVIEW_COL_START + col_offset
                            a1 = gspread.utils.rowcol_to_a1(row_idx, abs_col)
                            batch.append({"range": a1, "values": [[""]]})
                if batch:
                    ws.batch_update(batch)
                    result["none_cleaned"][sheet_key] = len(batch)
                    print(f"[full-export] {sheet_name}: подчищено 'None' → '': {len(batch)}")
            except Exception as exc:
                result["errors"].append({"sheet": sheet_key, "message": f"чистка None: {exc}"})
                print(f"[full-export] Ошибка чистки 'None' для {sheet_name}: {exc}")
    finally:
        db.close()

    return _finalize_full(result)


def _finalize_full(result: Dict) -> Dict:
    result["exported"] = dict(result["exported"])
    result["none_cleaned"] = dict(result["none_cleaned"])
    return result
