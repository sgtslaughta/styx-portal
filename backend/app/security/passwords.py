import re
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError):
        return False


@dataclass
class PasswordPolicy:
    min_length: int
    require_upper: bool
    require_lower: bool
    require_digit: bool
    require_symbol: bool


def validate_password(password: str, policy: PasswordPolicy) -> None:
    """Raise ValueError listing every unmet rule; return None if compliant."""
    problems: list[str] = []
    if len(password) < policy.min_length:
        problems.append(f"at least {policy.min_length} characters")
    if policy.require_upper and not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if policy.require_lower and not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if policy.require_digit and not re.search(r"\d", password):
        problems.append("a digit")
    if policy.require_symbol and not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a symbol")
    if problems:
        raise ValueError("Password must contain " + ", ".join(problems) + ".")


def current_policy() -> PasswordPolicy:
    from app.services.settings_store import settings
    return PasswordPolicy(
        min_length=settings.get("PASSWORD_MIN_LENGTH"),
        require_upper=settings.get("PASSWORD_REQUIRE_UPPER"),
        require_lower=settings.get("PASSWORD_REQUIRE_LOWER"),
        require_digit=settings.get("PASSWORD_REQUIRE_DIGIT"),
        require_symbol=settings.get("PASSWORD_REQUIRE_SYMBOL"),
    )
