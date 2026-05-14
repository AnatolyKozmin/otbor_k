import asyncio
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.database import engine, Base
from app.models import User, Role, TelegramChat, InterviewAssignment  # noqa: F401
from app.routers import auth, users, sheets, reviews, admin_ops, availability, telegram, interview, booking
from app.sync import do_sync


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

def _sync_loop():
    while True:
        time.sleep(180)  # 3 минуты
        try:
            do_sync()
        except Exception as exc:
            print(f"[sync] Неожиданная ошибка: {exc}")


def _homework_loop():
    """Каждые 5 минут: подгружаем новые домашки и автоматически распределяем."""
    from app.routers.admin_ops import sync_homework_and_distribute

    while True:
        time.sleep(300)  # 5 минут
        db = Session(engine)
        try:
            result = sync_homework_and_distribute(db)
            if result.get("loaded_new") or result.get("distributed"):
                print(
                    f"[homework] загружено новых: {result['loaded_new']}, "
                    f"распределено: {result['distributed']}, "
                    f"потеряно (no_id/no_anketa/no_coord): "
                    f"{result['lost_no_id']}/{result['lost_no_anketa']}/{result['lost_no_coord']}"
                )
            for err in result.get("errors", []):
                print(f"[homework] error: {err}")
        except Exception as exc:
            print(f"[homework] Неожиданная ошибка: {exc}")
        finally:
            db.close()


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_db()
    _seed_users()
    threading.Thread(target=_sync_loop, daemon=True, name="sheets-sync").start()
    threading.Thread(target=_homework_loop, daemon=True, name="homework-sync").start()
    bot_task = None
    if settings.TELEGRAM_BOT_TOKEN:
        from app.routers.telegram import start_bot_polling
        bot_task = asyncio.create_task(start_bot_polling())
    yield
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass


def _migrate_db():
    with engine.connect() as conn:
        cols = [c["name"] for c in inspect(engine).get_columns("users")]
        if "faculties" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN faculties JSON DEFAULT '[]'"))
            conn.commit()

        ia_cols = [c["name"] for c in inspect(engine).get_columns("interview_assignments")]
        if "slot_date" not in ia_cols:
            conn.execute(text("ALTER TABLE interview_assignments ADD COLUMN slot_date VARCHAR"))
        if "slot_hour" not in ia_cols:
            conn.execute(text("ALTER TABLE interview_assignments ADD COLUMN slot_hour INTEGER"))
        if "booked_at" not in ia_cols:
            conn.execute(text("ALTER TABLE interview_assignments ADD COLUMN booked_at DATETIME"))
        if "cancel_count" not in ia_cols:
            conn.execute(text("ALTER TABLE interview_assignments ADD COLUMN cancel_count INTEGER NOT NULL DEFAULT 0"))
        if "rebook_count" not in ia_cols:
            conn.execute(text("ALTER TABLE interview_assignments ADD COLUMN rebook_count INTEGER NOT NULL DEFAULT 0"))
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
app.include_router(availability.router)
app.include_router(telegram.router)
app.include_router(interview.router)
app.include_router(booking.router)


@app.get("/health")
def health():
    return {"status": "ok"}
