from app.security.passwords import hash_password, verify_password


def test_hash_is_not_plaintext():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert h.startswith("$argon2")


def test_verify_correct_password():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_wrong_password():
    h = hash_password("hunter2")
    assert verify_password("wrong", h) is False


def test_validate_password_length():
    from app.security.passwords import validate_password, PasswordPolicy
    p = PasswordPolicy(min_length=12, require_upper=False, require_lower=False,
                       require_digit=False, require_symbol=False)
    import pytest
    with pytest.raises(ValueError):
        validate_password("short", p)
    validate_password("x" * 12, p)  # ok


def test_validate_password_classes():
    from app.security.passwords import validate_password, PasswordPolicy
    import pytest
    p = PasswordPolicy(min_length=4, require_upper=True, require_lower=True,
                       require_digit=True, require_symbol=True)
    with pytest.raises(ValueError):
        validate_password("abcd", p)            # missing upper/digit/symbol
    validate_password("Ab1!", p)                # satisfies all
