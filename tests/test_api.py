import random
import re
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import crud, models
from app.database import SessionLocal
from app.main import app
from app.security import sha256_hash

KEY_RE = re.compile(r"bk_[A-Za-z0-9_\-]+")


def unique_phone() -> str:
    return "+79" + "".join(str(random.randint(0, 9)) for _ in range(9))


def unique_email() -> str:
    return f"api{random.randint(1_000_000, 9_999_999)}@example.com"


def make_user_and_key():
    client = TestClient(app)
    r = client.post(
        "/web/register",
        data={
            "surname": "Апишкин",
            "phone": unique_phone(),
            "email": unique_email(),
            "password": "Strong12!",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    home = client.post("/web/api-keys")
    assert home.status_code == 200
    match = KEY_RE.search(home.text)
    assert match, "API-ключ не найден на странице"
    return client, match.group(0)


def make_place(capacity: int = 4, active: bool = True) -> models.Place:
    db = SessionLocal()
    try:
        place = models.Place(
            capacity=capacity,
            address="Тестовая 1",
            isActive=active,
        )
        db.add(place)
        db.commit()
        db.refresh(place)
        return place
    finally:
        db.close()


def future_dates(offset: int = 10, nights: int = 2):
    start = date.today() + timedelta(days=offset)
    return start, start + timedelta(days=nights)


def booking_payload(place_id: int, offset: int = 10, nights: int = 2, guests: int = 2):
    check_in, check_out = future_dates(offset, nights)
    return {
        "place_id": place_id,
        "checkIn": check_in.isoformat(),
        "checkOut": check_out.isoformat(),
        "guestsCount": guests,
    }


def test_swagger_exposes_only_expected_api_paths():
    paths = set(app.openapi()["paths"].keys())
    assert paths == {
        "/api/places",
        "/api/places/{place_id}/availability",
        "/api/bookings",
        "/api/bookings/{booking_number}",
        "/api/bookings/{booking_number}/cancel",
    }
    schemes = app.openapi()["components"]["securitySchemes"]
    assert schemes, "Схема безопасности для API-ключа не зарегистрирована"


def test_places_list_is_public_and_has_expected_fields():
    make_place()
    make_place(active=False)
    client = TestClient(app)

    r = client.get("/api/places")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    for item in data:
        assert set(item.keys()) == {"id", "address", "isActive"}
        assert isinstance(item["address"], str) and item["address"]
        assert isinstance(item["isActive"], bool)


def test_my_bookings_requires_key_and_returns_only_own():
    client_a, key_a = make_user_and_key()
    client_b, key_b = make_user_and_key()
    place_1 = make_place()
    place_2 = make_place()

    created_a1 = client_a.post(
        "/api/bookings", json=booking_payload(place_1.id, offset=30), headers={"X-API-Key": key_a}
    )
    created_a2 = client_a.post(
        "/api/bookings", json=booking_payload(place_1.id, offset=40), headers={"X-API-Key": key_a}
    )
    created_b = client_b.post(
        "/api/bookings", json=booking_payload(place_2.id, offset=30), headers={"X-API-Key": key_b}
    )
    assert created_a1.status_code == 201
    assert created_a2.status_code == 201
    assert created_b.status_code == 201

    api = TestClient(app)
    no_key = api.get("/api/bookings")
    assert no_key.status_code == 401

    own = api.get("/api/bookings", headers={"X-API-Key": key_a})
    assert own.status_code == 200
    ids = {booking["id"] for booking in own.json()}
    assert ids == {created_a1.json()["id"], created_a2.json()["id"]}
    assert created_b.json()["id"] not in ids

    foreign = api.get("/api/bookings", headers={"X-API-Key": key_b})
    assert {booking["id"] for booking in foreign.json()} == {created_b.json()["id"]}


def test_availability_is_public():
    place = make_place()
    client = TestClient(app)
    check_in, check_out = future_dates()
    r = client.get(
        f"/api/places/{place.id}/availability",
        params={"check_in": check_in.isoformat(), "check_out": check_out.isoformat()},
    )
    assert r.status_code == 200
    assert r.json()["free"] is True


def test_availability_validation():
    place = make_place()
    client = TestClient(app)

    r = client.get(
        f"/api/places/{place.id}/availability",
        params={"check_in": "2026-01-10", "check_out": "2026-01-05"},
    )
    assert r.status_code == 400

    r = client.get(
        "/api/places/999999999/availability",
        params={"check_in": "2026-01-10", "check_out": "2026-01-12"},
    )
    assert r.status_code == 404


def test_create_booking_requires_key():
    place = make_place()
    client = TestClient(app)
    r = client.post("/api/bookings", json=booking_payload(place.id))
    assert r.status_code == 401


def test_create_booking_invalid_key():
    place = make_place()
    client = TestClient(app)
    r = client.post(
        "/api/bookings",
        json=booking_payload(place.id),
        headers={"X-API-Key": "bk_invalid"},
    )
    assert r.status_code == 401


def test_create_booking_owner_taken_from_key_not_body():
    _, key = make_user_and_key()
    place = make_place()
    client = TestClient(app)

    payload = booking_payload(place.id)
    payload["customer_id"] = 999999
    payload["status"] = "cancelled"

    r = client.post("/api/bookings", json=payload, headers={"X-API-Key": key})
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "active"
    assert "customer_id" not in data

    db = SessionLocal()
    try:
        booking = crud.get_booking(db, data["id"])
        api_key = crud.get_api_key_record_by_hash(db, sha256_hash(key))
        assert booking.customer_id == api_key.customer_id
    finally:
        db.close()


def test_api_key_is_stored_as_sha256():
    _, key = make_user_and_key()
    db = SessionLocal()
    try:
        record = crud.get_api_key_record_by_hash(db, sha256_hash(key))
        assert record is not None
        assert record.key_hash == sha256_hash(key)
        assert record.key_hash != key
        assert len(record.key_hash) == 64
        assert record.key_prefix == key[:12]
    finally:
        db.close()


def test_status_and_cancel_only_for_owner():
    _, key_a = make_user_and_key()
    _, key_b = make_user_and_key()
    place = make_place()
    client = TestClient(app)

    created = client.post(
        "/api/bookings",
        json=booking_payload(place.id),
        headers={"X-API-Key": key_a},
    )
    assert created.status_code == 201
    booking_number = created.json()["booking_number"]

    own = client.get(f"/api/bookings/{booking_number}", headers={"X-API-Key": key_a})
    assert own.status_code == 200
    assert own.json()["status"] == "active"

    # У другого пользователя нет брони с таким номером — 404, без раскрытия чужих данных
    foreign = client.get(f"/api/bookings/{booking_number}", headers={"X-API-Key": key_b})
    assert foreign.status_code == 404

    foreign_cancel = client.post(
        f"/api/bookings/{booking_number}/cancel", headers={"X-API-Key": key_b}
    )
    assert foreign_cancel.status_code == 404

    missing = client.get("/api/bookings/999999999", headers={"X-API-Key": key_a})
    assert missing.status_code == 404


def test_cancel_own_booking_and_second_cancel_conflicts():
    _, key = make_user_and_key()
    place = make_place()
    client = TestClient(app)

    created = client.post(
        "/api/bookings",
        json=booking_payload(place.id),
        headers={"X-API-Key": key},
    )
    booking_number = created.json()["booking_number"]

    cancelled = client.post(
        f"/api/bookings/{booking_number}/cancel", headers={"X-API-Key": key}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    again = client.post(
        f"/api/bookings/{booking_number}/cancel", headers={"X-API-Key": key}
    )
    assert again.status_code == 409


def test_availability_reflects_booking_and_cancel():
    _, key = make_user_and_key()
    place = make_place()
    client = TestClient(app)
    payload = booking_payload(place.id)

    params = {"check_in": payload["checkIn"], "check_out": payload["checkOut"]}
    assert client.get(
        f"/api/places/{place.id}/availability", params=params
    ).json()["free"] is True

    created = client.post("/api/bookings", json=payload, headers={"X-API-Key": key})
    assert created.status_code == 201
    assert client.get(
        f"/api/places/{place.id}/availability", params=params
    ).json()["free"] is False

    client.post(
        f"/api/bookings/{created.json()['booking_number']}/cancel",
        headers={"X-API-Key": key},
    )
    assert client.get(
        f"/api/places/{place.id}/availability", params=params
    ).json()["free"] is True


def test_booking_conflict_returns_409():
    _, key = make_user_and_key()
    place = make_place()
    client = TestClient(app)
    payload = booking_payload(place.id)

    assert client.post("/api/bookings", json=payload, headers={"X-API-Key": key}).status_code == 201
    second = client.post("/api/bookings", json=payload, headers={"X-API-Key": key})
    assert second.status_code == 409


def test_revoked_key_stops_working():
    client, key = make_user_and_key()

    db = SessionLocal()
    try:
        record = crud.get_api_key_record_by_hash(db, sha256_hash(key))
        key_id = record.id
    finally:
        db.close()

    revoke = client.post(f"/web/api-keys/{key_id}/revoke", follow_redirects=False)
    assert revoke.status_code == 303

    place = make_place()
    api = TestClient(app)
    r = api.post(
        "/api/bookings",
        json=booking_payload(place.id),
        headers={"X-API-Key": key},
    )
    assert r.status_code == 401


def test_inactive_place_cannot_be_booked():
    _, key = make_user_and_key()
    place = make_place(active=False)
    client = TestClient(app)
    r = client.post(
        "/api/bookings",
        json=booking_payload(place.id),
        headers={"X-API-Key": key},
    )
    assert r.status_code == 400
