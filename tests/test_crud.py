import random

from app import crud, schemas
from app.database import SessionLocal
from app.security import md5_hash


def unique_phone() -> str:
    return "+79" + "".join(str(random.randint(0, 9)) for _ in range(9))


def unique_email() -> str:
    return f"crud{random.randint(1_000_000, 9_999_999)}@example.com"


def create_customer(db, password="Strong12!"):
    return crud.create_customer(
        db,
        schemas.CustomerCreate(
            fullName="Крудов",
            phone=unique_phone(),
            email=unique_email(),
            password=password,
        ),
    )


def test_customer_lookup_and_authenticate():
    db = SessionLocal()
    try:
        customer = create_customer(db, password="Strong12!")

        assert crud.get_customer_by_phone(db, customer.phone).id == customer.id
        assert crud.get_customer_by_email(db, customer.email.upper()).id == customer.id
        assert crud.get_customer_by_login(db, customer.phone, "phone").id == customer.id
        assert crud.get_customer_by_login(db, customer.email, "email").id == customer.id
        assert crud.get_customer_by_login(db, "unknown", "other") is None

        assert crud.authenticate_customer(db, customer.phone, "phone", "Strong12!").id == customer.id
        assert crud.authenticate_customer(db, customer.phone, "phone", "Wrong12!") is None
        assert crud.authenticate_customer(db, "missing", "phone", "Strong12!") is None

        assert any(item.id == customer.id for item in crud.get_customers(db))
    finally:
        db.close()


def test_update_profile_and_password():
    db = SessionLocal()
    try:
        customer = create_customer(db, password="OldPass12!")
        new_phone = unique_phone()
        new_email = unique_email()

        updated = crud.update_customer_profile(db, customer, "Обновлён", new_phone, new_email)
        assert updated.fullName == "Обновлён"
        assert updated.phone == new_phone
        assert updated.email == new_email.lower()

        changed = crud.update_customer_password(db, customer, "NewPass12!")
        assert changed.password_hash == md5_hash("NewPass12!")
    finally:
        db.close()


def test_second_active_api_key_is_rejected():
    db = SessionLocal()
    try:
        customer = create_customer(db)

        first, raw_first = crud.create_api_key(db, customer.id)
        assert first is not None
        assert raw_first.startswith("bk_")

        second, raw_second = crud.create_api_key(db, customer.id)
        assert second is None
        assert raw_second is None

        active = crud.get_active_api_key_by_customer(db, customer.id)
        assert active is not None
        assert active.id == first.id
    finally:
        db.close()
