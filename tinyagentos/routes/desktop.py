from __future__ import annotations
import re
from urllib.parse import urljoin, quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
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


@router.get("/api/desktop/widgets")
async def get_widgets(request: Request):
    store = request.app.state.desktop_settings
    widgets = await store.get_widgets("user")
    return JSONResponse(widgets)


@router.put("/api/desktop/widgets")
async def save_widgets(request: Request):
    store = request.app.state.desktop_settings
    body = await request.json()
    widgets = body.get("widgets", [])
    await store.save_widgets("user", widgets)
    return JSONResponse({"ok": True})


@router.get("/api/desktop/proxy")
async def browser_proxy(url: str):
    """Proxy web pages for the browser app — strips frame headers, rewrites URLs."""
    if not url.startswith(("http://", "https://")):
        return JSONResponse({"error": "Invalid URL"}, status_code=400)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })

            content_type = resp.headers.get("content-type", "")

            # Build response headers — strip frame-blocking ones
            headers = {}
            for key, val in resp.headers.items():
                lower = key.lower()
                if lower in ("x-frame-options", "content-security-policy",
                             "content-security-policy-report-only", "content-length",
                             "transfer-encoding", "content-encoding"):
                    continue
                headers[key] = val

            # For non-HTML content (CSS, JS, images, fonts), pass through directly
            if "text/html" not in content_type:
                return StreamingResponse(
                    content=iter([resp.content]),
                    status_code=resp.status_code,
                    headers=headers,
                    media_type=content_type.split(";")[0] if content_type else "application/octet-stream",
                )

            # For HTML: rewrite URLs to go through proxy
            html = resp.text
            base_url = str(resp.url)  # final URL after redirects

            html = _rewrite_html_urls(html, base_url)

            # Add a <base> tag as fallback for URLs we miss
            if "<head" in html.lower():
                base_tag = f'<base href="/api/desktop/proxy?url={quote(base_url, safe="")}">'
                html = re.sub(r'(<head[^>]*>)', rf'\1{base_tag}', html, count=1, flags=re.IGNORECASE)

            return HTMLResponse(content=html, status_code=resp.status_code, headers=headers)

    except httpx.ConnectError:
        return JSONResponse({"error": f"Cannot connect to {url}"}, status_code=502)
    except httpx.TimeoutException:
        return JSONResponse({"error": "Request timed out"}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _rewrite_html_urls(html: str, base_url: str) -> str:
    """Rewrite src, href, action attributes to go through the proxy."""
    def rewrite_attr(match: re.Match[str]) -> str:
        prefix = match.group(1)  # e.g., 'src="' or "href='"
        url_val = match.group(2)
        suffix = match.group(3)  # closing quote

        # Skip data:, javascript:, mailto:, #anchors, and already-proxied URLs
        if url_val.startswith(("data:", "javascript:", "mailto:", "#", "/api/desktop/proxy")):
            return match.group(0)

        # Resolve relative URL against base
        absolute = urljoin(base_url, url_val)

        # Only proxy http/https URLs
        if not absolute.startswith(("http://", "https://")):
            return match.group(0)

        proxied = f"/api/desktop/proxy?url={quote(absolute, safe='')}"
        return f"{prefix}{proxied}{suffix}"

    # Match src="...", href="...", action="..." (both quote styles)
    pattern = r'''((?:src|href|action)\s*=\s*["'])([^"']*)(["'])'''
    html = re.sub(pattern, rewrite_attr, html, flags=re.IGNORECASE)

    return html


@router.get("/chat-pwa")
async def serve_chat_pwa():
    """Serve the standalone chat PWA."""
    chat_html = SPA_DIR / "chat.html"
    if chat_html.exists():
        return FileResponse(chat_html, media_type="text/html")
    return JSONResponse({"error": "Chat PWA not built"}, status_code=404)


@router.get("/chat-pwa/{rest:path}")
async def serve_chat_pwa_assets(rest: str = ""):
    """Serve assets for the chat PWA (uses same /desktop/assets base)."""
    # Assets are at /desktop/assets/... due to base path — this route just serves index
    chat_html = SPA_DIR / "chat.html"
    if chat_html.exists():
        return FileResponse(chat_html, media_type="text/html")
    return JSONResponse({"error": "Chat PWA not built"}, status_code=404)


@router.post("/api/desktop/browser/agent-command")
async def browser_agent_command(request: Request):
    """Execute a natural language command on the current page using browser-use."""
    body = await request.json()
    url = body.get("url", "")
    command = body.get("command", "")
    agent_name = body.get("agent_name")

    if not url or not command:
        return JSONResponse({"error": "url and command required"}, status_code=400)

    # Check if browser-use is installed
    try:
        import importlib.util
        if importlib.util.find_spec("browser_use") is None:
            return JSONResponse({
                "error": "browser-use not installed",
                "install": "pip install browser-use[cli]",
            }, status_code=503)
    except Exception as e:
        return JSONResponse({"error": f"Failed to check browser-use: {e}"}, status_code=500)

    # For now, return a placeholder response indicating the feature is wired but needs an agent
    return JSONResponse({
        "status": "queued",
        "url": url,
        "command": command,
        "agent_name": agent_name,
        "message": "Browser task queued. Requires an agent with browser-use capability.",
        "note": "Full integration requires browser-use plugin installation and agent configuration.",
    })


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
