"""Navigation-aware denial: forwardAuth relays a non-2xx body to the browser."""
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

_NO_ACCESS_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>No access</title>
<style>body{font-family:system-ui;background:#0b0f14;color:#e6edf3;display:grid;
place-items:center;height:100vh;margin:0}main{text-align:center}a{color:#7aa2f7}</style>
</head><body><main><h1>No access</h1>
<p>Your account is not allowed to open this page. Ask an administrator for access.</p>
<p><a href="/">Back to Styx</a></p></main></body></html>"""


def is_navigation(request: Request) -> bool:
    return (request.headers.get("sec-fetch-mode") == "navigate"
            or "text/html" in request.headers.get("accept", ""))


def no_access(request: Request, detail: str = "No access") -> HTMLResponse:
    """Styx "no access" page (403) for navigations; JSON 403 (raised) otherwise.
    The page is static: nothing from the request is echoed."""
    if not is_navigation(request):
        raise HTTPException(403, detail)
    return HTMLResponse(_NO_ACCESS_HTML, status_code=403, headers={"Cache-Control": "no-store"})
