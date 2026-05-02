import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import engine, Base
from app.models import User, Role, Review
from app.routers import auth, users, sheets, reviews, admin_ops


SEED_USERS = [
    # (email, name, password, role)
    ("admin@koord.ru", "Администратор", "admin123", Role.admin),
    ("ekaterina.basova@koord.ru",        "Басова Екатерина",        "Koord2026", Role.coordinator),
    ("alina.bedretdinova@koord.ru",      "Бедретдинова Алина",      "Koord2026", Role.coordinator),
    ("sofya.bedretdinova@koord.ru",      "Бедретдинова Софья",      "Koord2026", Role.coordinator),
    ("oleg.velichko@koord.ru",           "Величко Олег",            "Koord2026", Role.coordinator),
    ("darya.deriglazova@koord.ru",       "Дериглазова Дарья",       "Koord2026", Role.coordinator),
    ("polina.dziarskaya@koord.ru",       "Дзярская Полина",         "Koord2026", Role.coordinator),
    ("amil.iskenderov@koord.ru",         "Искендеров Амиль",        "Koord2026", Role.coordinator),
    ("polina.kalmykova@koord.ru",        "Калмыкова Полина",        "Koord2026", Role.coordinator),
    ("ilya.kirilyuk@koord.ru",           "Кирилюк Илья",            "Koord2026", Role.coordinator),
    ("amulanga.kitaeva@koord.ru",        "Китаева Амуланга",        "Koord2026", Role.coordinator),
    ("georgiy.kovalev@koord.ru",         "Ковалев Георгий",         "Koord2026", Role.coordinator),
    ("eva.koptelova@koord.ru",           "Коптелова Ева",           "Koord2026", Role.coordinator),
    ("elizaveta.kushnir@koord.ru",       "Кушнир Елизавета",        "Koord2026", Role.coordinator),
    ("yuliya.larina@koord.ru",           "Ларина Юлия",             "Koord2026", Role.coordinator),
    ("alisa.levina@koord.ru",            "Левина Алиса",            "Koord2026", Role.coordinator),
    ("marianna.margaryan@koord.ru",      "Маргарян Марианна",       "Koord2026", Role.coordinator),
    ("polina.mitrofanova@koord.ru",      "Митрофанова Полина",      "Koord2026", Role.coordinator),
    ("darya.pavlova@koord.ru",           "Павлова Дарья",           "Koord2026", Role.coordinator),
    ("valeriya.paliy@koord.ru",          "Палий Валерия",           "Koord2026", Role.coordinator),
    ("anastasiya.pivovarova@koord.ru",   "Пивоварова Анастасия",    "Koord2026", Role.coordinator),
    ("veronika.pogrebnyak@koord.ru",     "Погребняк Вероника",      "Koord2026", Role.coordinator),
    ("dana.sagatova@koord.ru",           "Сагатова Дана",           "Koord2026", Role.coordinator),
    ("kira.sysoeva@koord.ru",            "Сысоева Кира",            "Koord2026", Role.coordinator),
    ("arina.shityagina@koord.ru",        "Шитягина Арина",          "Koord2026", Role.coordinator),
    ("alina.shishkova@koord.ru",         "Шишкова Алина",           "Koord2026", Role.coordinator),
    ("anastasiya.shonya@koord.ru",       "Шоня Анастасия",          "Koord2026", Role.coordinator),
]


# ---------------------------------------------------------------------------
# Background sync: SQLite reviews → Google Sheets (every 3 min)
# ---------------------------------------------------------------------------

def _do_sync():
    """Sync SQLite reviews → Google Sheets с оптимистичной блокировкой по saved_at.

    Ключевая инвариантa: помечаем synced=True ТОЛЬКО для тех записей, у которых
    saved_at не изменился между чтением и записью в sheets. Если координатор
    успел сохранить заново во время отправки, его новые данные останутся
    synced=False и попадут в следующий цикл.
    """
    from app.sheets import GoogleSheetsEngine
    from collections import defaultdict

    db = Session(engine)
    try:
        # Снимок: id + содержимое + saved_at на момент чтения
        unsynced = (
            db.query(Review.id, Review.sheet, Review.row_number, Review.scores, Review.saved_at)
            .filter(Review.synced_to_sheets.is_(False))
            .all()
        )
        if not unsynced:
            return

        try:
            gs = GoogleSheetsEngine()
        except Exception as exc:
            print(f"[sync] Google Sheets недоступен: {exc}")
            return

        by_sheet = defaultdict(list)
        for r in unsynced:
            # (row_number, scores, id, snapshot_saved_at)
            by_sheet[r.sheet].append((r.row_number, r.scores, r.id, r.saved_at))

        for sheet_key, items in by_sheet.items():
            try:
                updates = [(row_num, scores) for row_num, scores, _, _ in items]
                gs.batch_update_reviews(sheet_key, updates)

                # Per-row UPDATE с проверкой saved_at — если запись изменилась после
                # снимка, condition не сработает и synced останется False.
                marked = 0
                for _, _, review_id, snapshot in items:
                    rows_updated = (
                        db.query(Review)
                        .filter(Review.id == review_id, Review.saved_at == snapshot)
                        .update({"synced_to_sheets": True}, synchronize_session=False)
                    )
                    marked += rows_updated
                db.commit()
                skipped = len(items) - marked
                msg = f"[sync] {sheet_key}: записано {len(items)}, помечено synced {marked}"
                if skipped:
                    msg += f" (пропущено {skipped} — изменены после снимка, попадут в след. цикл)"
                print(msg)
            except Exception as exc:
                print(f"[sync] Ошибка для листа {sheet_key}: {exc}")
                db.rollback()
    finally:
        db.close()


def _sync_loop():
    while True:
        time.sleep(180)  # 3 минуты
        try:
            _do_sync()
        except Exception as exc:
            print(f"[sync] Неожиданная ошибка: {exc}")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_db()
    _seed_users()
    threading.Thread(target=_sync_loop, daemon=True, name="sheets-sync").start()
    yield


def _migrate_db():
    with engine.connect() as conn:
        cols = [c["name"] for c in inspect(engine).get_columns("users")]
        if "faculties" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN faculties JSON DEFAULT '[]'"))
            conn.commit()


def _seed_users():
    db = Session(engine)
    try:
        for email, name, password, role in SEED_USERS:
            if not db.query(User).filter(User.email == email).first():
                db.add(User(
                    email=email,
                    name=name,
                    role=role,
                    password_hash=hash_password(password),
                ))
        db.commit()
    finally:
        db.close()


app = FastAPI(title="Koordinatorstvo HR API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sheets.router)
app.include_router(reviews.router)
app.include_router(admin_ops.router)


@app.get("/health")
def health():
    return {"status": "ok"}
