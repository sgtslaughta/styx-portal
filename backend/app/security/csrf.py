import secrets

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_valid(cookie: str | None, header: str | None) -> bool:
    if not cookie or not header:
        return False
    return secrets.compare_digest(cookie, header)
