from app.security import detect_login_identifier, format_phone_display, normalize_phone


def test_normalize_phone_variants():
    assert normalize_phone("89991234567") == "+79991234567"
    assert normalize_phone("8 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("9991234567") == "+79991234567"
    assert normalize_phone("   ") == ""
    assert normalize_phone("8") == ""
    assert normalize_phone("123") == "+123"


def test_format_phone_display():
    assert format_phone_display("+79991234567") == "8 (999) 123-45-67"
    assert format_phone_display("89991234567") == "8 (999) 123-45-67"
    assert format_phone_display("8 (999) 123-45-67") == "8 (999) 123-45-67"
    assert format_phone_display("user@example.com") == "user@example.com"


def test_detect_login_identifier():
    assert detect_login_identifier("89991234567") == ("phone", "+79991234567")
    assert detect_login_identifier("8 (999) 123-45-67") == ("phone", "+79991234567")
    assert detect_login_identifier("user@example.com") == ("email", "user@example.com")
    assert detect_login_identifier("User@Example.COM") == ("email", "user@example.com")
    assert detect_login_identifier("не телефон") == (None, None)
    assert detect_login_identifier("") == (None, None)
