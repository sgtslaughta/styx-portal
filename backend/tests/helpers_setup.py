"""Test helper: the first-run setup code field for POST /api/auth/setup bodies."""
from app.security import setup_token


def st() -> dict:
    return {"setup_token": setup_token.current()}
