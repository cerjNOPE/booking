
import argparse
import random

from app.database import SessionLocal
from app.images import image_filenames
from app.models import Place

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


def seed(count: int = 20, inactive: int = 4) -> list[Place]:
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

    db = SessionLocal()
    try:
        db.add_all(places)
        db.commit()
        for place in places:
            db.refresh(place)
        return places
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Заполнить БД тестовыми местами")
    parser.add_argument("--count", type=int, default=20, help="Всего мест (по умолчанию 20)")
    parser.add_argument(
        "--inactive", type=int, default=4, help="Из них неактивных (по умолчанию 4)"
    )
    args = parser.parse_args()

    places = seed(count=args.count, inactive=args.inactive)
    active = sum(1 for place in places if place.isActive)
    inactive = len(places) - active

    print(f"Добавлено мест: {len(places)} (активных: {active}, неактивных: {inactive})")
    for place in places:
        status = "активно" if place.isActive else "неактивно"
        print(f"  id={place.id:<4} {place.address:<24} мест: {place.capacity}  {status}")


if __name__ == "__main__":
    main()
