from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# FastAPI's built-in interactive docs load JS/CSS from a CDN — a strict CSP
# would break them, so they're excluded rather than trying to special-case
# jsdelivr into the policy (this is a JSON API; the docs are a dev convenience,
# not something that needs the same lockdown as the actual data endpoints).
_CSP_EXEMPT_PATHS = {"/docs", "/redoc", "/openapi.json"}

# default-src 'none' is safe here because this backend never returns HTML for
# real endpoints — every response is JSON (or a WebSocket upgrade), so there's
# nothing legitimate for a browser to execute/render even if it tried.
_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds the standard baseline security response headers that were
    entirely absent before — CORS alone doesn't cover clickjacking, MIME
    sniffing, or referrer leakage, and this is a JSON API with no legitimate
    reason to ever be framed or to execute injected content."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Ignored by browsers on plain HTTP (per spec), harmless to always send —
        # takes effect the moment this sits behind real TLS in production.
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        if request.url.path not in _CSP_EXEMPT_PATHS:
            response.headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY

        return response
