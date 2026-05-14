"""
Telegram-интеграция: управление чатами и отправка карточек «Легендарные кандидаты».

Карточка генерируется через Pillow (800×480, фон #441766, белый текст),
отправляется через aiogram Bot.send_photo.

Polling: при старте приложения запускается aiogram-поллинг (asyncio task).
  - /chatid в любом чате → бот отвечает chat_id и названием
  - my_chat_member update → бот автоматически сохраняет новый чат в БД
"""
import io
import math
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import get_db, engine
from app.models import SheetRow, TelegramChat, User

router = APIRouter(prefix="/telegram", tags=["telegram"])

FACULTY_NAMES = {"НАБ", "ФЭБ", "ВШУ", "ИТиАБД", "СНиМК", "МЭО", "Финфак", "Юрфак"}

# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class ChatIn(BaseModel):
    chat_id: str
    title: str
    faculties: List[str] = []


class SharePayload(BaseModel):
    sheet: str
    row_number: int
    question_label: str
    answer: str


# ─── Admin: chat management ───────────────────────────────────────────────────

@router.get("/chats")
def list_chats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    chats = db.query(TelegramChat).order_by(TelegramChat.title).all()
    return [
        {"id": c.id, "chat_id": c.chat_id, "title": c.title, "faculties": c.faculties}
        for c in chats
    ]


@router.post("/chats")
def upsert_chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    existing = (
        db.query(TelegramChat)
        .filter(TelegramChat.chat_id == payload.chat_id)
        .first()
    )
    if existing:
        existing.title = payload.title
        existing.faculties = payload.faculties
    else:
        db.add(TelegramChat(
            chat_id=payload.chat_id,
            title=payload.title,
            faculties=payload.faculties,
        ))
    db.commit()
    return {"ok": True}


@router.delete("/chats/{chat_db_id}")
def delete_chat(
    chat_db_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    db.query(TelegramChat).filter(TelegramChat.id == chat_db_id).delete()
    db.commit()
    return {"ok": True}


# ─── Share ────────────────────────────────────────────────────────────────────

@router.post("/share")
async def share_answer(
    payload: SharePayload,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(400, "Telegram бот не настроен (BOT_TOKEN не задан в .env)")

    row = (
        db.query(SheetRow)
        .filter(SheetRow.sheet == payload.sheet, SheetRow.row_number == payload.row_number)
        .first()
    )
    if not row:
        raise HTTPException(404, "Строка не найдена")

    faculty = _detect_faculty(row.data)

    chats = db.query(TelegramChat).all()
    target = next(
        (c for c in chats if faculty and faculty in (c.faculties or [])),
        None,
    )
    if not target:
        label = f"«{faculty}»" if faculty else "неизвестного факультета"
        raise HTTPException(
            404,
            f"Чат для {label} не настроен — добавьте его в Настройках.",
        )

    img_bytes = _generate_card(payload.question_label, payload.answer)
    await _send_photo(target.chat_id, img_bytes)
    return {"ok": True, "chat": target.title}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _detect_faculty(data: dict) -> str:
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if str(value).strip() in FACULTY_NAMES:
            return str(value).strip()
    return ""


async def _send_text(chat_id: str, text: str) -> None:
    from aiogram import Bot

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        print(f"[tg] Ошибка отправки текста в {chat_id}: {exc}")
    finally:
        await bot.session.close()


async def notify_interview_assigned(
    db: "Session",
    faculty: str,
    fio: str,
    slot_date: str,
    slot_hour: int,
    reviewer1: str,
    reviewer2: str,
) -> None:
    """Отправляет короткое уведомление в чат факультета о назначении на собес."""
    if not settings.TELEGRAM_BOT_TOKEN or not faculty:
        return

    chats = db.query(TelegramChat).all()
    target_chats = [c for c in chats if faculty in (c.faculties or [])]
    if not target_chats:
        return

    MONTHS = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"]
    try:
        y, m, d = slot_date.split("-")
        date_str = f"{int(d)} {MONTHS[int(m)-1]}"
    except Exception:
        date_str = slot_date

    reviewers = " + ".join(filter(None, [reviewer1, reviewer2]))
    text = (
        f"📋 <b>Собеседование назначено</b>\n"
        f"👤 {fio}\n"
        f"📅 {date_str}, {slot_hour}:00\n"
        f"✅ Проверяющие: {reviewers}"
    )

    import asyncio
    for chat in target_chats:
        try:
            asyncio.create_task(_send_text(chat.chat_id, text))
        except RuntimeError:
            # Нет event loop (sync context) — запускаем в новом
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_send_text(chat.chat_id, text))
            finally:
                loop.close()


async def _send_photo(chat_id: str, photo_bytes: bytes) -> None:
    from aiogram import Bot
    from aiogram.types import BufferedInputFile

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(photo_bytes, filename="legendary.png"),
        )
    except Exception as exc:
        raise HTTPException(502, f"Ошибка отправки в Telegram: {exc}") from exc
    finally:
        await bot.session.close()


# ─── Image generation ─────────────────────────────────────────────────────────

def _generate_card(question: str, answer: str) -> bytes:
    from PIL import Image, ImageDraw

    W, H = 900, 480
    BG = (68, 23, 102)        # #441766
    ACCENT = (130, 70, 180)
    TEXT_WHITE = (255, 255, 255)
    TEXT_Q = (210, 170, 250)
    FOOTER_BG = (45, 12, 72)
    GOLD = (255, 235, 120)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    font_title = _load_font(38, bold=True)
    font_q = _load_font(18)
    font_a = _load_font(24)
    font_footer = _load_font(14)

    # Lighthouse (top-right corner)
    _draw_lighthouse(draw, 855, 44, GOLD, ACCENT)

    # Title
    draw.text((50, 24), "ЛЕГЕНДАРНЫЕ КАНДИДАТЫ", font=font_title, fill=TEXT_WHITE)

    # Divider
    draw.rectangle([50, 80, W - 50, 82], fill=ACCENT)

    # Question label (truncated to one line)
    q_label = question if len(question) <= 110 else question[:107] + "…"
    draw.text((50, 96), q_label, font=font_q, fill=TEXT_Q)

    # Answer (word-wrapped)
    lines = _wrap_text(answer, font_a, max_width=W - 120, draw=draw)
    y = 136
    for line in lines[:9]:
        draw.text((50, y), line, font=font_a, fill=TEXT_WHITE)
        y += 34
        if y > 430:
            draw.text((50, y - 34), lines[lines.index(line)] + "…", font=font_a, fill=TEXT_WHITE)
            break

    # Footer bar
    draw.rectangle([0, H - 34, W, H], fill=FOOTER_BG)
    draw.text((50, H - 24), "Координаторство'26", font=font_footer, fill=ACCENT)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_lighthouse(draw, cx: int, cy: int, gold, accent) -> None:
    """Minimal lighthouse: tower + lantern + three light rays."""
    # Tower (trapezoid)
    draw.polygon(
        [(cx - 10, cy + 65), (cx + 10, cy + 65), (cx + 6, cy + 2), (cx - 6, cy + 2)],
        fill=accent,
    )
    # Cap (triangle)
    draw.polygon([(cx - 8, cy + 2), (cx + 8, cy + 2), (cx, cy - 12)], fill=(90, 40, 115))
    # Window stripe
    draw.rectangle([cx - 5, cy + 30, cx + 5, cx + 42], fill=gold)
    # Lantern (ellipse)
    draw.ellipse([cx - 9, cy - 7, cx + 9, cy + 5], fill=gold)
    # Light rays (pointing left into the content area)
    for deg in (-22, 0, 22):
        rad = math.radians(180 + deg)
        ex = cx + int(58 * math.cos(rad))
        ey = (cy - 1) + int(58 * math.sin(rad))
        draw.line([(cx, cy - 1), (ex, ey)], fill=gold, width=2)


def _load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list:
    words = text.split()
    lines: list = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ─── Bot polling ──────────────────────────────────────────────────────────────

async def start_bot_polling() -> None:
    """Запускается как asyncio-таск при старте FastAPI (только если задан BOT_TOKEN).

    Обрабатывает два события:
      /chatid  — бот отвечает ID и названием текущего чата
      my_chat_member — когда бота добавляют в группу, сохраняет чат в БД
    """
    from aiogram import Bot, Dispatcher
    from aiogram.filters import Command
    from aiogram.types import ChatMemberUpdated, Message

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("chatid"))
    async def cmd_chatid(message: Message) -> None:
        chat = message.chat
        name = chat.title or chat.full_name or str(chat.id)
        await message.reply(
            f"Chat ID: <code>{chat.id}</code>\nНазвание: {name}",
            parse_mode="HTML",
        )

    @dp.my_chat_member()
    async def on_my_chat_member(update: ChatMemberUpdated) -> None:
        """Автоматически сохраняем чат, когда бота добавляют в группу/канал."""
        new_status = update.new_chat_member.status
        if new_status not in ("member", "administrator"):
            return
        chat = update.chat
        if chat.type not in ("group", "supergroup", "channel"):
            return
        db = Session(engine)
        try:
            existing = (
                db.query(TelegramChat)
                .filter(TelegramChat.chat_id == str(chat.id))
                .first()
            )
            if not existing:
                title = chat.title or str(chat.id)
                db.add(TelegramChat(chat_id=str(chat.id), title=title, faculties=[]))
                db.commit()
                print(f"[bot] Новый чат сохранён: {title} ({chat.id})")
            else:
                # Обновляем название если изменилось
                if chat.title and existing.title != chat.title:
                    existing.title = chat.title
                    db.commit()
        finally:
            db.close()

    print("[bot] Polling started")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "my_chat_member"])
    finally:
        await bot.session.close()
