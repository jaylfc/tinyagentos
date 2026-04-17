import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
class TestProviderAPI:
    async def test_list_providers(self, client):
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_test_connection_missing_url(self, client):
        resp = await client.post("/api/providers/test", json={"type": "ollama"})
        assert resp.status_code == 422  # Pydantic validation requires url field

    async def test_add_provider(self, client):
        resp = await client.post("/api/providers", json={
            "name": "test-ollama", "type": "ollama",
            "url": "http://localhost:11434", "priority": 1,
        })
        assert resp.status_code == 200

    async def test_delete_provider(self, client):
        # Add then delete
        await client.post("/api/providers", json={
            "name": "to-delete", "type": "ollama",
            "url": "http://localhost:11434", "priority": 5,
        })
        resp = await client.delete("/api/providers/to-delete")
        assert resp.status_code == 200

    async def test_add_duplicate_provider(self, client):
        await client.post("/api/providers", json={
            "name": "dup-test", "type": "ollama",
            "url": "http://localhost:11434", "priority": 1,
        })
        resp = await client.post("/api/providers", json={
            "name": "dup-test", "type": "ollama",
            "url": "http://localhost:11434", "priority": 2,
        })
        assert resp.status_code == 409

    async def test_add_kilocode_autofills_url_and_models(self, client, app):
        """Kilocode add form only collects name + api_key — server must fill
        the canonical base URL and a routable model list (from live probe,
        falling back to the seed) so generate_litellm_config registers at
        least one routable model."""
        # Stub the probe to a deterministic empty result so the test
        # doesn't touch the real kilocode endpoint; the seed list then
        # kicks in, which is the guarantee we care about.
        with patch(
            "tinyagentos.routes.providers._discover_provider_models",
            new=AsyncMock(return_value=[]),
        ):
            resp = await client.post("/api/providers", json={
                "name": "kilo-auto-test",
                "type": "kilocode",
                "api_key_secret": "provider-kilo-auto-test-key",
            })
            assert resp.status_code == 200

        stored = next(
            b for b in app.state.config.backends
            if b.get("name") == "kilo-auto-test"
        )
        assert stored["url"] == "https://api.kilo.ai/api/gateway"
        assert stored.get("models"), "models list should be auto-populated"
        model_ids = [
            m.get("id") if isinstance(m, dict) else m for m in stored["models"]
        ]
        assert "kilo-auto/free" in model_ids

    async def test_add_kilocode_respects_caller_supplied_url_and_models(self, client, app):
        """Caller-supplied url/models override the autofill defaults."""
        resp = await client.post("/api/providers", json={
            "name": "kilo-custom",
            "type": "kilocode",
            "url": "https://example.test/api",
            "models": [{"id": "custom/model-a"}],
            "api_key_secret": "provider-kilo-custom-key",
        })
        assert resp.status_code == 200
        stored = next(
            b for b in app.state.config.backends
            if b.get("name") == "kilo-custom"
        )
        assert stored["url"] == "https://example.test/api"
        model_ids = [
            m.get("id") if isinstance(m, dict) else m for m in stored["models"]
        ]
        assert model_ids == ["custom/model-a"]

    async def test_add_provider_discovers_models_when_empty(self, client, app):
        """Empty models list on a cloud provider triggers a server-side
        probe of ``{url}/models``. Works for any provider type that
        returns an OpenAI-shaped payload — no per-type branching."""
        fake_ids = ["disco/model-x", "disco/model-y"]
        with patch(
            "tinyagentos.routes.providers._discover_provider_models",
            new=AsyncMock(return_value=[{"id": mid} for mid in fake_ids]),
        ):
            resp = await client.post("/api/providers", json={
                "name": "disco",
                "type": "openrouter",
                "api_key_secret": "provider-disco-key",
            })
            assert resp.status_code == 200

        # Assert against stored config (list-providers live-probes and
        # replaces `models`, which would mask what add_provider actually
        # persisted).
        stored_entry = next(
            b for b in app.state.config.backends if b.get("name") == "disco"
        )
        assert stored_entry["url"] == "https://openrouter.ai/api/v1"
        stored_ids = [
            m.get("id") if isinstance(m, dict) else m
            for m in stored_entry["models"]
        ]
        assert stored_ids == fake_ids

    async def test_add_provider_discovery_failure_keeps_entry(self, client, app):
        """A failing probe must NOT block saving the provider — we still
        persist the entry, log a warning, and let the user refine models
        by hand. kilocode falls back to the seed list; a cloud type with
        no seed saves with an empty models list."""
        with patch(
            "tinyagentos.routes.providers._discover_provider_models",
            new=AsyncMock(return_value=[]),
        ):
            resp = await client.post("/api/providers", json={
                "name": "offline-openrouter",
                "type": "openrouter",
                "api_key_secret": "provider-offline-key",
            })
            assert resp.status_code == 200

            resp_kilo = await client.post("/api/providers", json={
                "name": "offline-kilo",
                "type": "kilocode",
                "api_key_secret": "provider-offline-kilo-key",
            })
            assert resp_kilo.status_code == 200

        or_entry = next(
            b for b in app.state.config.backends
            if b.get("name") == "offline-openrouter"
        )
        assert or_entry["url"] == "https://openrouter.ai/api/v1"
        # openrouter has no default seed — empty/missing models is fine;
        # generate_litellm_config will log the incomplete-backend warning.
        assert not or_entry.get("models")

        kilo_entry = next(
            b for b in app.state.config.backends
            if b.get("name") == "offline-kilo"
        )
        kilo_ids = [
            m.get("id") if isinstance(m, dict) else m
            for m in kilo_entry["models"]
        ]
        assert "kilo-auto/free" in kilo_ids
