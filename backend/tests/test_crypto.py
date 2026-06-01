import pytest
from app.security import crypto


def test_roundtrip():
    token = crypto.encrypt_secret("super-secret-value")
    assert token != "super-secret-value"
    assert crypto.decrypt_secret(token) == "super-secret-value"


def test_key_is_stable_for_same_jwt_secret():
    a = crypto._fernet_key()
    b = crypto._fernet_key()
    assert a == b


def test_decrypt_garbage_raises():
    with pytest.raises(Exception):
        crypto.decrypt_secret("not-a-valid-token")
