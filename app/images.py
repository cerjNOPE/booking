"""Работа с изображениями мест."""

import re
from pathlib import Path

IMAGE_DIR = Path(__file__).resolve().parent / "static" / "img"
PLACEHOLDER = "/static/img/placeholder.jpg"


def image_filenames() -> list[str]:
    """Все camp-*.jpg, отсортированные по номеру."""
    found = []
    for path in IMAGE_DIR.glob("camp-*.jpg"):
        match = re.fullmatch(r"camp-(\d+)\.jpg", path.name)
        if match:
            found.append((int(match.group(1)), path.name))
    found.sort()
    return [name for _, name in found]


def place_image(place) -> str:
    """Картинка места или заглушка, если файла нет."""
    filename = getattr(place, "image_filename", None)
    if filename and (IMAGE_DIR / filename).is_file():
        return f"/static/img/{filename}"
    return PLACEHOLDER
