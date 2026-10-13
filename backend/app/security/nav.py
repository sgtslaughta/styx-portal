"""Navigation-aware denial: forwardAuth relays a non-2xx body to the browser."""
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from app.security.page_style import styx_page

_NO_ACCESS_HTML = styx_page(
    "No access",
    "<h1>No access</h1><p>Your account can't open this app. Ask an administrator to add you "
    'to its group.</p><div class="actions"><a class="btn" href="/_styx/exit">Back to Styx</a></div>')


def is_navigation(request: Request) -> bool:
    return (request.headers.get("sec-fetch-mode") == "navigate"
            or "text/html" in request.headers.get("accept", ""))


def no_access(request: Request, detail: str = "No access") -> HTMLResponse:
    """Styx "no access" page (403) for navigations; JSON 403 (raised) otherwise.
    The page is static: nothing from the request is echoed."""
    if not is_navigation(request):
        raise HTTPException(403, detail)
    return HTMLResponse(_NO_ACCESS_HTML, status_code=403, headers={"Cache-Control": "no-store"})
