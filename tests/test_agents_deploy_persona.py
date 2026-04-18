import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
class TestDeployPersonaFields:
    async def test_deploy_stores_persona_fields(self, client, app):
        app.state.archive = MagicMock(
            record=AsyncMock(), query=AsyncMock(return_value=[{"x": 1}])
        )
        resp = await client.post("/api/agents/deploy", json={
            "name": "Atlas-persona",
            "framework": "openclaw",
            "soul_md": "You are Atlas",
            "agent_md": "Always verify",
            "memory_plugin": "taosmd",
            "source_persona_id": "builtin:research",
        })
        assert resp.status_code == 200
        slug = resp.json()["name"]
        agent = next(a for a in app.state.config.agents if a["name"] == slug)
        assert agent["soul_md"] == "You are Atlas"
        assert agent["agent_md"] == "Always verify"
        assert agent["memory_plugin"] == "taosmd"
        assert agent["source_persona_id"] == "builtin:research"
        assert agent["migrated_to_v2_personas"] is True
        assert agent["display_name"] == "Atlas-persona"

    async def test_deploy_persona_fields_default_correctly(self, client, app):
        app.state.archive = MagicMock(
            record=AsyncMock(), query=AsyncMock(return_value=[{}])
        )
        resp = await client.post("/api/agents/deploy", json={"name": "DefaultAgent", "framework": "openclaw"})
        assert resp.status_code == 200
        agent = next(a for a in app.state.config.agents if a["name"] == resp.json()["name"])
        assert agent["soul_md"] == ""
        assert agent["agent_md"] == ""
        assert agent["memory_plugin"] == "taosmd"
        assert agent["source_persona_id"] is None
        assert agent["migrated_to_v2_personas"] is True

    async def test_deploy_with_save_to_library_writes_user_persona(self, client, app, tmp_path):
        from tinyagentos.user_personas import UserPersonaStore
        if not hasattr(app.state, "user_persona_store"):
            app.state.user_persona_store = UserPersonaStore(tmp_path / "p.db")
        app.state.archive = MagicMock(
            record=AsyncMock(), query=AsyncMock(return_value=[{}])
        )
        resp = await client.post("/api/agents/deploy", json={
            "name": "CustomOne",
            "framework": "openclaw",
            "soul_md": "Custom soul",
            "agent_md": "",
            "memory_plugin": "taosmd",
            "save_to_library": {"name": "My Custom", "description": "for reuse"},
        })
        assert resp.status_code == 200
        rows = app.state.user_persona_store.list()
        assert any(r["name"] == "My Custom" and r["soul_md"] == "Custom soul" for r in rows)

    async def test_deploy_without_save_to_library_does_not_create_persona(self, client, app, tmp_path):
        from tinyagentos.user_personas import UserPersonaStore
        if not hasattr(app.state, "user_persona_store"):
            app.state.user_persona_store = UserPersonaStore(tmp_path / "p.db")
        before = len(app.state.user_persona_store.list())
        app.state.archive = MagicMock(
            record=AsyncMock(), query=AsyncMock(return_value=[{}])
        )
        resp = await client.post("/api/agents/deploy", json={
            "name": "NoSave",
            "framework": "openclaw",
            "soul_md": "S",
        })
        assert resp.status_code == 200
        after = len(app.state.user_persona_store.list())
        assert after == before
