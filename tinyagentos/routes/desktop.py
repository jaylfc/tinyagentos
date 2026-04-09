from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pathlib import Path
import httpx

router = APIRouter()

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SPA_DIR = PROJECT_DIR / "static" / "desktop"


@router.get("/api/desktop/settings")
async def get_settings(request: Request):
    store = request.app.state.desktop_settings
    settings = await store.get_settings("user")
    return JSONResponse(settings)


@router.put("/api/desktop/settings")
async def update_settings(request: Request):
    store = request.app.state.desktop_settings
    body = await request.json()
    await store.update_settings("user", body)
    return JSONResponse({"ok": True})


@router.get("/api/desktop/dock")
async def get_dock(request: Request):
    store = request.app.state.desktop_settings
    dock = await store.get_dock("user")
    return JSONResponse(dock)


@router.put("/api/desktop/dock")
async def update_dock(request: Request):
    store = request.app.state.desktop_settings
    body = await request.json()
    await store.update_dock("user", body)
    return JSONResponse({"ok": True})


@router.get("/api/desktop/windows")
async def get_windows(request: Request):
    store = request.app.state.desktop_settings
    windows = await store.get_windows("user")
    return JSONResponse(windows)


@router.put("/api/desktop/windows")
async def save_windows(request: Request):
    store = request.app.state.desktop_settings
    body = await request.json()
    await store.save_windows("user", body.get("positions", []))
    return JSONResponse({"ok": True})


@router.get("/api/desktop/proxy")
async def browser_proxy(url: str):
    """Proxy web pages for the desktop browser app, stripping X-Frame-Options."""
    if not url.startswith(("http://", "https://")):
        return JSONResponse({"error": "Invalid URL"}, status_code=400)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; TinyAgentOS)"})
            # Strip headers that block iframe embedding
            headers = dict(resp.headers)
            for h in ("x-frame-options", "content-security-policy", "content-security-policy-report-only"):
                headers.pop(h, None)
            return StreamingResponse(
                content=iter([resp.content]),
                status_code=resp.status_code,
                headers=headers,
                media_type=resp.headers.get("content-type", "text/html"),
            )
    except httpx.ConnectError:
        return JSONResponse({"error": f"Cannot connect to {url}"}, status_code=502)
    except httpx.TimeoutException:
        return JSONResponse({"error": "Request timed out"}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/desktop")
async def serve_spa_root():
    """Serve the SPA index.html at /desktop."""
    index = SPA_DIR / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return JSONResponse({"error": "Desktop shell not built. Run: cd desktop && npm run build"}, status_code=404)


@router.get("/desktop/{rest:path}")
async def serve_spa(rest: str = ""):
    """Serve static assets from the SPA build, fall back to index.html for client-side routes."""
    # Try to serve the exact file first (CSS, JS, images)
    file_path = SPA_DIR / rest
    if file_path.is_file() and SPA_DIR in file_path.resolve().parents:
        return FileResponse(file_path)
    # Fall back to index.html for client-side routing
    index = SPA_DIR / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return JSONResponse({"error": "Desktop shell not built. Run: cd desktop && npm run build"}, status_code=404)
