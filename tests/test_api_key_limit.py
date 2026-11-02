import random

from fastapi.testclient import TestClient

from app import crud
from app.database import SessionLocal
from app.main import app


def unique_email() -> str:
    return f"keylimit{random.randint(1_000_000, 9_999_999)}@example.com"


def unique_phone() -> str:
    return "+79" + "".join(str(random.randint(0, 9)) for _ in range(9))


def test_only_one_active_api_key():
    client = TestClient(app)
    email = unique_email()
    register = client.post(
        "/web/register",
        data={
            "surname": "Ключев",
            "phone": unique_phone(),
            "email": email,
            "password": "Strong12!",
        },
        follow_redirects=False,
    )
    assert register.status_code == 303

    first = client.post("/web/api-keys")
    assert first.status_code == 200
    assert "bk_" in first.text

    second = client.post("/web/api-keys")
    assert second.status_code == 400
    assert "уже есть активный API-ключ" in second.text

    db = SessionLocal()
    try:
        customer = crud.get_customer_by_email(db, email)
        active = crud.get_active_api_key_by_customer(db, customer.id)
        assert active is not None
        key_id = active.id
        assert len(crud.get_api_keys_by_customer(db, customer.id)) == 1
    finally:
        db.close()

    revoke = client.post(f"/web/api-keys/{key_id}/revoke", follow_redirects=False)
    assert revoke.status_code == 303

    third = client.post("/web/api-keys")
    assert third.status_code == 200
    assert "bk_" in third.text

    db = SessionLocal()
    try:
        customer = crud.get_customer_by_email(db, email)
        assert len(crud.get_api_keys_by_customer(db, customer.id)) == 2
        active = crud.get_active_api_key_by_customer(db, customer.id)
        assert active is not None
    finally:
        db.close()
