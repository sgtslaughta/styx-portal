import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import Settings

_settings = Settings()


def _fernet_key() -> bytes:
    """Derive a stable 32-byte Fernet key from JWT_SECRET via HKDF-SHA256."""
    secret = _settings.jwt_secret_or_raise().encode()
    raw = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"selkies-oauth-secret-enc",
    ).derive(secret)
    return base64.urlsafe_b64encode(raw)


def _fernet() -> Fernet:
    return Fernet(_fernet_key())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
