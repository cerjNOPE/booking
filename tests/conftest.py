import random

import pytest

from app.database import SessionLocal
from app.images import image_filenames
from app.models import ApiKey, Booking, BookingCounter, Customer, Place

STREETS = [
    "Лесная",
    "Сосновая",
    "Речная",
    "Озёрная",
    "Кедровая",
    "Полярная",
    "Тихая",
    "Берёзовая",
    "Горная",
    "Песчаная",
    "Прибрежная",
    "Ромашковая",
]


def _build_places(count: int = 20, inactive: int = 4):
    """Несохранённые места для тестов."""
    if inactive > count:
        raise ValueError("Неактивных мест не может быть больше общего количества")

    inactive_indexes = set(random.sample(range(count), inactive))
    images = image_filenames()
    places = []

    for index in range(count):
        street = random.choice(STREETS)
        house = random.randint(1, 60)
        places.append(
            Place(
                capacity=random.randint(1, 8),
                address=f"ул. {street}, {house}",
                isActive=index not in inactive_indexes,
                image_filename=images[index % len(images)] if images else None,
            )
        )

    return places


@pytest.fixture
def build_places():
    return _build_places


@pytest.fixture(scope="session", autouse=True)
def cleanup_after_tests():
    db = SessionLocal()
    try:
        initial_place_ids = {place_id for (place_id,) in db.query(Place.id).all()}
    finally:
        db.close()

    yield

    db = SessionLocal()
    try:
        db.query(ApiKey).delete(synchronize_session=False)
        db.query(Booking).delete(synchronize_session=False)
        db.query(BookingCounter).delete(synchronize_session=False)
        db.query(Customer).delete(synchronize_session=False)

        places_query = db.query(Place)
        if initial_place_ids:
            places_query = places_query.filter(Place.id.notin_(initial_place_ids))
        places_query.delete(synchronize_session=False)

        db.commit()
    finally:
        db.close()
