"""Интеграционные тесты публичной записи на собес (/booking)."""

from app.models import (
    Availability,
    InterviewAssignment,
    Role,
    SheetRow,
    SlotCapacity,
    User,
)


def _coord(session, *, email, name, faculties):
    # Реальный bcrypt не нужен: booking не проверяет пароли.
    u = User(
        email=email,
        name=name,
        password_hash="unused-test-hash",
        role=Role.coordinator,
        faculties=list(faculties),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _interview_row(session, row_number: int, ticket_display: str, fio: str):
    r = SheetRow(
        sheet="interview",
        row_number=row_number,
        data={
            "_row": row_number,
            "Номер студенческого билета": ticket_display,
            "ФИО": fio,
        },
    )
    session.add(r)
    session.commit()


def _anketa_row(session, row_number: int, ticket: str, faculty: str):
    r = SheetRow(
        sheet="anketa",
        row_number=row_number,
        data={
            "_row": row_number,
            "Номер студенческого билета": ticket,
            "Факультет": faculty,
        },
    )
    session.add(r)
    session.commit()


SLOT_DATE = "2026-05-15"
SLOT_HOUR = 10


class TestLookup:
    def test_rejects_ticket_without_digits(self, client):
        r = client.get("/booking/lookup", params={"student_id": "абв"})
        assert r.status_code == 400

    def test_not_found_without_anketa_rows(self, client):
        r = client.get("/booking/lookup", params={"student_id": "2112345"})
        assert r.status_code == 404

    def test_success_fio_and_faculty_from_anketa_only(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")
        # дополнительно явное ФИО в анкете
        r = db_session.query(SheetRow).filter_by(sheet="anketa", row_number=2).one()
        r.data = {**r.data, "ФИО": "Иванов Иван"}
        db_session.commit()

        res = client.get("/booking/lookup", params={"student_id": "21/12345"})
        assert res.status_code == 200
        body = res.json()
        assert body["row_number"] == 2
        assert body["fio"] == "Иванов Иван"
        assert body["faculty"] == "НАБ"
        assert body["already_booked"] is None

    def test_already_booked_block(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")
        _interview_row(db_session, 10, "2112345", "Петров П.")
        c1 = _coord(db_session, email="a@test.ru", name="Рецензент А", faculties=["НАБ"])
        c2 = _coord(db_session, email="b@test.ru", name="Рецензент Б", faculties=["НАБ"])
        db_session.add(
            InterviewAssignment(
                row_number=10,
                reviewer1_id=c1.id,
                reviewer2_id=c2.id,
                slot_date=SLOT_DATE,
                slot_hour=SLOT_HOUR,
            )
        )
        db_session.commit()

        r = client.get("/booking/lookup", params={"student_id": "2112345"})
        assert r.status_code == 200
        ab = r.json()["already_booked"]
        assert ab["slot_date"] == SLOT_DATE
        assert ab["slot_hour"] == SLOT_HOUR
        assert ab["reviewer1"] == "Рецензент А"
        assert ab["reviewer2"] == "Рецензент Б"


class TestSlots:
    def test_empty_when_no_capacity(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")

        r = client.get("/booking/slots", params={"student_id": "2112345"})
        assert r.status_code == 200
        assert r.json()["dates"] == []

    def test_recommended_when_two_coords_same_faculty_free(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")
        c1 = _coord(db_session, email="n1@test.ru", name="Наб1", faculties=["НАБ"])
        c2 = _coord(db_session, email="n2@test.ru", name="Наб2", faculties=["НАБ"])
        db_session.add(SlotCapacity(slot_date=SLOT_DATE, slot_hour=SLOT_HOUR, capacity=3))
        db_session.add(Availability(user_id=c1.id, slot_date=SLOT_DATE, slot_hour=SLOT_HOUR))
        db_session.add(Availability(user_id=c2.id, slot_date=SLOT_DATE, slot_hour=SLOT_HOUR))
        db_session.commit()

        r = client.get("/booking/slots", params={"student_id": "2112345"})
        assert r.status_code == 200
        data = r.json()
        assert data["candidate_faculty"] == "НАБ"
        assert len(data["dates"]) >= 1
        day = next(d for d in data["dates"] if d["date"] == SLOT_DATE)
        slot = next(s for s in day["slots"] if s["hour"] == SLOT_HOUR)
        assert slot["type"] == "recommended"

    def test_other_when_only_foreign_faculty_coords_free(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")
        c1 = _coord(db_session, email="f1@test.ru", name="Фэб1", faculties=["ФЭБ"])
        c2 = _coord(db_session, email="f2@test.ru", name="Фэб2", faculties=["ФЭБ"])
        db_session.add(SlotCapacity(slot_date=SLOT_DATE, slot_hour=SLOT_HOUR, capacity=3))
        db_session.add(Availability(user_id=c1.id, slot_date=SLOT_DATE, slot_hour=SLOT_HOUR))
        db_session.add(Availability(user_id=c2.id, slot_date=SLOT_DATE, slot_hour=SLOT_HOUR))
        db_session.commit()

        r = client.get("/booking/slots", params={"student_id": "2112345"})
        assert r.status_code == 200
        data = r.json()
        assert data["candidate_faculty"] == "НАБ"
        day = next(d for d in data["dates"] if d["date"] == SLOT_DATE)
        slot = next(s for s in day["slots"] if s["hour"] == SLOT_HOUR)
        assert slot["type"] == "other"


class TestBook:
    def test_success_assigns_two_reviewers_prefers_same_faculty(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")
        nab1 = _coord(db_session, email="n1@test.ru", name="Наб1", faculties=["НАБ"])
        nab2 = _coord(db_session, email="n2@test.ru", name="Наб2", faculties=["НАБ"])
        _coord(db_session, email="f1@test.ru", name="Фэб1", faculties=["ФЭБ"])
        db_session.add(SlotCapacity(slot_date=SLOT_DATE, slot_hour=SLOT_HOUR, capacity=3))
        for uid in (nab1.id, nab2.id):
            db_session.add(Availability(user_id=uid, slot_date=SLOT_DATE, slot_hour=SLOT_HOUR))
        db_session.commit()

        r = client.post(
            "/booking/book",
            json={"student_id": "2112345", "slot_date": SLOT_DATE, "slot_hour": SLOT_HOUR},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert set([body["reviewer1"], body["reviewer2"]]) == {"Наб1", "Наб2"}

        ia = db_session.query(InterviewAssignment).one()
        assert ia.row_number == 10001
        assert ia.slot_date == SLOT_DATE
        assert ia.slot_hour == SLOT_HOUR
        assert ia.reviewer1_id in (nab1.id, nab2.id)
        assert ia.reviewer2_id in (nab1.id, nab2.id)

    def test_conflict_when_already_booked(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")
        _interview_row(db_session, 10, "2112345", "Иванов")
        c1 = _coord(db_session, email="a@test.ru", name="A", faculties=["НАБ"])
        c2 = _coord(db_session, email="b@test.ru", name="B", faculties=["НАБ"])
        db_session.add(
            InterviewAssignment(
                row_number=10,
                reviewer1_id=c1.id,
                reviewer2_id=c2.id,
                slot_date=SLOT_DATE,
                slot_hour=SLOT_HOUR,
            )
        )
        db_session.commit()

        r = client.post(
            "/booking/book",
            json={"student_id": "2112345", "slot_date": SLOT_DATE, "slot_hour": SLOT_HOUR},
        )
        assert r.status_code == 409

    def test_rejects_unknown_slot_capacity(self, db_session, client):
        _anketa_row(db_session, 2, "2112345", "НАБ")
        _coord(db_session, email="a@test.ru", name="A", faculties=["НАБ"])
        _coord(db_session, email="b@test.ru", name="B", faculties=["НАБ"])
        db_session.commit()

        r = client.post(
            "/booking/book",
            json={"student_id": "2112345", "slot_date": SLOT_DATE, "slot_hour": SLOT_HOUR},
        )
        assert r.status_code == 400

    def test_capacity_exhausted_returns_409(self, db_session, client):
        _anketa_row(db_session, 1, "1111111", "НАБ")
        _anketa_row(db_session, 2, "2222222", "НАБ")
        c1 = _coord(db_session, email="c1@test.ru", name="C1", faculties=["НАБ"])
        c2 = _coord(db_session, email="c2@test.ru", name="C2", faculties=["НАБ"])
        db_session.add(SlotCapacity(slot_date=SLOT_DATE, slot_hour=SLOT_HOUR, capacity=1))
        for uid in (c1.id, c2.id):
            db_session.add(Availability(user_id=uid, slot_date=SLOT_DATE, slot_hour=SLOT_HOUR))
        db_session.commit()

        first = client.post(
            "/booking/book",
            json={"student_id": "1111111", "slot_date": SLOT_DATE, "slot_hour": SLOT_HOUR},
        )
        assert first.status_code == 200

        second = client.post(
            "/booking/book",
            json={"student_id": "2222222", "slot_date": SLOT_DATE, "slot_hour": SLOT_HOUR},
        )
        assert second.status_code == 409
