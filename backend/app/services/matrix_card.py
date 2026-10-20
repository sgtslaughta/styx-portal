"""Matrix card 2FA: 5x10 grid of 3-char codes; login asks for 3 random cells."""
import hmac
import json
import secrets

from app.security.crypto import decrypt_secret, encrypt_secret

COLUMNS = "ABCDE"
ROWS = range(1, 11)
ALPHABET = "ACDEFGHJKLMNPQRTUVWXY34679"
CELLS = [f"{c}{r}" for r in ROWS for c in COLUMNS]


def generate_card() -> dict[str, str]:
    return {c: "".join(secrets.choice(ALPHABET) for _ in range(3)) for c in CELLS}


def pick_challenge(n: int = 3) -> list[str]:
    pool = list(CELLS)
    return [pool.pop(secrets.randbelow(len(pool))) for _ in range(n)]


def verify(card: dict[str, str], challenge: list[str], answers: list[str]) -> bool:
    # Fail closed: empty challenge, count mismatch or an unknown cell never verifies.
    if not challenge or len(answers) != len(challenge) or any(c not in card for c in challenge):
        return False
    ok = True
    for cell, ans in zip(challenge, answers):
        ok &= hmac.compare_digest(card[cell].encode(), str(ans).strip().upper().encode())
    return ok


def seal(obj) -> str:
    return encrypt_secret(json.dumps(obj))


def unseal(token: str):
    return json.loads(decrypt_secret(token))
