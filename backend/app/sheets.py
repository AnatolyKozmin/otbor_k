"""
Google Sheets engine.

Структура таблиц:
  Анкета / Домашка — строка 1: заголовки, ответы в столбцах C:AL (0-indexed 2:38)
  Собес            — строка 1: заголовки, все столбцы
"""
from pathlib import Path
from typing import Dict, List, Tuple

import gspread
import gspread.utils
from google.oauth2.service_account import Credentials

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SHEET_LABELS = {
    "anketa":    "Анкеты",
    "homework":  "Домашка",
    "interview": "Собес",
}

# Столбцы с ответами в анкете и домашке (C = 2, AL = 37 включительно)
ANSWER_START = 2
ANSWER_END   = 38  # slice-end, не включительно

# Столбцы для оценок рецензента (AN = 40-й столбец, 1-based)
REVIEW_COL_START = 40  # AN (1-based для gspread)
REVIEW_FIELDS = [
    "team_work",
    "efcom",
    "time_mgmt",
    "project_understanding",
    "interest",
    "awareness",
    "experience",
    "leadership",
    "gpt_usage",
    "questions",
    "comments",
]

SheetData = Tuple[List[str], List[Dict]]  # (headers, rows)


class GoogleSheetsEngine:
    """Базовый движок для чтения/записи данных Google Sheets."""

    def __init__(self) -> None:
        if not settings.SPREADSHEET_ID:
            raise ValueError("Не задан SPREADSHEET_ID в настройках (.env)")
        creds_path = Path(settings.GOOGLE_CREDENTIALS_PATH)
        if not creds_path.exists():
            raise FileNotFoundError(
                f"Файл credentials не найден: {creds_path.resolve()}"
            )
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        gc = gspread.authorize(creds)
        self._spreadsheet = gc.open_by_key(settings.SPREADSHEET_ID)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _raw_values(self, sheet_key: str) -> List[List[str]]:
        ws = self._spreadsheet.worksheet(SHEET_LABELS[sheet_key])
        return ws.get_all_values()

    @staticmethod
    def _pad(row: List[str], length: int) -> List[str]:
        return row + [""] * max(0, length - len(row))

    # ------------------------------------------------------------------
    # Sheet loaders
    # ------------------------------------------------------------------

    def load_questionnaire(self, sheet_key: str) -> SheetData:
        """Загружает Анкету или Домашку.

        Строка 1 — заголовки.  Столбцы A и B — мета.
        Столбцы C:AL (индексы 2–37) — ответы.
        Столбцы после AL игнорируются (там баллы).
        """
        values = self._raw_values(sheet_key)
        if not values:
            return [], []

        raw_headers = self._pad(values[0], ANSWER_END)
        headers = raw_headers[:ANSWER_START] + raw_headers[ANSWER_START:ANSWER_END]

        rows: List[Dict] = []
        for row_num, raw_row in enumerate(values[1:], start=2):
            row = self._pad(raw_row, ANSWER_END)
            data = {h: row[i] for i, h in enumerate(headers) if h}
            data["_row"] = row_num
            if all(v == "" for k, v in data.items() if not k.startswith("_")):
                continue
            rows.append(data)

        return headers, rows

    def load_interview(self) -> SheetData:
        """Загружает Собес. Строка 1 — заголовки, все столбцы."""
        values = self._raw_values("interview")
        if not values:
            return [], []

        headers = values[0]
        rows: List[Dict] = []
        for row_num, raw_row in enumerate(values[1:], start=2):
            row = self._pad(raw_row, len(headers))
            data = {h: row[i] for i, h in enumerate(headers) if h}
            data["_row"] = row_num
            if all(v == "" for k, v in data.items() if not k.startswith("_")):
                continue
            rows.append(data)

        return headers, rows

    def load_sheet(self, sheet_key: str) -> SheetData:
        if sheet_key in ("anketa", "homework"):
            return self.load_questionnaire(sheet_key)
        if sheet_key == "interview":
            return self.load_interview()
        raise ValueError(f"Неизвестный ключ листа: {sheet_key!r}")

    def load_all(self) -> Dict[str, SheetData]:
        return {key: self.load_sheet(key) for key in SHEET_LABELS}

    # ------------------------------------------------------------------
    # Review writers
    # ------------------------------------------------------------------

    def update_review_scores(
        self, sheet_key: str, row_number: int, scores: Dict
    ) -> None:
        """Записывает оценки в Google Sheets (колонки AN→AV для данной строки)."""
        ws = self._spreadsheet.worksheet(SHEET_LABELS[sheet_key])
        values = [[str(scores.get(f, "")) for f in REVIEW_FIELDS]]
        start_a1 = gspread.utils.rowcol_to_a1(row_number, REVIEW_COL_START)
        ws.update(values, start_a1)

    def batch_update_reviews(
        self, sheet_key: str, updates: List[Tuple[int, Dict]]
    ) -> None:
        """Пакетная запись оценок: updates = [(row_number, scores), ...]."""
        if not updates:
            return
        ws = self._spreadsheet.worksheet(SHEET_LABELS[sheet_key])
        batch = []
        for row_number, scores in updates:
            start_a1 = gspread.utils.rowcol_to_a1(row_number, REVIEW_COL_START)
            end_a1 = gspread.utils.rowcol_to_a1(
                row_number, REVIEW_COL_START + len(REVIEW_FIELDS) - 1
            )
            batch.append({
                "range": f"{start_a1}:{end_a1}",
                "values": [[str(scores.get(f, "")) for f in REVIEW_FIELDS]],
            })
        ws.batch_update(batch)
