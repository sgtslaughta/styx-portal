"""Shared ?next= rule for every redirect builder (mirrors frontend lib/safe-next.ts).

A cross-site link to /login?next=X becomes a same-site navigation once the SPA
follows it, so SameSite=Strict cookies ride along. next= may therefore only
name pages a user opens (SPA routes, /w/, /i/, service paths) — never Styx's
API/control paths, and never via percent-encoded separators or dot segments.
"""
import re
from urllib.parse import unquote

# One leading "/", then no "/" or "\" right after it ("//host", "/\host" are
# protocol-relative to browsers); no whitespace or control characters.
_SHAPE = re.compile(r"^/(?![/\\])[A-Za-z0-9._~!$&'()*+,;=:@%/?#\[\]-]*$")
_ENCODED_SEP = re.compile(r"%(2e|2f|5c)", re.IGNORECASE)
BLOCKED_FIRST_SEGMENTS = frozenset({
    "api", "internal", "_styx", "login", "logout", "setup", "accept-invite", "change-password"})


def safe_next(uri: str | None, *, allow_login: bool = False) -> str | None:
    """`uri` unchanged if it is a safe same-site next target, else None.

    allow_login: only for /_styx/exit, which chains to /login?next=… (the login
    page re-validates its own next with the same rule).
    """
    if not uri or not _SHAPE.match(uri):
        return None
    path = re.split(r"[?#]", uri, maxsplit=1)[0]
    decoded = unquote(path)
    if _ENCODED_SEP.search(path) or _ENCODED_SEP.search(decoded) or "\\" in decoded:
        return None
    if re.search(r"[\x00-\x20\x7f]", decoded):
        return None
    segs = decoded.split("/")
    if "." in segs or ".." in segs:
        return None
    blocked = BLOCKED_FIRST_SEGMENTS - {"login"} if allow_login else BLOCKED_FIRST_SEGMENTS
    return None if segs[1].lower() in blocked else uri
