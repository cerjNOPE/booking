import random

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.images import PLACEHOLDER, image_filenames, place_image
from app.main import app


class FakePlace:
    def __init__(self, filename):
        self.image_filename = filename


def make_place(image_filename):
    db = SessionLocal()
    try:
        place = models.Place(
            capacity=2,
            address=f"ул. Фотографическая, {random.randint(1, 99)}",
            isActive=True,
            image_filename=image_filename,
        )
        db.add(place)
        db.commit()
        db.refresh(place)
        return place
    finally:
        db.close()


def test_place_image_falls_back_to_placeholder():
    assert place_image(FakePlace(None)) == PLACEHOLDER
    assert place_image(FakePlace("no-such-file.jpg")) == PLACEHOLDER


def test_place_image_returns_existing_file():
    names = image_filenames()
    assert names, "В app/static/img должны быть фотографии camp-*.jpg"
    assert place_image(FakePlace(names[0])) == f"/static/img/{names[0]}"


def test_seed_places_assigns_images(build_places):
    places = build_places(count=5, inactive=1)
    assert all(place.image_filename for place in places)


def test_home_shows_placeholder_for_place_without_image():
    client = TestClient(app)
    client.post(
        "/web/register",
        data={
            "surname": "Фотов",
            "phone": "+79" + "".join(str(random.randint(0, 9)) for _ in range(9)),
            "email": f"photo{random.randint(1_000_000, 9_999_999)}@example.com",
            "password": "Strong12!",
        },
        follow_redirects=False,
    )
    make_place(None)
    names = image_filenames()
    make_place(names[0])

    page = client.get("/")
    assert page.status_code == 200
    assert PLACEHOLDER in page.text
    assert f"/static/img/{names[0]}" in page.text
