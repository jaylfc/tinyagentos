"""Route-level tests for /api/github/* endpoints.

Uses a minimal FastAPI app with only the GitHub router mounted so these tests
run fast without the full create_app initialisation.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tinyagentos.routes.github import router as github_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_response(data, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data)
    resp.text = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
    resp.raise_for_status = MagicMock()
    return resp


def _make_http_client(*side_effects):
    """Return a mock httpx.AsyncClient whose .get() yields responses in order."""
    client = MagicMock()
    client.get = AsyncMock(side_effect=list(side_effects))
    return client


def _build_app(token: str | None = "test-token", http_client=None):
    """Build a minimal FastAPI app with the GitHub router and mock state."""
    app = FastAPI()
    app.include_router(github_router)

    mock_secrets = MagicMock()
    if token:
        mock_secrets.get = AsyncMock(return_value={"value": token})
    else:
        mock_secrets.get = AsyncMock(return_value=None)

    app.state.secrets = mock_secrets
    app.state.http_client = http_client or MagicMock()
    return app


@pytest_asyncio.fixture
async def no_token_client():
    app = _build_app(token=None)
    # Also make gh CLI fail
    transport = ASGITransport(app=app)
    with patch("tinyagentos.routes.github.asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


# ---------------------------------------------------------------------------
# Auth status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_status_with_token():
    app = _build_app(token="my-github-token")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True


@pytest.mark.asyncio
async def test_auth_status_no_token(no_token_client):
    resp = await no_token_client.get("/api/github/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False


# ---------------------------------------------------------------------------
# Starred
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_starred_returns_repos():
    starred_data = [
        {
            "name": "repo1",
            "owner": {"login": "alice"},
            "full_name": "alice/repo1",
            "description": "Repo 1",
            "stargazers_count": 10,
            "language": "Python",
            "updated_at": "2026-01-01T00:00:00Z",
            "html_url": "https://github.com/alice/repo1",
        }
    ]
    http_client = _make_http_client(_make_response(starred_data))
    app = _build_app(http_client=http_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/starred?page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "repos" in data
    assert len(data["repos"]) == 1
    assert data["repos"][0]["name"] == "repo1"
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_starred_no_token_returns_401(no_token_client):
    resp = await no_token_client.get("/api/github/starred")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notifications_returns_list():
    notif_data = [
        {
            "id": "1",
            "reason": "mention",
            "unread": True,
            "updated_at": "2026-01-01T00:00:00Z",
            "subject": {"type": "Issue", "title": "Bug", "url": "https://api.github.com/repos/owner/repo/issues/1"},
            "repository": {"full_name": "owner/repo", "html_url": "https://github.com/owner/repo"},
        }
    ]
    http_client = _make_http_client(_make_response(notif_data))
    app = _build_app(http_client=http_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert "notifications" in data
    assert data["unread_count"] == 1
    assert data["notifications"][0]["title"] == "Bug"
    assert data["notifications"][0]["repo"] == "owner/repo"


@pytest.mark.asyncio
async def test_notifications_no_token_returns_401(no_token_client):
    resp = await no_token_client.get("/api/github/notifications")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Repo metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repo_returns_metadata():
    meta_data = {
        "name": "myrepo",
        "owner": {"login": "bob"},
        "description": "My repo",
        "stargazers_count": 100,
        "forks_count": 5,
        "language": "Go",
        "license": {"name": "MIT"},
        "topics": ["tool"],
        "updated_at": "2026-02-01T00:00:00Z",
    }
    readme_resp = MagicMock()
    readme_resp.status_code = 200
    readme_resp.text = "# MyRepo"
    readme_resp.raise_for_status = MagicMock()

    http_client = _make_http_client(_make_response(meta_data), readme_resp)
    app = _build_app(http_client=http_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/repo/bob/myrepo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "myrepo"
    assert data["stars"] == 100
    assert data["readme_content"] == "# MyRepo"


@pytest.mark.asyncio
async def test_repo_no_token_returns_401(no_token_client):
    resp = await no_token_client.get("/api/github/repo/owner/repo")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Issues list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_issues_list():
    issues_data = [
        {
            "number": 1,
            "title": "First issue",
            "state": "open",
            "user": {"login": "carol"},
            "labels": [{"name": "bug"}],
            "comments": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
    ]
    http_client = _make_http_client(_make_response(issues_data))
    app = _build_app(http_client=http_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/repo/owner/repo/issues?state=open&page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "issues" in data
    assert len(data["issues"]) == 1
    assert data["issues"][0]["title"] == "First issue"
    assert data["issues"][0]["labels"] == ["bug"]


@pytest.mark.asyncio
async def test_issues_list_no_token_returns_401(no_token_client):
    resp = await no_token_client.get("/api/github/repo/owner/repo/issues")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Single issue / PR
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_issue():
    issue_data = {
        "number": 42,
        "title": "Fix crash",
        "state": "closed",
        "user": {"login": "dave"},
        "body": "Details here.",
        "labels": [],
        "created_at": "2026-01-15T00:00:00Z",
    }
    http_client = _make_http_client(
        _make_response(issue_data),
        _make_response([]),
    )
    app = _build_app(http_client=http_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/repo/owner/repo/issues/42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["number"] == 42
    assert data["title"] == "Fix crash"
    assert data["comments"] == []


@pytest.mark.asyncio
async def test_single_issue_no_token_returns_401(no_token_client):
    resp = await no_token_client.get("/api/github/repo/owner/repo/issues/1")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_releases_list():
    releases_data = [
        {
            "tag_name": "v1.0.0",
            "name": "First release",
            "body": "Release notes.",
            "author": {"login": "eve"},
            "published_at": "2026-01-01T00:00:00Z",
            "assets": [],
            "prerelease": False,
        }
    ]
    http_client = _make_http_client(_make_response(releases_data))
    app = _build_app(http_client=http_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/repo/owner/repo/releases")
    assert resp.status_code == 200
    data = resp.json()
    assert "releases" in data
    assert len(data["releases"]) == 1
    assert data["releases"][0]["tag"] == "v1.0.0"
    assert data["releases"][0]["prerelease"] is False


@pytest.mark.asyncio
async def test_releases_no_token_returns_401(no_token_client):
    resp = await no_token_client.get("/api/github/repo/owner/repo/releases")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repo_upstream_error_returns_500():
    http_client = MagicMock()
    exc = Exception("GitHub API unavailable")
    http_client.get = AsyncMock(side_effect=exc)
    app = _build_app(http_client=http_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/github/repo/owner/repo")
    assert resp.status_code == 500
    data = resp.json()
    assert "error" in data
