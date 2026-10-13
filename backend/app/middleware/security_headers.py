from starlette.middleware.base import BaseHTTPMiddleware

_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


# Styx's own error/notice pages are shown inside the shell's iframe (a stopped
# app, no access, expired session). Same-origin framing has no clickjack surface.
SAMEORIGIN_HEADERS = {"X-Frame-Options": "SAMEORIGIN",
                      "Content-Security-Policy": _CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'")}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # setdefault: a route may set a scoped CSP (e.g. the SSO test probe page,
        # which needs an inline <script>). Don't clobber it with the strict default.
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp
