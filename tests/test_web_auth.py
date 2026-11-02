import random

from fastapi.testclient import TestClient

from app import crud
from app.database import SessionLocal
from app.main import app
from app.security import md5_hash


def unique_phone() -> str:
    return "+79" + "".join(str(random.randint(0, 9)) for _ in range(9))


def unique_email() -> str:
    return f"user{random.randint(1_000_000, 9_999_999)}@example.com"


def register(client, phone=None, email=None, surname="Иванов", password="secret12!"):
    return client.post(
        "/web/register",
        data={
            "surname": surname,
            "phone": phone or unique_phone(),
            "email": email or unique_email(),
            "password": password,
        },
        follow_redirects=False,
    )


def test_root_shows_login_without_cookie():
    fresh = TestClient(app)
    r = fresh.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "Вход" in r.text
    assert "Выйти" not in r.text


def test_register_page_has_fields_mask_and_requirements():
    fresh = TestClient(app)
    r = fresh.get("/register")
    assert r.status_code == 200
    assert 'name="surname"' in r.text
    assert 'name="phone"' in r.text
    assert 'name="email"' in r.text
    assert 'name="password"' in r.text
    assert "data-phone-mask" in r.text
    assert 'pattern=' in r.text
    assert "password-requirements" in r.text
    assert "eye-btn" in r.text


def test_register_creates_customer_and_md5():
    fresh = TestClient(app)
    phone = unique_phone()
    email = unique_email()
    r = register(fresh, phone=phone, email=email, password="qwerty12!")
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert "user_id" in r.cookies

    db = SessionLocal()
    try:
        customer = crud.get_customer_by_email(db, email)
        assert customer is not None
        assert customer.phone == phone
        assert customer.password_hash == md5_hash("qwerty12!")
        assert customer.password_hash != "qwerty12!"
    finally:
        db.close()

    home = fresh.get("/")
    assert home.status_code == 200
    assert "Выйти" in home.text


def test_login_by_phone_and_email():
    fresh = TestClient(app)
    phone = unique_phone()
    email = unique_email()
    register(fresh, phone=phone, email=email, password="pass123!")
    fresh.get("/logout", follow_redirects=False)

    r1 = fresh.post(
        "/web/login",
        data={"identifier": phone, "password": "pass123!"},
        follow_redirects=False,
    )
    assert r1.status_code == 303
    assert r1.headers["location"] == "/"

    fresh.get("/logout", follow_redirects=False)

    r2 = fresh.post(
        "/web/login",
        data={"identifier": email, "password": "pass123!"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert r2.headers["location"] == "/"


def test_login_wrong_password_says_wrong_password():
    fresh = TestClient(app)
    phone = unique_phone()
    register(fresh, phone=phone, password="right12!")
    fresh.get("/logout", follow_redirects=False)

    r = fresh.post(
        "/web/login",
        data={"identifier": phone, "password": "wrong12!"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "Неверный пароль" in r.text
    assert "не найден" not in r.text
    # введённый телефон сохраняется и показывается в формате 8 (xxx) xxx-xx-xx
    assert "8 (" in r.text


def test_login_unknown_user_says_not_found_and_suggests_register():
    fresh = TestClient(app)
    missing = unique_phone()
    r = fresh.post(
        "/web/login",
        data={"identifier": missing, "password": "any12!A"},
        follow_redirects=False,
    )
    assert r.status_code == 404
    assert "не найден" in r.text
    assert 'href="/register"' in r.text
    assert "8 (" in r.text


def test_login_invalid_format():
    fresh = TestClient(app)
    r = fresh.post(
        "/web/login",
        data={"identifier": "не телефон и не email", "password": "x"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "корректный" in r.text


def test_register_surname_with_space_rejected_and_preserved():
    fresh = TestClient(app)
    phone = unique_phone()
    email = unique_email()
    r = register(fresh, phone=phone, email=email, surname="Иван Иванов")
    assert r.status_code == 400
    assert "без пробелов" in r.text
    assert 'input-error' in r.text
    # телефон сохраняется и показывается в формате 8 (xxx) xxx-xx-xx
    assert "8 (" in r.text
    assert email in r.text


def test_register_empty_fields_are_handled():
    fresh = TestClient(app)
    cases = [
        ({"surname": "", "phone": "89991234567", "email": "a@b.ru", "password": "Strong12!"}, "Введите фамилию"),
        ({"surname": "Иванов", "phone": "", "email": "a@b.ru", "password": "Strong12!"}, "Введите номер телефона"),
        ({"surname": "Иванов", "phone": "89991234567", "email": "", "password": "Strong12!"}, "Введите email"),
        ({"surname": "Иванов", "phone": "89991234567", "email": "a@b.ru", "password": ""}, "Введите пароль"),
    ]
    for payload, message in cases:
        r = fresh.post("/web/register", data=payload, follow_redirects=False)
        assert r.status_code == 400, payload
        assert message in r.text, payload


def test_register_whitespace_only_fields_are_empty():
    fresh = TestClient(app)
    r = fresh.post(
        "/web/register",
        data={"surname": "   ", "phone": "   ", "email": "   ", "password": "   "},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "Введите фамилию" in r.text


def test_phone_is_stored_normalized_and_displayed_as_8_format():
    fresh = TestClient(app)
    email = unique_email()
    phone = unique_phone()
    digits = phone.replace("+", "")
    display = f"8 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    r = register(fresh, phone=display, email=email, password="Strong12!")
    assert r.status_code == 303

    db = SessionLocal()
    try:
        customer = crud.get_customer_by_email(db, email)
        assert customer.phone == "+7" + digits[1:]
    finally:
        db.close()


def test_login_with_8_format_phone():
    fresh = TestClient(app)
    email = unique_email()
    phone = unique_phone()
    digits = phone.replace("+", "")  # 7XXXXXXXXXX
    display = f"8 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    register(fresh, phone=phone, email=email, password="Strong12!")
    fresh.get("/logout", follow_redirects=False)

    r = fresh.post(
        "/web/login",
        data={"identifier": display, "password": "Strong12!"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_login_empty_fields_are_handled():
    fresh = TestClient(app)
    r1 = fresh.post(
        "/web/login",
        data={"identifier": "", "password": "x"},
        follow_redirects=False,
    )
    assert r1.status_code == 400
    assert "Введите номер телефона или email" in r1.text

    r2 = fresh.post(
        "/web/login",
        data={"identifier": "user@example.com", "password": ""},
        follow_redirects=False,
    )
    assert r2.status_code == 400
    assert "Введите пароль" in r2.text


def test_register_invalid_phone_rejected_and_preserved():
    fresh = TestClient(app)
    r = register(fresh, phone="123", surname="Петров")
    assert r.status_code == 400
    assert "телефон" in r.text.lower()
    assert "Петров" in r.text


def test_register_invalid_email_rejected():
    fresh = TestClient(app)
    r = register(fresh, email="not-an-email")
    assert r.status_code == 400
    assert "email" in r.text.lower()


def test_register_weak_password_rejected():
    fresh = TestClient(app)
    cases = ["short1!", "12345678!", "onlyletters!", "NoSpecial12"]
    for password in cases:
        r = register(fresh, password=password)
        assert r.status_code == 400, password
        assert "Пароль должен содержать" in r.text


def test_register_duplicate_contact_rejected():
    fresh = TestClient(app)
    phone = unique_phone()
    email = unique_email()
    assert register(fresh, phone=phone, email=email).status_code == 303
    fresh.get("/logout", follow_redirects=False)

    r = register(fresh, phone=phone, email=unique_email())
    assert r.status_code == 400
    assert "уже занят" in r.text


def test_home_is_closed_with_forged_cookie():
    fresh = TestClient(app)
    fresh.cookies.set("user_id", "999999999")
    r = fresh.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "Вход" in r.text
    assert "Выйти" not in r.text


def test_logout_clears_cookie():
    fresh = TestClient(app)
    register(fresh)
    r = fresh.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    after = fresh.get("/", follow_redirects=False)
    assert "Вход" in after.text
