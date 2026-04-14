from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_PAGE_HTML = """\
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In — TinyAgentOS</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
    <style>
        body { display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #13111c; }
        .login-card { max-width: 380px; width: 100%; padding: 2.5rem; border-radius: 12px; background: #1e1b2e; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
        .login-card h1 { text-align: center; font-size: 1.5rem; margin-bottom: 0.25rem; }
        .login-card .subtitle { text-align: center; color: #888; margin-bottom: 2rem; font-size: 0.9rem; }
        .error-msg { color: #e74c3c; font-size: 0.875rem; margin-bottom: 1rem; text-align: center; }
        button[type="submit"] { width: 100%; }
    </style>
</head>
<body>
    <div class="login-card">
        <h1>TinyAgentOS</h1>
        <p class="subtitle">Sign in to continue</p>
        {error}
        <form method="POST" action="/auth/login">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="Enter password" required autofocus>
            <button type="submit">Sign In</button>
        </form>
    </div>
</body>
</html>
"""


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    error_html = ""
    if error:
        error_html = '<p class="error-msg">Invalid password. Please try again.</p>'
    return HTMLResponse(LOGIN_PAGE_HTML.replace("{error}", error_html))


@router.post("/login")
async def login(request: Request):
    """Sign in. Accepts JSON or form-encoded.

    JSON body: ``{username?, password}``. Returns the user profile and
    sets a session cookie.

    Form body: legacy password-only login (kept for backward compat with
    the HTML fallback page).
    """
    auth_mgr = request.app.state.auth

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        username = (body.get("username") or "").strip() or None
        password = body.get("password") or ""
        if not auth_mgr.check_password(password, username=username):
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        long_lived = bool(body.get("auto_login", False))
        token = auth_mgr.create_session(long_lived=long_lived)
        resp = JSONResponse({"ok": True, "user": auth_mgr.get_user()})
        resp.set_cookie(
            "taos_session", token, httponly=True, samesite="lax",
            max_age=auth_mgr.session_ttl_for(long_lived),
        )
        return resp

    form = await request.form()
    password = form.get("password", "")
    if not auth_mgr.check_password(password):
        return RedirectResponse("/auth/login?error=1", status_code=303)
    token = auth_mgr.create_session()
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("taos_session", token, httponly=True, samesite="lax", max_age=auth_mgr.session_ttl)
    return response


@router.post("/logout")
async def logout(request: Request):
    auth_mgr = request.app.state.auth
    token = request.cookies.get("taos_session")
    if token:
        auth_mgr.revoke_session(token)
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie("taos_session")
    return response


@router.post("/setup")
async def auth_setup(request: Request):
    """Onboard the first user. Accepts JSON or form-encoded.

    JSON body: ``{username, full_name, email, password}``. Returns the
    new user's public profile and sets a session cookie.

    Form body: legacy single-password setup (kept for backward compat).
    """
    auth_mgr = request.app.state.auth

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        if auth_mgr.is_configured():
            return JSONResponse({"error": "already configured"}, status_code=409)
        username = (body.get("username") or "").strip()
        full_name = (body.get("full_name") or "").strip()
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""
        if not username:
            return JSONResponse({"error": "username is required"}, status_code=400)
        if not password or len(password) < 4:
            return JSONResponse({"error": "password must be at least 4 characters"}, status_code=400)
        try:
            user = auth_mgr.setup_user(username, full_name, email, password)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        long_lived = bool(body.get("auto_login", True))
        token = auth_mgr.create_session(long_lived=long_lived)
        resp = JSONResponse({"ok": True, "user": user})
        resp.set_cookie(
            "taos_session", token, httponly=True, samesite="lax",
            max_age=auth_mgr.session_ttl_for(long_lived),
        )
        return resp

    # Legacy password-only form setup
    if auth_mgr.is_configured():
        return JSONResponse({"error": "Password already configured"}, status_code=400)
    form = await request.form()
    password = form.get("password", "")
    if not password:
        return JSONResponse({"error": "Password is required"}, status_code=400)
    auth_mgr.set_password(password)
    token = auth_mgr.create_session()
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("taos_session", token, httponly=True, samesite="lax", max_age=auth_mgr.session_ttl)
    return response


@router.get("/status")
async def auth_status(request: Request):
    """Single endpoint the UI calls to decide what to render.

    Returns ``{configured, authenticated, user}``. The UI uses this to
    pick between Onboarding, Login, or the desktop shell on first paint.
    """
    auth_mgr = request.app.state.auth
    configured = auth_mgr.is_configured()
    token = request.cookies.get("taos_session", "")
    authenticated = bool(token) and auth_mgr.validate_session(token)
    user = auth_mgr.get_user() if (configured and authenticated) else None
    return JSONResponse({"configured": configured, "authenticated": authenticated, "user": user})


@router.get("/me")
async def auth_me(request: Request):
    """Return the current user's profile. 401 when not signed in."""
    auth_mgr = request.app.state.auth
    token = request.cookies.get("taos_session", "")
    if not token or not auth_mgr.validate_session(token):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    user = auth_mgr.get_user()
    if user is None:
        return JSONResponse({"error": "no user configured"}, status_code=404)
    return JSONResponse({"user": user})
