from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

EXEMPT_PATHS = {"/auth/login", "/auth/setup", "/api/health", "/api/cluster/workers", "/api/cluster/heartbeat", "/setup", "/setup/complete"}
EXEMPT_PREFIXES = ("/static/",)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_mgr = request.app.state.auth

        # Skip if auth not configured (first boot)
        if not auth_mgr.is_configured():
            return await call_next(request)

        path = request.url.path

        # Skip exempt paths
        if path in EXEMPT_PATHS or any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        # Check session cookie
        token = request.cookies.get("taos_session")
        if token and auth_mgr.validate_session(token):
            return await call_next(request)

        # Redirect to login for browsers, 401 for API calls
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse("/auth/login", status_code=303)

        return JSONResponse({"error": "Authentication required"}, status_code=401)
