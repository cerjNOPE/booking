from app.i18n import translate
from app.security import (
    detect_login_identifier,
    format_phone_display,
    generate_api_key,
    is_valid_email,
    is_valid_password,
    is_valid_phone,
    is_valid_surname,
    md5_hash,
    normalize_phone,
    password_requirements,
    sha256_hash,
)


def test_hashes():
    assert md5_hash("secret") == "5ebe2294ecd0e0f08eab7690d2a6ee69"
    assert sha256_hash("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_generate_api_key():
    raw_key, prefix, key_hash = generate_api_key()
    assert raw_key.startswith("bk_")
    assert len(raw_key) > 20
    assert prefix == raw_key[:12]
    assert key_hash == sha256_hash(raw_key)


def test_normalize_phone():
    assert normalize_phone("89991234567") == "+79991234567"
    assert normalize_phone("8 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("+7 999 123-45-67") == "+79991234567"
    assert normalize_phone("9991234567") == "+79991234567"
    assert normalize_phone("   ") == ""
    assert normalize_phone("8") == ""


def test_format_phone_display():
    assert format_phone_display("+79991234567") == "8 (999) 123-45-67"
    assert format_phone_display("89991234567") == "8 (999) 123-45-67"
    assert format_phone_display("9991234567") == "8 (999) 123-45-67"
    assert format_phone_display("user@example.com") == "user@example.com"


def test_validators():
    assert is_valid_phone("8 (999) 123-45-67")
    assert not is_valid_phone("123")
    assert is_valid_email("user@example.com")
    assert not is_valid_email("bad@")
    assert is_valid_surname("Иванов-Петров")
    assert not is_valid_surname("Иван Иванов")
    assert not is_valid_surname("")


def test_password_requirements():
    assert password_requirements("Strong12!") == {
        "length": True,
        "letter": True,
        "digit": True,
        "special": True,
    }
    assert password_requirements("short") == {
        "length": False,
        "letter": True,
        "digit": False,
        "special": False,
    }
    assert is_valid_password("Strong12!")
    assert not is_valid_password("weak")


def test_detect_login_identifier():
    assert detect_login_identifier("89991234567") == ("phone", "+79991234567")
    assert detect_login_identifier("user@example.com") == ("email", "user@example.com")
    assert detect_login_identifier("User@Example.COM") == ("email", "user@example.com")
    assert detect_login_identifier("bad@") == (None, None)
    assert detect_login_identifier("") == (None, None)


def test_translate_fallback():
    assert translate("en", "app.name") == "Camping"
    assert translate("ru", "app.name") == "Кемпинг"
    assert translate("fr", "app.name") == "Кемпинг"
    assert translate("ru", "unknown.key") == "unknown.key"
