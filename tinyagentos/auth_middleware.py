from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

EXEMPT_PATHS = {"/auth/login", "/auth/setup", "/auth/status", "/auth/me", "/api/health", "/api/cluster/workers", "/api/cluster/heartbeat", "/setup", "/setup/complete"}
EXEMPT_PREFIXES = ("/static/", "/desktop", "/chat-pwa")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_mgr = request.app.state.auth
        path = request.url.path

        # Always allow exempt paths through (SPA shell, static assets, auth
        # endpoints, cluster heartbeat). Without this, a cached old client
        # could bypass onboarding by hitting an /api endpoint that the
        # not-configured branch used to allow through unconditionally.
        if path in EXEMPT_PATHS or any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        # First boot: no user yet. /api/* must hard-fail so the SPA falls
        # through to its onboarding flow instead of acting on stale state.
        if not auth_mgr.is_configured():
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return RedirectResponse("/desktop", status_code=303)
            return JSONResponse(
                {"error": "onboarding_required", "needs_onboarding": True},
                status_code=401,
            )

        # Check session cookie
        token = request.cookies.get("taos_session")
        if token and auth_mgr.validate_session(token):
            return await call_next(request)

        # Redirect to login for browsers, 401 for API calls
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse("/auth/login", status_code=303)

        return JSONResponse({"error": "Authentication required"}, status_code=401)
