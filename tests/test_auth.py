from __future__ import annotations

import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tinyagentos.auth import AuthManager, hash_password, verify_password


# --- Unit tests for password hashing ---

class TestPasswordHashing:
    def test_hash_produces_salt_and_hash(self):
        result = hash_password("secret")
        parts = result.split(":")
        assert len(parts) == 2
        assert len(parts[0]) == 32  # 16 bytes hex
        assert len(parts[1]) == 64  # sha256 hex

    def test_hash_with_explicit_salt(self):
        result = hash_password("secret", "abcd1234")
        assert result.startswith("abcd1234:")

    def test_verify_correct_password(self):
        stored = hash_password("mypass")
        assert verify_password("mypass", stored) is True

    def test_verify_wrong_password(self):
        stored = hash_password("mypass")
        assert verify_password("wrong", stored) is False

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("alpha", "same_salt")
        h2 = hash_password("beta", "same_salt")
        assert h1 != h2


# --- Unit tests for AuthManager ---

class TestAuthManager:
    def test_not_configured_initially(self, tmp_path):
        mgr = AuthManager(tmp_path)
        assert mgr.is_configured() is False

    def test_configured_after_set_password(self, tmp_path):
        mgr = AuthManager(tmp_path)
        mgr.set_password("test123")
        assert mgr.is_configured() is True

    def test_check_password_correct(self, tmp_path):
        mgr = AuthManager(tmp_path)
        mgr.set_password("test123")
        assert mgr.check_password("test123") is True

    def test_check_password_wrong(self, tmp_path):
        mgr = AuthManager(tmp_path)
        mgr.set_password("test123")
        assert mgr.check_password("wrong") is False

    def test_check_password_not_configured(self, tmp_path):
        mgr = AuthManager(tmp_path)
        assert mgr.check_password("anything") is False

    def test_create_and_validate_session(self, tmp_path):
        mgr = AuthManager(tmp_path)
        token = mgr.create_session()
        assert mgr.validate_session(token) is True

    def test_validate_invalid_token(self, tmp_path):
        mgr = AuthManager(tmp_path)
        assert mgr.validate_session("bogus") is False

    def test_revoke_session(self, tmp_path):
        mgr = AuthManager(tmp_path)
        token = mgr.create_session()
        mgr.revoke_session(token)
        assert mgr.validate_session(token) is False

    def test_revoke_nonexistent_session(self, tmp_path):
        mgr = AuthManager(tmp_path)
        mgr.revoke_session("nonexistent")  # should not raise

    def test_expired_session(self, tmp_path):
        mgr = AuthManager(tmp_path)
        token = mgr.create_session()
        # Manually expire it
        mgr._sessions[token] = time.time() - 1
        assert mgr.validate_session(token) is False
        # Should also be cleaned up
        assert token not in mgr._sessions

    def test_cleanup_sessions(self, tmp_path):
        mgr = AuthManager(tmp_path)
        t1 = mgr.create_session()
        t2 = mgr.create_session()
        # Expire t1
        mgr._sessions[t1] = time.time() - 1
        mgr.cleanup_sessions()
        assert t1 not in mgr._sessions
        assert t2 in mgr._sessions


# --- Integration tests for routes ---

@pytest_asyncio.fixture
async def auth_client(app):
    """Client for auth tests — initialises required stores."""
    store = app.state.metrics
    if store._db is not None:
        await store.close()
    await store.init()
    notif_store = app.state.notifications
    if notif_store._db is not None:
        await notif_store.close()
    await notif_store.init()
    await app.state.qmd_client.init()
    secrets_store = app.state.secrets
    if secrets_store._db is not None:
        await secrets_store.close()
    await secrets_store.init()
    scheduler = app.state.scheduler
    if scheduler._db is not None:
        await scheduler.close()
    await scheduler.init()
    channel_store = app.state.channels
    if channel_store._db is not None:
        await channel_store.close()
    await channel_store.init()
    relationship_mgr = app.state.relationships
    if relationship_mgr._db is not None:
        await relationship_mgr.close()
    await relationship_mgr.init()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await relationship_mgr.close()
    await channel_store.close()
    await scheduler.close()
    await secrets_store.close()
    await notif_store.close()
    await store.close()
    await app.state.qmd_client.close()
    await app.state.http_client.aclose()


class TestAuthRoutes:
    @pytest.mark.asyncio
    async def test_login_page_accessible(self, auth_client):
        resp = await auth_client.get("/auth/login")
        assert resp.status_code == 200
        assert "Sign In" in resp.text

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, app, auth_client):
        app.state.auth.set_password("correct")
        resp = await auth_client.post(
            "/auth/login",
            data={"password": "wrong"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "error" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_login_correct_password(self, app, auth_client):
        app.state.auth.set_password("correct")
        resp = await auth_client.post(
            "/auth/login",
            data={"password": "correct"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "taos_session" in resp.headers.get("set-cookie", "")

    @pytest.mark.asyncio
    async def test_logout_clears_session(self, app, auth_client):
        app.state.auth.set_password("pass")
        # Login first
        resp = await auth_client.post(
            "/auth/login",
            data={"password": "pass"},
            follow_redirects=False,
        )
        cookies = resp.cookies
        # Logout
        resp = await auth_client.post("/auth/logout", cookies=cookies, follow_redirects=False)
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_auth_setup_sets_password(self, app, auth_client):
        assert app.state.auth.is_configured() is False
        resp = await auth_client.post(
            "/auth/setup",
            data={"password": "newpass"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert app.state.auth.is_configured() is True
        assert app.state.auth.check_password("newpass") is True

    @pytest.mark.asyncio
    async def test_auth_setup_rejects_if_already_configured(self, app, auth_client):
        app.state.auth.set_password("existing")
        resp = await auth_client.post(
            "/auth/setup",
            data={"password": "newpass"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_auth_setup_rejects_empty_password(self, app, auth_client):
        resp = await auth_client.post(
            "/auth/setup",
            data={"password": ""},
        )
        assert resp.status_code == 400


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_no_auth_when_not_configured(self, auth_client):
        """Before onboarding, /api/* must hard-fail so the SPA forces setup.

        Exempt paths (health, cluster heartbeat, /static/, /desktop, /auth/*)
        still pass through; everything else returns 401 with
        needs_onboarding so the client routes to OnboardingScreen instead
        of acting on stale state.
        """
        # Exempt path still works
        resp = await auth_client.get("/api/health")
        assert resp.status_code == 200

        # Non-exempt /api/* now requires onboarding
        resp = await auth_client.get("/api/system")
        assert resp.status_code == 401
        assert resp.json().get("needs_onboarding") is True

    @pytest.mark.asyncio
    async def test_protected_route_returns_401(self, app, auth_client):
        """With auth configured, API routes should return 401 without session."""
        app.state.auth.set_password("secret")
        resp = await auth_client.get("/api/system")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_health_exempt(self, app, auth_client):
        """Health endpoint should be accessible without auth."""
        app.state.auth.set_password("secret")
        resp = await auth_client.get("/api/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_login_page_exempt(self, app, auth_client):
        """Login page should be accessible without auth."""
        app.state.auth.set_password("secret")
        resp = await auth_client.get("/auth/login")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_static_exempt(self, app, auth_client):
        """Static files should be accessible without auth (404 is fine, not 401)."""
        app.state.auth.set_password("secret")
        resp = await auth_client.get("/static/app.css")
        # Should not be 401 — could be 200 or 404 depending on file existence
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_authenticated_request_passes(self, app, auth_client):
        """With valid session cookie, protected routes should work."""
        app.state.auth.set_password("secret")
        # Login to get session
        resp = await auth_client.post(
            "/auth/login",
            data={"password": "secret"},
            follow_redirects=False,
        )
        cookies = resp.cookies
        # Access protected route with session
        resp = await auth_client.get("/api/system", cookies=cookies)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_html_request_redirects_to_login(self, app, auth_client):
        """Browser requests should redirect to login page."""
        app.state.auth.set_password("secret")
        resp = await auth_client.get(
            "/",
            headers={"accept": "text/html,application/xhtml+xml"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_cluster_worker_exempt(self, app, auth_client):
        """Worker registration should be exempt from auth."""
        app.state.auth.set_password("secret")
        resp = await auth_client.post(
            "/api/cluster/workers",
            json={"worker_id": "test", "capabilities": {}},
        )
        # Should not be 401 (may be 422 or other depending on validation)
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_cluster_heartbeat_exempt(self, app, auth_client):
        """Worker heartbeat should be exempt from auth."""
        app.state.auth.set_password("secret")
        resp = await auth_client.post(
            "/api/cluster/heartbeat",
            json={"worker_id": "test"},
        )
        assert resp.status_code != 401
