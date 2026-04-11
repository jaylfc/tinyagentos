import pytest

from tinyagentos.adapters import list_frameworks

VALID_STATUSES = {"tested", "beta", "experimental", "broken"}


@pytest.mark.asyncio
async def test_frameworks_endpoint_returns_list(client):
    resp = await client.get("/api/frameworks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_frameworks_each_entry_has_required_fields(client):
    resp = await client.get("/api/frameworks")
    assert resp.status_code == 200
    for entry in resp.json():
        assert "id" in entry, f"missing id in {entry}"
        assert "name" in entry, f"missing name in {entry}"
        assert "description" in entry, f"missing description in {entry}"
        assert "verification_status" in entry, f"missing verification_status in {entry}"


@pytest.mark.asyncio
async def test_frameworks_count_matches_registry(client):
    resp = await client.get("/api/frameworks")
    assert resp.status_code == 200
    assert len(resp.json()) == len(list_frameworks())


@pytest.mark.asyncio
async def test_frameworks_all_statuses_are_valid(client):
    resp = await client.get("/api/frameworks")
    assert resp.status_code == 200
    for entry in resp.json():
        assert entry["verification_status"] in VALID_STATUSES, (
            f"{entry['id']} has unknown status {entry['verification_status']!r}"
        )


@pytest.mark.asyncio
async def test_frameworks_at_least_one_tested(client):
    resp = await client.get("/api/frameworks")
    assert resp.status_code == 200
    tested = [e for e in resp.json() if e["verification_status"] == "tested"]
    assert len(tested) > 0, "no tested frameworks found — wizard would show nothing by default"


@pytest.mark.asyncio
async def test_frameworks_known_adapters_present(client):
    resp = await client.get("/api/frameworks")
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    for expected in ("smolagents", "generic", "hermes", "openclaw", "langroid"):
        assert expected in ids, f"expected adapter {expected!r} missing from response"
