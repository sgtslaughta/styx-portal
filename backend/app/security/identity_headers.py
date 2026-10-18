"""Parser-independent backstop for spoofed identity headers.

Traefik's styx-strip-identity blanks an enumerated list of exact names. WSGI/CGI
stacks fold `-` and `_` (and case) into one variable, so mixed spellings such as
`X-Styx_User` would survive. The service forwardAuth handlers run after that
middleware and see what is left: any header whose normalised name is an identity
name, and which is not an (already blanked) exact dashed one, is refused.
"""
from fastapi import HTTPException, Request, status

IDENTITY_NAMES = frozenset({
    "x-styx-user", "x-styx-email", "x-styx-groups",
    "x-authentik-username", "x-authentik-groups", "x-authentik-email", "x-authentik-uid",
    "remote-user", "x-remote-user", "x-forwarded-user", "x-webauth-user"})


def has_disguised_identity(request: Request) -> bool:
    for raw, value in request.headers.raw:
        name = raw.decode("latin-1").lower()
        if name.replace("_", "-") in IDENTITY_NAMES and ("_" in name or value.strip()):
            return True
    return False


async def reject_disguised_identity(request: Request) -> None:
    if has_disguised_identity(request):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")
