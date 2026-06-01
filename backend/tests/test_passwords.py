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
