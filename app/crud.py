from datetime import date, datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .security import generate_api_key, md5_hash


# ---------- Places ----------

def get_place(db: Session, place_id: int):
    return db.query(models.Place).filter(models.Place.id == place_id).first()


def get_places(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Place).offset(skip).limit(limit).all()


def get_active_places(db: Session):
    return (
        db.query(models.Place)
        .filter(models.Place.isActive.is_(True))
        .order_by(models.Place.id)
        .all()
    )


def create_place(db: Session, place: schemas.PlaceCreate):
    db_place = models.Place(**place.model_dump())
    db.add(db_place)
    db.commit()
    db.refresh(db_place)
    return db_place


# ---------- Customers ----------

def get_customer(db: Session, customer_id: int):
    return db.query(models.Customer).filter(models.Customer.id == customer_id).first()


def get_customer_by_phone(db: Session, phone: str):
    return db.query(models.Customer).filter(models.Customer.phone == phone).first()


def get_customer_by_email(db: Session, email: str):
    return db.query(models.Customer).filter(models.Customer.email == email.lower()).first()


def get_customer_by_login(db: Session, identifier: str, kind: str):
    """Поиск клиента для входа по телефону или email."""
    if kind == "phone":
        return get_customer_by_phone(db, identifier)
    if kind == "email":
        return get_customer_by_email(db, identifier)
    return None


def get_customers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Customer).offset(skip).limit(limit).all()


def create_customer(db: Session, customer: schemas.CustomerCreate):
    db_customer = models.Customer(
        fullName=customer.fullName,
        phone=customer.phone,
        email=customer.email.lower(),
        password_hash=md5_hash(customer.password),
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


def update_customer_profile(db: Session, customer: models.Customer, full_name: str, phone: str, email: str):
    customer.fullName = full_name
    customer.phone = phone
    customer.email = email.lower()
    db.commit()
    db.refresh(customer)
    return customer


def update_customer_password(db: Session, customer: models.Customer, password: str):
    customer.password_hash = md5_hash(password)
    db.commit()
    db.refresh(customer)
    return customer


def authenticate_customer(db: Session, identifier: str, kind: str, password: str):
    customer = get_customer_by_login(db, identifier, kind)
    if customer is None:
        return None
    if customer.password_hash != md5_hash(password):
        return None
    return customer


# ---------- API keys ----------

def create_api_key(db: Session, customer_id: int):

    raw_key, prefix, key_hash = generate_api_key()
    db_key = models.ApiKey(
        customer_id=customer_id,
        key_prefix=prefix,
        key_hash=key_hash,
    )
    db.add(db_key)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None, None
    db.refresh(db_key)
    return db_key, raw_key


def get_api_key_record_by_hash(db: Session, key_hash: str):
    return db.query(models.ApiKey).filter(models.ApiKey.key_hash == key_hash).first()


def get_api_keys_by_customer(db: Session, customer_id: int):
    return (
        db.query(models.ApiKey)
        .filter(models.ApiKey.customer_id == customer_id)
        .order_by(models.ApiKey.created_at.desc())
        .all()
    )


def get_active_api_key_by_customer(db: Session, customer_id: int):
    return (
        db.query(models.ApiKey)
        .filter(
            models.ApiKey.customer_id == customer_id,
            models.ApiKey.revoked_at.is_(None),
        )
        .first()
    )


def revoke_api_key(db: Session, key_id: int, customer_id: int):
    db_key = (
        db.query(models.ApiKey)
        .filter(
            models.ApiKey.id == key_id,
            models.ApiKey.customer_id == customer_id,
        )
        .first()
    )
    if db_key is None:
        return None
    if db_key.revoked_at is None:
        db_key.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_key)
    return db_key


# ---------- Bookings ----------

def is_place_free(db: Session, place_id: int, check_in: date, check_out: date):
    bookings = db.query(models.Booking).filter(
        models.Booking.place_id == place_id,
        models.Booking.status == "active"
    ).all()
    for b in bookings:
        if not (check_out <= b.checkIn or check_in >= b.checkOut):
            return False
    return True


def get_bookings(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Booking).offset(skip).limit(limit).all()


def get_bookings_by_customer(db: Session, customer_id: int):
    return (
        db.query(models.Booking)
        .filter(models.Booking.customer_id == customer_id)
        .order_by(models.Booking.checkIn.desc(), models.Booking.id.desc())
        .all()
    )


def next_booking_number(db: Session, customer_id: int) -> int:
    statement = pg_insert(models.BookingCounter).values(
        customer_id=customer_id,
        last_number=1,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[models.BookingCounter.customer_id],
        set_={"last_number": models.BookingCounter.last_number + 1},
    ).returning(models.BookingCounter.last_number)
    return db.execute(statement).scalar_one()


def create_booking(db: Session, booking: schemas.BookingCreate):
    if not is_place_free(db, booking.place_id, booking.checkIn, booking.checkOut):
        return None

    number = next_booking_number(db, booking.customer_id)
    data = booking.model_dump()
    data["booking_number"] = number
    db_booking = models.Booking(**data)
    db.add(db_booking)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(db_booking)
    return db_booking


def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()


def get_booking_by_number(db: Session, customer_id: int, booking_number: int):
    return (
        db.query(models.Booking)
        .filter(
            models.Booking.customer_id == customer_id,
            models.Booking.booking_number == booking_number,
        )
        .first()
    )


def change_booking_status(db: Session, booking_id: int, status: str):
    db_booking = get_booking(db, booking_id)
    if not db_booking:
        return None
    db_booking.status = status
    db.commit()
    db.refresh(db_booking)
    return db_booking
