import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, JSON, String, UniqueConstraint, Index,
)
from sqlalchemy.sql import func

from app.database import Base

SHEET_KEYS = ("anketa", "homework", "interview")


class Role(str, enum.Enum):
    admin = "admin"
    coordinator = "coordinator"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.coordinator)
    faculties = Column(JSON, nullable=False, default=list, server_default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SheetRow(Base):
    __tablename__ = "sheet_rows"

    id = Column(Integer, primary_key=True)
    sheet = Column(String, nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now())


class Assignment(Base):
    """Назначение: какой координатор проверяет какую строку какого листа."""
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True)
    sheet = Column(String, nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("sheet", "row_number", name="uq_assignment_row"),
        Index("ix_assignment_reviewer", "sheet", "reviewer_id"),
    )


class Availability(Base):
    """Занятость пользователя по часовым слотам (когда МОЖЕТ приходить).

    Хранит только слоты со значением «могу» — отсутствие записи = «не могу».
    Это компактнее и проще для перезаписи: при сохранении из UI просто
    удаляем все строки пользователя и вставляем актуальный набор.
    """
    __tablename__ = "availability"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    slot_date = Column(String, nullable=False)   # YYYY-MM-DD
    slot_hour = Column(Integer, nullable=False)  # 9..21 (час начала)

    __table_args__ = (
        UniqueConstraint("user_id", "slot_date", "slot_hour", name="uq_availability_slot"),
    )


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    sheet = Column(String, nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scores = Column(JSON, nullable=False, default=dict)
    # saved_at обновляется ВРУЧНУЮ при изменении scores в save_review.
    # БЕЗ onupdate — иначе sync ломал бы оптимистичную блокировку.
    saved_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    synced_to_sheets = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("sheet", "row_number", "reviewer_id", name="uq_review"),
    )
