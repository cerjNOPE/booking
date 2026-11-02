import random
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import crud, models
from app.database import SessionLocal
from app.main import app
from app.security import md5_hash


def unique_phone() -> str:
    return "+79" + "".join(str(random.randint(0, 9)) for _ in range(9))


def unique_email() -> str:
    return f"feature{random.randint(1_000_000, 9_999_999)}@example.com"


def register_client(phone=None, email=None, password="Strong12!"):
    client = TestClient(app)
    phone = phone or unique_phone()
    email = email or unique_email()
    r = client.post(
        "/web/register",
        data={"surname": "Функциев", "phone": phone, "email": email, "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return client, phone, email, password


def make_place(capacity=4, active=True):
    db = SessionLocal()
    try:
        place = models.Place(
            capacity=capacity,
            address=f"ул. Тестовая, {random.randint(1, 90)}",
            isActive=active,
        )
        db.add(place)
        db.commit()
        db.refresh(place)
        return place
    finally:
        db.close()


def future(days=5):
    return (date.today() + timedelta(days=days)).isoformat()


def test_forgot_password_changes_password():
    client, phone, email, _ = register_client()
    client.get("/logout", follow_redirects=False)

    r = client.post(
        "/web/forgot-password",
        data={"identifier": email, "new_password": "NewPass12!", "confirm": "NewPass12!"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/?reset=1"

    login = client.post(
        "/web/login",
        data={"identifier": phone, "password": "NewPass12!"},
        follow_redirects=False,
    )
    assert login.status_code == 303


def test_forgot_password_validation():
    client, _, email, _ = register_client()
    client.get("/logout", follow_redirects=False)

    weak = client.post(
        "/web/forgot-password",
        data={"identifier": email, "new_password": "weak", "confirm": "weak"},
        follow_redirects=False,
    )
    assert weak.status_code == 400
    assert "Пароль должен содержать" in weak.text

    mismatch = client.post(
        "/web/forgot-password",
        data={"identifier": email, "new_password": "GoodPass12!", "confirm": "OtherPass12!"},
        follow_redirects=False,
    )
    assert mismatch.status_code == 400
    assert "не совпадают" in mismatch.text

    unknown = client.post(
        "/web/forgot-password",
        data={"identifier": unique_email(), "new_password": "GoodPass12!", "confirm": "GoodPass12!"},
        follow_redirects=False,
    )
    assert unknown.status_code == 404
    assert "не найден" in unknown.text


def test_registration_duplicate_highlights_and_offers_login():
    phone = unique_phone()
    register_client(phone=phone)
    other = TestClient(app)

    r = other.post(
        "/web/register",
        data={"surname": "Дубль", "phone": phone, "email": unique_email(), "password": "Strong12!"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "Телефон уже занят" in r.text
    assert 'href="/"' in r.text
    assert 'input-error' in r.text


def test_language_switch_to_english():
    client = TestClient(app)
    r = client.get("/lang/en", follow_redirects=False)
    assert r.status_code == 303
    assert client.cookies.get("lang") == "en"

    page = client.get("/")
    assert "Sign in" in page.text
    assert "Forgot your password?" in page.text


def test_home_shows_instructions_places_contacts_and_inactive_label():
    client, _, _, _ = register_client()
    active = make_place(capacity=3, active=True)
    inactive = make_place(active=False)

    r = client.get("/")
    assert r.status_code == 200
    assert "Как пользоваться системой" in r.text
    assert active.address in r.text
    assert inactive.address in r.text
    assert "Место временно не доступно" in r.text
    assert "3 мест" in r.text
    assert "camping@example.com" in r.text
    assert "+7 (900) 000-00-00" in r.text
    assert "Забронировать" in r.text


def test_booking_page_autofills_selected_place():
    client, _, _, _ = register_client()
    selected = make_place(capacity=5)
    inactive = make_place(active=False)

    r = client.get(f"/book?place_id={selected.id}")
    assert r.status_code == 200
    assert selected.address in r.text
    assert 'value="5"' in r.text
    assert 'id="capacity-output"' in r.text
    assert "readonly" in r.text
    assert f">{inactive.address}</option>" not in r.text
    assert "data-capacity" in r.text


def test_web_booking_create_view_and_cancel():
    client, _, _, _ = register_client()
    place = make_place(capacity=2)

    created = client.post(
        "/web/bookings",
        data={"place_id": str(place.id), "check_in": future(5), "check_out": future(7), "guests": "2"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    detail_url = created.headers["location"]
    assert detail_url.startswith("/bookings/")

    detail = client.get(detail_url)
    assert detail.status_code == 200
    assert "Забронировано" in detail.text

    listing = client.get("/bookings")
    assert place.address in listing.text
    assert "Забронировано" in listing.text

    booking_id = detail_url.split("/")[2].split("?")[0]
    cancel = client.post(f"/bookings/{booking_id}/cancel", follow_redirects=False)
    assert cancel.status_code == 303
    assert cancel.headers["location"] == "/bookings?cancelled=1"

    db = SessionLocal()
    try:
        assert crud.get_booking(db, int(booking_id)).status == "cancelled"
    finally:
        db.close()


def test_cancel_confirmation_dialog_present():
    client, _, _, _ = register_client()
    place = make_place()
    client.post(
        "/web/bookings",
        data={"place_id": str(place.id), "check_in": future(5), "check_out": future(7), "guests": "1"},
        follow_redirects=False,
    )
    page = client.get("/bookings")
    assert "Вы точно хотите отменить бронь?" in page.text


def test_booking_capacity_busy_and_past_date_errors():
    client, _, _, _ = register_client()
    place = make_place(capacity=2)

    over_capacity = client.post(
        "/web/bookings",
        data={"place_id": str(place.id), "check_in": future(5), "check_out": future(7), "guests": "3"},
        follow_redirects=False,
    )
    assert over_capacity.status_code == 400
    assert "Превышено количество вмещаемых гостей" in over_capacity.text

    past = client.post(
        "/web/bookings",
        data={
            "place_id": str(place.id),
            "check_in": (date.today() - timedelta(days=2)).isoformat(),
            "check_out": (date.today() + timedelta(days=1)).isoformat(),
            "guests": "1",
        },
        follow_redirects=False,
    )
    assert past.status_code == 400
    assert "прошедшие даты" in past.text

    first = client.post(
        "/web/bookings",
        data={"place_id": str(place.id), "check_in": future(10), "check_out": future(12), "guests": "1"},
        follow_redirects=False,
    )
    assert first.status_code == 303

    busy = client.post(
        "/web/bookings",
        data={"place_id": str(place.id), "check_in": future(11), "check_out": future(13), "guests": "1"},
        follow_redirects=False,
    )
    assert busy.status_code == 409
    assert "занято" in busy.text


def test_cancel_after_check_in_marks_expired():
    client, _, _, _ = register_client()
    place = make_place()

    db = SessionLocal()
    try:
        customer = db.query(models.Customer).order_by(models.Customer.id.desc()).first()
        booking = models.Booking(
            place_id=place.id,
            customer_id=customer.id,
            booking_number=crud.next_booking_number(db, customer.id),
            checkIn=date.today() - timedelta(days=1),
            checkOut=date.today() + timedelta(days=2),
            guestsCount=1,
            status="active",
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        booking_id = booking.id
    finally:
        db.close()

    r = client.post(f"/bookings/{booking_id}/cancel", follow_redirects=False)
    assert r.status_code == 303
    assert "expired=1" in r.headers["location"]

    db = SessionLocal()
    try:
        assert crud.get_booking(db, booking_id).status == "expired"
    finally:
        db.close()


def test_settings_profile_update():
    client, phone, email, _ = register_client()
    new_email = unique_email()
    digits = unique_phone().replace("+", "")
    new_phone = f"8 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"

    r = client.post(
        "/web/settings/profile",
        data={"surname": "Обновлённый", "phone": new_phone, "email": new_email},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?saved=1"

    db = SessionLocal()
    try:
        customer = crud.get_customer_by_email(db, new_email)
        assert customer is not None
        assert customer.fullName == "Обновлённый"
        assert customer.phone == "+7" + digits[1:]
    finally:
        db.close()


def test_settings_profile_validation():
    _, phone, _, _ = register_client()
    other, _, _, _ = register_client()

    taken = other.post(
        "/web/settings/profile",
        data={"surname": "Занятов", "phone": phone, "email": unique_email()},
        follow_redirects=False,
    )
    assert taken.status_code == 400
    assert "Телефон уже занят" in taken.text


def test_settings_password_change_requires_old_and_requirements():
    client, phone, _, password = register_client()

    wrong_old = client.post(
        "/web/settings/password",
        data={"old_password": "Wrong12!", "new_password": "NewPass12!", "confirm": "NewPass12!"},
        follow_redirects=False,
    )
    assert wrong_old.status_code == 400
    assert "Старый пароль" in wrong_old.text

    weak = client.post(
        "/web/settings/password",
        data={"old_password": password, "new_password": "weak", "confirm": "weak"},
        follow_redirects=False,
    )
    assert weak.status_code == 400
    assert "Пароль должен содержать" in weak.text

    mismatch = client.post(
        "/web/settings/password",
        data={"old_password": password, "new_password": "NewPass12!", "confirm": "Other12!"},
        follow_redirects=False,
    )
    assert mismatch.status_code == 400
    assert "не совпадают" in mismatch.text

    success = client.post(
        "/web/settings/password",
        data={"old_password": password, "new_password": "NewPass12!", "confirm": "NewPass12!"},
        follow_redirects=False,
    )
    assert success.status_code == 303
    assert success.headers["location"] == "/settings?password_changed=1"

    db = SessionLocal()
    try:
        db_customer = crud.get_customer_by_phone(db, phone)
        assert db_customer.password_hash == md5_hash("NewPass12!")
    finally:
        db.close()


def test_api_key_created_from_settings():
    client, _, _, _ = register_client()
    page = client.post("/web/api-keys")
    assert page.status_code == 200
    assert "bk_" in page.text
    assert "settings" in page.text.lower() or "API" in page.text
