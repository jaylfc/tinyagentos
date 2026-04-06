import pytest
from tinyagentos.agent_templates import list_templates, get_template, CATEGORIES, TEMPLATES, EXTERNAL_SOURCES


class TestAgentTemplates:
    def test_list_all_templates(self):
        templates = list_templates()
        assert len(templates) == 12
        assert all("id" in t for t in templates)

    def test_list_by_category(self):
        dev_templates = list_templates(category="development")
        assert len(dev_templates) >= 1
        assert all(t["category"] == "development" for t in dev_templates)

    def test_get_template(self):
        tmpl = get_template("research-assistant")
        assert tmpl is not None
        assert tmpl["name"] == "Research Assistant"
        assert tmpl["framework"] == "smolagents"

    def test_get_nonexistent(self):
        assert get_template("nonexistent") is None

    def test_categories_list(self):
        assert "development" in CATEGORIES
        assert "research" in CATEGORIES

    def test_all_templates_have_required_fields(self):
        required = {"id", "name", "category", "description", "framework", "model", "system_prompt", "color"}
        for tmpl in TEMPLATES:
            missing = required - set(tmpl.keys())
            assert not missing, f"Template '{tmpl['id']}' missing fields: {missing}"


class TestTemplateRoutes:
    @pytest.mark.asyncio
    async def test_templates_page(self, client):
        resp = await client.get("/templates")
        assert resp.status_code == 200
        assert b"Agent Templates" in resp.content

    @pytest.mark.asyncio
    async def test_list_templates_api(self, client):
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert "categories" in data
        assert len(data["templates"]) == 12

    @pytest.mark.asyncio
    async def test_filter_by_category(self, client):
        resp = await client.get("/api/templates?category=development")
        assert resp.status_code == 200
        templates = resp.json()["templates"]
        assert all(t["category"] == "development" for t in templates)

    @pytest.mark.asyncio
    async def test_get_template_api(self, client):
        resp = await client.get("/api/templates/research-assistant")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Research Assistant"

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, client):
        resp = await client.get("/api/templates/nonexistent")
        assert resp.status_code == 404


class TestExternalSources:
    def test_external_sources_defined(self):
        from tinyagentos.agent_templates import EXTERNAL_SOURCES
        assert len(EXTERNAL_SOURCES) == 2
        ids = [s["id"] for s in EXTERNAL_SOURCES]
        assert "awesome-openclaw" in ids
        assert "system-prompt-library" in ids

    @pytest.mark.asyncio
    async def test_list_sources_api(self, client):
        resp = await client.get("/api/templates/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert len(data["sources"]) == 2

    @pytest.mark.asyncio
    async def test_external_index_unknown_source(self, client):
        resp = await client.get("/api/templates/external/nonexistent")
        assert resp.status_code == 200
        assert resp.json()["templates"] == []

    @pytest.mark.asyncio
    async def test_fetch_external_no_path(self, client):
        resp = await client.get("/api/templates/external/awesome-openclaw/fetch")
        assert resp.status_code == 400
