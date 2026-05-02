"""
Перегенерирует frontend/src/data/rubric.js из листа "Матрица (итог)"
гугл-таблицы с компетенциями. Запускать, когда HR обновит формулировки.

Запуск (из корня репо):
    cd backend && python scripts/sync_rubric.py

Доступ к таблице — через тот же сервис-аккаунт, что использует бэк
(backend/credentials.json). Таблица должна быть расшарена на email из creds.
"""
import json
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

# ID таблицы с матрицей компетенций (отдельная от рабочей таблицы анкет)
RUBRIC_SHEET_ID = "1k7ePgz6uFt6tAkVEjQ_u-2uIyXu_CBGOUcpcktTJs2o"
RUBRIC_TAB = "Матрица (итог)"

# Маппинг названий компетенций → ключи формы (REVIEW_FIELDS / SCORE_CRITERIA)
LABEL_TO_KEY = {
    "Эфком": "efcom",
    "Тайм-менеджмент": "time_mgmt",
    "Публичка-клубничка": "publichka",
    "Эмоциональный интеллект + эмпатия": "emotional_intelligence",
    "Понимание проекта": "project_understanding",
    "Заинтересованность": "interest",
    "инициативность": "initiative",
    "Коммуникабельность": "communicability",
    "Девиантность (сквозная компетенция)": "deviance",
    "креативное мышление": "creative_thinking",
    "работа в команде": "team_work",
    "стрессоустойчивость": "stress_resistance",
    "критическое мышление": "critical_thinking",
}

# Сначала критерии, которые есть в форме оценки анкеты — чтобы координатор
# первым делом видел релевантное. Остальные идут следом.
FORM_ORDER = ["team_work", "efcom", "time_mgmt", "project_understanding", "interest"]
EXTRA_ORDER = [
    "publichka", "emotional_intelligence", "initiative", "communicability",
    "deviance", "creative_thinking", "stress_resistance", "critical_thinking",
]

ROOT = Path(__file__).resolve().parent.parent
CREDS_PATH = ROOT / "credentials.json"
OUT_PATH = ROOT.parent / "frontend" / "src" / "data" / "rubric.js"


def main() -> None:
    creds = Credentials.from_service_account_file(
        str(CREDS_PATH), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(RUBRIC_SHEET_ID).worksheet(RUBRIC_TAB)
    values = ws.get_all_values()

    items_by_key = {}
    for row in values[2:]:
        while len(row) < 6:
            row.append("")
        label = row[1].strip()
        if not label or label not in LABEL_TO_KEY:
            if label:
                print(f"[skip] нет маппинга для {label!r}")
            continue
        key = LABEL_TO_KEY[label]
        levels = []
        for score, raw in enumerate(row[2:6]):
            text = raw.strip()
            if text:
                levels.append({"score": score, "text": text})
        items_by_key[key] = {"key": key, "label": label, "levels": levels}

    ordered = [items_by_key[k] for k in FORM_ORDER + EXTRA_ORDER if k in items_by_key]
    missing_keys = set(items_by_key) - {*FORM_ORDER, *EXTRA_ORDER}
    if missing_keys:
        print(f"[warn] эти ключи не указаны в порядке вывода: {missing_keys}")

    js_lines = [
        "// Рубрика для подсказки координатору при оценивании.",
        f'// АВТОГЕНЕРАЦИЯ из листа "{RUBRIC_TAB}" таблицы {RUBRIC_SHEET_ID}.',
        "// Правки руками перепишутся при следующей выгрузке — меняй текст в Google-таблице",
        "// и запускай: cd backend && python scripts/sync_rubric.py",
        "//",
        "// Структура: { key, label, levels: [{ score, text }] }",
        '// Пропущенные баллы (например, "Понимание проекта" не имеет 2) отсутствуют в levels.',
        "",
        "export const RUBRIC = [",
    ]
    for r in ordered:
        js_lines.append("  {")
        js_lines.append(f"    key: {json.dumps(r['key'], ensure_ascii=False)},")
        js_lines.append(f"    label: {json.dumps(r['label'], ensure_ascii=False)},")
        js_lines.append("    levels: [")
        for lvl in r["levels"]:
            text_js = json.dumps(lvl["text"], ensure_ascii=False)
            js_lines.append(f"      {{ score: {lvl['score']}, text: {text_js} }},")
        js_lines.append("    ],")
        js_lines.append("  },")
    js_lines.append("]")
    js_lines.append("")

    OUT_PATH.write_text("\n".join(js_lines), encoding="utf-8")
    print(f"OK: записано {len(ordered)} компетенций в {OUT_PATH}")


if __name__ == "__main__":
    main()
