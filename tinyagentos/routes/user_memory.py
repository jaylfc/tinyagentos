from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

USER_ID = "user"  # Single-user for now


def _store(request: Request):
    return request.app.state.user_memory


@router.get("/api/user-memory/stats")
async def get_stats(request: Request):
    stats = await _store(request).get_stats(USER_ID)
    return JSONResponse(stats)


@router.get("/api/user-memory/settings")
async def get_settings(request: Request):
    settings = await _store(request).get_settings(USER_ID)
    return JSONResponse(settings)


@router.put("/api/user-memory/settings")
async def update_settings(request: Request):
    body = await request.json()
    await _store(request).update_settings(USER_ID, body)
    return JSONResponse({"ok": True})


@router.get("/api/user-memory/search")
async def search(request: Request, q: str, collection: str | None = None, limit: int = 20):
    results = await _store(request).search(USER_ID, q, collection, limit)
    return JSONResponse({"results": results, "query": q})


@router.get("/api/user-memory/browse")
async def browse(request: Request, collection: str | None = None, limit: int = 50):
    chunks = await _store(request).browse(USER_ID, collection, limit)
    return JSONResponse({"chunks": chunks})


@router.post("/api/user-memory/save")
async def save(request: Request):
    body = await request.json()
    content = body.get("content", "")
    title = body.get("title", "")
    collection = body.get("collection", "snippets")
    metadata = body.get("metadata", {})
    if not content:
        return JSONResponse({"error": "content required"}, status_code=400)
    h = await _store(request).save_chunk(USER_ID, content, title, collection, metadata)
    return JSONResponse({"ok": True, "hash": h})


@router.delete("/api/user-memory/chunk/{chunk_hash}")
async def delete_chunk(request: Request, chunk_hash: str):
    deleted = await _store(request).delete_chunk(USER_ID, chunk_hash)
    return JSONResponse({"ok": deleted})


@router.get("/api/user-memory/collections")
async def list_collections(request: Request):
    stats = await _store(request).get_stats(USER_ID)
    return JSONResponse({"collections": list(stats["collections"].keys())})
