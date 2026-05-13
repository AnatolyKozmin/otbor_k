"""Скрипт разметки листа «Собес» в основной таблице.

Для каждого кандидата, сдавшего домашку, создаёт вертикальный блок:
  • 3 строки шапки: «Кандидат», ФИО, билет / проверяющие 1+2
  • Сценарий собеса по структуре INTERVIEW_FORM (как в существующем шаблоне «Собес»):
      col A — название секции, col B — текст вопроса/скрипта
      col C — место для ответа от проверяющего 1
      col D — место для ответа от проверяющего 2
  • Блок «Оценка компетенций» в конце: критерии по строкам, баллы по горизонтали (C / D)
  • 2 пустые строки разделитель между кандидатами

Дедупликация: если кандидат сдавал ДЗ несколько раз, берётся последняя сдача
(с максимальным row_number). Остальные сдачи перечисляются в шапке блока.

Запуск:
  cd backend
  .venv/bin/python -m scripts.build_sobes_layout --preview   # печатает первый кандидат-блок
  .venv/bin/python -m scripts.build_sobes_layout --write     # пишет в новый лист «Собес (заготовка)»

Целевая таблица:
  SPREADSHEET_ID из app/config.py (.env)
  Новый лист — «Собес (заготовка)» (создаётся, если нет; ОЧИЩАЕТСЯ перед записью)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

# Корень проекта = backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings
from app.interview_form import INTERVIEW_FORM

TARGET_SHEET_TITLE = "Собес (заготовка)"

# Критерии, как в routers/reviews.py (для итогового блока «Оценка компетенций»)
INTERVIEW_CRITERIA = [
    ("team_work",             "Работа в команде [0,1,2,3]"),
    ("efcom",                 "Эфком [0,1,2,3]"),
    ("time_mgmt",             "Тайм-менеджмент [0,1,2,3]"),
    ("project_understanding", "Понимание проекта [0,1,3]"),
    ("interest",              "Заинтересованность [0,2,3]"),
    ("awareness",             "Осознанность (текст)"),
    ("experience",            "Опыт в схожей деятельности (текст)"),
    ("leadership",            "Лидерство (текст)"),
    ("gpt_usage",             "Использование ГПТ (текст)"),
    ("comments",              "Общий комментарий (текст)"),
]


def _normalize_sid(v) -> str:
    s = str(v or "").strip()
    return "".join(ch for ch in s if ch.isdigit())


def _open_main_spreadsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_CREDENTIALS_PATH, scopes=scopes
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(settings.SPREADSHEET_ID)


def _detect_col(headers: list[str], keywords: list[str]) -> Optional[int]:
    """Возвращает индекс колонки по подстрокам (regardless of order)."""
    for i, h in enumerate(headers):
        hl = h.lower()
        if all(kw in hl for kw in keywords):
            return i
    return None


def _load_anketa_by_sid(sh) -> dict[str, dict]:
    ws = sh.worksheet("Анкеты")
    vals = ws.get_all_values()
    headers = vals[0]
    sid_i = _detect_col(headers, ["студ", "билет"])
    fio_i = _detect_col(headers, ["фио"])
    fac_i = _detect_col(headers, ["факультет"])
    if sid_i is None:
        raise RuntimeError("В «Анкеты» не нашёл колонку студ. билета")
    out = {}
    for r in vals[1:]:
        if sid_i >= len(r):
            continue
        sid = _normalize_sid(r[sid_i])
        if not sid:
            continue
        out[sid] = {
            "fio": (r[fio_i].strip() if fio_i is not None and fio_i < len(r) else ""),
            "faculty": (r[fac_i].strip() if fac_i is not None and fac_i < len(r) else ""),
        }
    return out


def _load_hw_submitters(sh) -> list[dict]:
    """Уникальные сдавшие ДЗ — берём последнюю запись каждого студента.

    Возвращает: [{sid, fio, package, link, all_submissions: [...]}]
    """
    ws = sh.worksheet("Домашка")
    vals = ws.get_all_values()
    headers = vals[0]
    sid_i  = _detect_col(headers, ["студ", "билет"])
    fio_i  = _detect_col(headers, ["фио"])
    pkg_i  = _detect_col(headers, ["пакет"])
    link_i = _detect_col(headers, ["ссылк"])
    if sid_i is None:
        raise RuntimeError("В «Домашка» не нашёл колонку студ. билета")

    # row_idx в sheet = (i + 2) [1-based, плюс шапка]
    submissions_by_sid: dict[str, list[dict]] = {}
    for i, r in enumerate(vals[1:], start=2):
        if sid_i >= len(r):
            continue
        sid = _normalize_sid(r[sid_i])
        if not sid:
            continue
        sub = {
            "row": i,
            "fio": r[fio_i].strip() if fio_i is not None and fio_i < len(r) else "",
            "package": r[pkg_i].strip() if pkg_i is not None and pkg_i < len(r) else "",
            "link": r[link_i].strip() if link_i is not None and link_i < len(r) else "",
        }
        submissions_by_sid.setdefault(sid, []).append(sub)

    result = []
    for sid, subs in submissions_by_sid.items():
        latest = max(subs, key=lambda s: s["row"])
        alt = [s for s in subs if s["row"] != latest["row"]]
        result.append({
            "sid": sid,
            "fio": latest["fio"],
            "package": latest["package"],
            "link": latest["link"],
            "all_submissions": subs,
            "alt_count": len(alt),
        })
    return result


def _build_candidate_block(candidate: dict, anketa: dict) -> list[list[str]]:
    """Один вертикальный блок для одного кандидата.

    Каждая строка = список из 4 ячеек (col A, B, C, D).
    """
    sid = candidate["sid"]
    fio = candidate["fio"] or anketa.get("fio", "")
    faculty = anketa.get("faculty", "")
    package = candidate["package"]
    link = candidate["link"]
    alt_count = candidate["alt_count"]

    rows: list[list[str]] = []

    # 1. шапка
    rows.append(["", "", "Кандидат", ""])
    fio_cell = fio + (f"  ({faculty})" if faculty else "")
    rows.append(["", "", fio_cell, sid])
    pkg_text = f"Пакет ДЗ: {package}" if package else ""
    if alt_count > 0:
        pkg_text += f"  ⚠ сдач: {alt_count + 1}"
    rows.append(["", "", "проверяющий 1", "проверяющий 2"])
    if link:
        rows.append(["", "Ссылка на ДЗ", link, pkg_text])
    elif pkg_text:
        rows.append(["", pkg_text, "", ""])

    rows.append(["", "", "", ""])  # пустая строка-разделитель шапки

    # 2. интервью-секции
    for sec_idx, sec in enumerate(INTERVIEW_FORM):
        section_name = sec["section"]
        first_section_cell_used = False
        for item in sec["items"]:
            t = item.get("type")
            text = item.get("text", "")
            if t in ("script", "label", "question", "case"):
                col_a = section_name if not first_section_cell_used else ""
                col_b = text
                rows.append([col_a, col_b, "", ""])
                first_section_cell_used = True
        # пустая строка-разделитель между секциями
        rows.append(["", "", "", ""])

    # 3. оценка компетенций
    rows.append(["Оценка компетенций", "", "балл / коммент. от 1-го", "балл / коммент. от 2-го"])
    for key, label in INTERVIEW_CRITERIA:
        rows.append(["", label, "", ""])

    # 4. два пустых разделителя между кандидатами
    rows.append(["", "", "", ""])
    rows.append(["", "", "", ""])

    return rows


def build_full_layout(sh) -> tuple[list[list[str]], int]:
    anketa_by_sid = _load_anketa_by_sid(sh)
    candidates = _load_hw_submitters(sh)
    # сортировка: сначала по ФИО анкеты, потом по билету
    candidates.sort(key=lambda c: (anketa_by_sid.get(c["sid"], {}).get("fio", "") or c["fio"] or "", c["sid"]))

    all_rows: list[list[str]] = []
    for c in candidates:
        block = _build_candidate_block(c, anketa_by_sid.get(c["sid"], {}))
        all_rows.extend(block)

    return all_rows, len(candidates)


def write_to_sheet(sh, all_rows: list[list[str]]):
    # удаляем старый «Собес (заготовка)», если есть
    try:
        old = sh.worksheet(TARGET_SHEET_TITLE)
        sh.del_worksheet(old)
    except gspread.exceptions.WorksheetNotFound:
        pass

    n_rows = len(all_rows) + 10
    new = sh.add_worksheet(title=TARGET_SHEET_TITLE, rows=n_rows, cols=6)
    # gspread пишет всю матрицу за один батч
    new.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")
    print(f"✓ Записано в лист «{TARGET_SHEET_TITLE}»: {len(all_rows)} строк")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preview", action="store_true",
                   help="распечатать первый блок (один кандидат) и общее число строк")
    g.add_argument("--write", action="store_true",
                   help=f"записать в новый лист «{TARGET_SHEET_TITLE}»")
    args = ap.parse_args()

    sh = _open_main_spreadsheet()
    print(f"Таблица: {sh.title}")
    all_rows, n_cand = build_full_layout(sh)
    print(f"Кандидатов (по уникальным студ. билетам): {n_cand}")
    print(f"Всего строк к записи: {len(all_rows)}")

    if args.preview:
        # печатаем первый блок (до второго пустого разделителя)
        print("\n=== ПРЕВЬЮ: первый кандидат ===")
        blank_run = 0
        for r in all_rows[:200]:
            print("  | ".join(f"{c[:60]!r:<62}" for c in r))
            if all(not c for c in r):
                blank_run += 1
                if blank_run >= 2:
                    break
            else:
                blank_run = 0
    else:
        write_to_sheet(sh, all_rows)


if __name__ == "__main__":
    main()
