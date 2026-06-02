# shared/middleware.py
"""
Security middleware for FastAPI applications.
Provides: security headers, rate limiting setup, and CSRF helpers.
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from slowapi import Limiter
from slowapi.util import get_remote_address


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects security headers into every HTTP response.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(self), geolocation=(self)"
        )
        # Content-Security-Policy — allow inline scripts/styles for Jinja templates
        # and Leaflet map tiles from OpenStreetMap
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'none'"
        )

        return response


# ---------------------------------------------------------------------------
# Rate Limiter (shared instance)
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
