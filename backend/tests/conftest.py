"""Тестовое приложение только с роутером booking — без lifespan main.py (потоки, seed)."""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.routers.booking import router as booking_router


@pytest.fixture(autouse=True)
def _freeze_booking_time(monkeypatch):
    """Фиксируем «сегодня», чтобы слоты с датами из мая 2026 не отфильтровались как прошедшие."""
    fixed = datetime(2026, 5, 11, 12, 0, 0)

    class _Dt:
        @staticmethod
        def now():
            return fixed

        @staticmethod
        def utcnow():
            return fixed

    monkeypatch.setattr("app.routers.booking.datetime", _Dt)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db_session(engine):
    SessionTesting = sessionmaker(bind=engine)
    s = SessionTesting()
    yield s
    s.close()


@pytest.fixture
def client(engine):
    SessionTesting = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(booking_router)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
