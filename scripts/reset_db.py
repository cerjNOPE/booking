
from app import models
from app.database import Base, engine


def main() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Схема БД пересоздана")


if __name__ == "__main__":
    main()
