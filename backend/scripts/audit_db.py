"""Аудит БД: счётчики, целостность, аномалии.

Запуск в контейнере:
  docker compose exec backend python -m scripts.audit_db

Только чтение — ничего не меняет.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
from app.models import (
    Availability, InterviewAssignment, Review, Role,
    SheetRow, SlotCapacity, TelegramChat, User,
)

OK = "✓"
WARN = "⚠"
ERR = "✗"


def main() -> None:
    db = SessionLocal()
    issues: list[str] = []
    try:
        # ─── 1. Счётчики ────────────────────────────────────────────────
        print("=" * 60)
        print("СЧЁТЧИКИ ТАБЛИЦ")
        print("=" * 60)

        users = db.query(User).all()
        by_role = Counter(u.role.value for u in users)
        print(f"  users: {len(users)}  (admin={by_role.get('admin',0)}, "
              f"coordinator={by_role.get('coordinator',0)})")

        sheet_counts = Counter(r.sheet for r in db.query(SheetRow).all())
        for sk in ("anketa", "homework", "interview"):
            print(f"  sheet_rows[{sk}]: {sheet_counts.get(sk, 0)}")

        ias = db.query(InterviewAssignment).all()
        avails = db.query(Availability).all()
        caps = db.query(SlotCapacity).all()
        reviews = db.query(Review).all()
        chats = db.query(TelegramChat).all()
        print(f"  interview_assignments: {len(ias)}")
        print(f"  availability: {len(avails)}")
        print(f"  slot_capacities: {len(caps)}")
        print(f"  reviews: {len(reviews)}")
        print(f"  telegram_chats: {len(chats)}")

        # ─── 2. Брони ───────────────────────────────────────────────────
        print()
        print("=" * 60)
        print("БРОНИ НА СОБЕС")
        print("=" * 60)

        now = datetime.now()

        def _slot_end(a):
            try:
                return datetime.strptime(f"{a.slot_date} {a.slot_hour}:00", "%Y-%m-%d %H:%M")
            except Exception:
                return None

        booked = [a for a in ias if a.slot_date]
        future = [a for a in booked if (_slot_end(a) or now) >= now]
        past = [a for a in booked if (_slot_end(a) or now) < now]

        def _rev_stats(group):
            full = sum(1 for a in group if a.reviewer1_id and a.reviewer2_id)
            partial = sum(1 for a in group if (a.reviewer1_id or a.reviewer2_id)
                          and not (a.reviewer1_id and a.reviewer2_id))
            none_r = sum(1 for a in group if not a.reviewer1_id and not a.reviewer2_id)
            return full, partial, none_r

        print(f"  Всего записано: {len(booked)}  "
              f"(прошло: {len(past)}, предстоит: {len(future)})")
        print()
        f_full, f_part, f_none = _rev_stats(future)
        print(f"  ПРЕДСТОЯЩИЕ ({len(future)}):")
        print(f"    Оба проверяющих: {f_full}")
        print(f"    Один проверяющий: {f_part}")
        print(f"    Без проверяющих: {f_none}")
        if f_part or f_none:
            print(f"    → требуют внимания: {f_part + f_none}")
        p_full, p_part, p_none = _rev_stats(past)
        print(f"  Прошедшие ({len(past)}): оба={p_full}, один={p_part}, без={p_none}")

        by_date = Counter(a.slot_date for a in booked)
        print("  По датам (все):")
        for d in sorted(by_date):
            print(f"    {d}: {by_date[d]}")

        cancelled = [a for a in ias if (a.cancel_count or 0) > 0]
        rebooked = [a for a in ias if (a.rebook_count or 0) > 0]
        print(f"  Отменяли запись: {len(cancelled)}")
        print(f"  Переносили запись: {len(rebooked)}")

        # ─── 3. Проверки целостности ────────────────────────────────────
        print()
        print("=" * 60)
        print("ЦЕЛОСТНОСТЬ")
        print("=" * 60)

        interview_rns = {r.row_number for r in db.query(SheetRow)
                         .filter(SheetRow.sheet == "interview").all()}
        coord_ids = {u.id for u in users if u.role == Role.coordinator}
        user_ids = {u.id for u in users}

        # 3.1 InterviewAssignment без строки «Собес»
        orphans = [a for a in ias if a.row_number not in interview_rns]
        if orphans:
            issues.append(f"{ERR} {len(orphans)} InterviewAssignment без строки interview: "
                          f"row_numbers={[a.row_number for a in orphans][:10]}")
        else:
            print(f"  {OK} Все брони ссылаются на существующие строки «Собес»")

        # 3.2 Назначен не-координатор
        bad_rev = []
        for a in ias:
            for rid in (a.reviewer1_id, a.reviewer2_id):
                if rid and rid not in coord_ids:
                    bad_rev.append((a.row_number, rid))
        if bad_rev:
            issues.append(f"{ERR} Назначены не-координаторы (или удалённые user): {bad_rev[:10]}")
        else:
            print(f"  {OK} Все проверяющие — действующие координаторы")

        # 3.3 reviewer1 == reviewer2
        same_rev = [a.row_number for a in ias
                    if a.reviewer1_id and a.reviewer1_id == a.reviewer2_id]
        if same_rev:
            issues.append(f"{ERR} Один человек назначен дважды на собес: rows={same_rev}")
        else:
            print(f"  {OK} Нет собесов где один проверяющий стоит дважды")

        # 3.4 Битые slot_date/slot_hour
        for a in booked:
            if _slot_end(a) is None:
                issues.append(f"{ERR} Бронь #{a.row_number}: некорректные slot_date/slot_hour "
                               f"({a.slot_date!r}/{a.slot_hour!r})")
        print(f"  {OK} Прошедших собесов: {len(past)} (история, назначать там нечего)")

        # 3.5 Один проверяющий на 2 собеса в один час — только БУДУЩИЕ
        slot_revs: dict[tuple, list] = defaultdict(list)
        for a in future:
            key = (a.slot_date, a.slot_hour)
            for rid in (a.reviewer1_id, a.reviewer2_id):
                if rid:
                    slot_revs[key].append((rid, a.row_number))
        conflicts = []
        for key, items in slot_revs.items():
            seen = Counter(rid for rid, _ in items)
            for rid, cnt in seen.items():
                if cnt > 1:
                    conflicts.append((key, rid, cnt))
        if conflicts:
            for (d, h), rid, cnt in conflicts[:10]:
                issues.append(f"{ERR} Коорд #{rid} назначен на {cnt} собеса в {d} {h}:00")
        else:
            print(f"  {OK} Нет двойных назначений координатора на один час")

        # 3.6 Availability вне периода
        ALLOWED = {f"2026-05-{d:02d}" for d in range(9, 25)}
        bad_avail = [a for a in avails if a.slot_date not in ALLOWED]
        if bad_avail:
            issues.append(f"{WARN} {len(bad_avail)} записей Availability вне 9–24 мая")
        else:
            print(f"  {OK} Вся занятость в пределах 9–24 мая")

        # 3.7 Дубли броней по студ. билету (две interview-строки на одного)
        from app.routers.admin_ops import _detect_student_id_col, _normalize_student_id
        int_rows = db.query(SheetRow).filter(SheetRow.sheet == "interview").all()
        if int_rows:
            sid_col = _detect_student_id_col(int_rows)
            if sid_col:
                booked_rns = {a.row_number for a in booked}
                sid_to_rows: dict[str, list] = defaultdict(list)
                for r in int_rows:
                    if r.row_number not in booked_rns:
                        continue
                    sid = _normalize_student_id(r.data.get(sid_col, ""))
                    if sid:
                        sid_to_rows[sid].append(r.row_number)
                dups = {s: rns for s, rns in sid_to_rows.items() if len(rns) > 1}
                if dups:
                    for sid, rns in list(dups.items())[:10]:
                        issues.append(f"{ERR} Билет {sid}: несколько активных броней rows={rns}")
                else:
                    print(f"  {OK} Нет дублей активных броней по студ. билету")

        # ─── 4. Координаторы ────────────────────────────────────────────
        print()
        print("=" * 60)
        print("КООРДИНАТОРЫ")
        print("=" * 60)

        no_fac = [u.name for u in users if u.role == Role.coordinator and not u.faculties]
        if no_fac:
            print(f"  {WARN} Без факультетов ({len(no_fac)}): {', '.join(no_fac)}")
        else:
            print(f"  {OK} У всех координаторов заданы факультеты")

        coords_with_avail = {a.user_id for a in avails}
        no_avail = [u.name for u in users
                    if u.role == Role.coordinator and u.id not in coords_with_avail]
        if no_avail:
            print(f"  {WARN} Не заполнили занятость ({len(no_avail)}): {', '.join(no_avail)}")
        else:
            print(f"  {OK} Все координаторы заполнили занятость")

        load = Counter()
        for a in booked:
            for rid in (a.reviewer1_id, a.reviewer2_id):
                if rid:
                    load[rid] += 1
        names = {u.id: u.name for u in users}
        print("  Нагрузка (собесов назначено):")
        for rid, cnt in load.most_common():
            print(f"    {names.get(rid, '#'+str(rid))}: {cnt}")

        # ─── 5. Telegram-чаты ───────────────────────────────────────────
        print()
        print("=" * 60)
        print("TELEGRAM-ЧАТЫ")
        print("=" * 60)
        if not chats:
            print(f"  {WARN} Чаты не настроены — уведомления о назначении не уйдут")
        for c in chats:
            facs = ", ".join(c.faculties or []) or "—"
            print(f"  {c.title}: [{facs}]")
        all_chat_facs = set()
        for c in chats:
            all_chat_facs.update(c.faculties or [])
        FACULTIES = {'НАБ','ФЭБ','ВШУ','ИТиАБД','СНиМК','МЭО','Финфак','Юрфак'}
        uncovered = FACULTIES - all_chat_facs
        if uncovered and chats:
            print(f"  {WARN} Факультеты без чата: {', '.join(sorted(uncovered))}")

        # ─── Итог ───────────────────────────────────────────────────────
        print()
        print("=" * 60)
        if issues:
            print(f"НАЙДЕНО ПРОБЛЕМ: {len(issues)}")
            print("=" * 60)
            for i in issues:
                print(f"  {i}")
        else:
            print(f"{OK} КРИТИЧНЫХ ПРОБЛЕМ НЕ НАЙДЕНО")
            print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
