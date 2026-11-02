import random
import re
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Place


def unique_phone() -> str:
    return "+79" + "".join(str(random.randint(0, 9)) for _ in range(9))


def unique_email() -> str:
    return f"number{random.randint(1_000_000, 9_999_999)}@example.com"


def make_user():
    client = TestClient(app)
    response = client.post(
        "/web/register",
        data={
            "surname": "Номеров",
            "phone": unique_phone(),
            "email": unique_email(),
            "password": "Strong12!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.post("/web/api-keys")
    assert page.status_code == 200
    match = re.search(r"bk_[A-Za-z0-9_\-]+", page.text)
    assert match
    return client, match.group(0)


def make_place(capacity: int = 4) -> Place:
    db = SessionLocal()
    try:
        place = Place(
            capacity=capacity,
            address=f"ул. Номерная, {random.randint(1, 99)}",
            isActive=True,
            image_filename=None,
        )
        db.add(place)
        db.commit()
        db.refresh(place)
        return place
    finally:
        db.close()


def api_booking(client, key, place_id, offset, nights):
    check_in = date.today() + timedelta(days=offset)
    check_out = check_in + timedelta(days=nights)
    return client.post(
        "/api/bookings",
        headers={"X-API-Key": key},
        json={
            "place_id": place_id,
            "checkIn": check_in.isoformat(),
            "checkOut": check_out.isoformat(),
            "guestsCount": 1,
        },
    )


def test_booking_numbers_start_from_one_per_user_and_max_seven_days():
    client_a, key_a = make_user()
    client_b, key_b = make_user()
    place = make_place()

    first = api_booking(client_a, key_a, place.id, 10, 2)
    assert first.status_code == 201
    assert first.json()["booking_number"] == 1

    second = api_booking(client_a, key_a, place.id, 20, 2)
    assert second.status_code == 201
    assert second.json()["booking_number"] == 2

    other = api_booking(client_b, key_b, place.id, 30, 2)
    assert other.status_code == 201
    assert other.json()["booking_number"] == 1

    detail = client_a.get(f"/bookings/{second.json()['id']}")
    assert detail.status_code == 200
    assert "Бронь №2" in detail.text

    too_long = api_booking(client_a, key_a, place.id, 40, 8)
    assert too_long.status_code == 400
    assert "7" in too_long.json()["detail"]

    seven_days = api_booking(client_a, key_a, place.id, 50, 7)
    assert seven_days.status_code == 201
    assert seven_days.json()["booking_number"] == 3

    web_too_long = client_a.post(
        "/web/bookings",
        data={
            "place_id": str(place.id),
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "check_out": (date.today() + timedelta(days=68)).isoformat(),
            "guests": "1",
        },
        follow_redirects=False,
    )
    assert web_too_long.status_code == 400
    assert "Максимальный срок бронирования" in web_too_long.text
