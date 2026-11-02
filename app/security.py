import hashlib
import re
import secrets

PHONE_RE = re.compile(r"^\+?\d{10,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-zА-Яа-я]{2,}$")
NAME_RE = re.compile(r"^[А-Яа-яЁёA-Za-z-]+$")

PASSWORD_MIN_LENGTH = 8
LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
DIGIT_RE = re.compile(r"\d")
SPECIAL_RE = re.compile(r"[^A-Za-zА-Яа-яЁё0-9\s]")


def md5_hash(password: str) -> str:
    """Пароль хранится в MD5 (по требованию ТЗ)."""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def sha256_hash(value: str) -> str:
    """SHA-256 для API-ключей."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Создаёт новый API-ключ.

    Возвращает (полный ключ, префикс для показа, SHA-256 хэш для БД).
    Полный ключ показывается пользователю один раз и в БД не хранится.
    """
    raw_key = "bk_" + secrets.token_urlsafe(32)
    return raw_key, raw_key[:12], sha256_hash(raw_key)


def normalize_phone(value: str) -> str:
    """Приводит телефон к виду для хранения в БД: +7XXXXXXXXXX.

    Понимает ввод вида `89991234567`, `8 (999) 123-45-67`,
    `+79991234567`, `9991234567`. Для остальных стран оставляет + и цифры.
    """
    digits = re.sub(r"\D", "", (value or "").strip())
    if not digits or digits in ("7", "8"):
        return ""
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return "+" + digits


def format_phone_display(value: str) -> str:
    """Формат для показа пользователю: 8 (999) 123-45-67."""
    digits = re.sub(r"\D", "", (value or "").strip())
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = "8" + digits[1:]
    elif len(digits) == 10:
        digits = "8" + digits
    if len(digits) == 11 and digits.startswith("8"):
        return f"8 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return (value or "").strip()


def is_valid_phone(value: str) -> bool:
    return bool(PHONE_RE.match(normalize_phone(value)))


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))


def is_valid_surname(value: str) -> bool:
    value = value.strip()
    if not value or " " in value:
        return False
    return bool(NAME_RE.match(value))


def password_requirements(password: str) -> dict:
    """Проверка требований к паролю.

    Пароль должен содержать минимум 8 символов, хотя бы одну букву,
    хотя бы одну цифру и хотя бы один специальный символ.
    """
    return {
        "length": len(password) >= PASSWORD_MIN_LENGTH,
        "letter": bool(LETTER_RE.search(password)),
        "digit": bool(DIGIT_RE.search(password)),
        "special": bool(SPECIAL_RE.search(password)),
    }


def is_valid_password(password: str) -> bool:
    return all(password_requirements(password).values())


def detect_login_identifier(value: str):
    """Определяет, что ввёл пользователь: телефон или email.

    Возвращает ("phone" | "email", нормализованное значение) либо (None, None).
    """
    value = value.strip()
    if not value:
        return None, None
    if "@" in value:
        if is_valid_email(value):
            return "email", value.lower()
        return None, None
    phone = normalize_phone(value)
    if is_valid_phone(phone):
        return "phone", phone
    return None, None
