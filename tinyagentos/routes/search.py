from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/search")
async def global_search(request: Request, q: str = "", limit: int = 5):
    """Search across all platform data."""
    if not q or len(q) < 2:
        return {"results": [], "query": q}

    query = q.lower()
    results = []

    # 1. Agents
    config = request.app.state.config
    for agent in config.agents:
        if query in agent.get("name", "").lower():
            results.append({
                "type": "agent",
                "title": agent["name"],
                "subtitle": f"Agent — {agent.get('status', 'configured')}",
                "url": f"/workspace/{agent['name']}",
            })

    # 2. Apps from catalog
    registry = request.app.state.registry
    for app in registry.list_available():
        if query in app.name.lower() or query in (app.description or "").lower():
            results.append({
                "type": "app",
                "title": app.name,
                "subtitle": f"App — {app.type}",
                "url": "/store",
            })
            if len(results) >= limit * 3:
                break

    # 3. Messages
    try:
        msg_store = request.app.state.agent_messages
        messages = await msg_store.search(q, limit=limit)
        for msg in messages:
            preview = msg["message"][:80] + ("..." if len(msg["message"]) > 80 else "")
            results.append({
                "type": "message",
                "title": f"{msg['from']} → {msg['to']}",
                "subtitle": preview,
                "url": f"/workspace/{msg['from']}/messages",
            })
    except Exception:
        pass

    # 4. Shared folders
    try:
        folders = await request.app.state.shared_folders.list_folders()
        for folder in folders:
            if query in folder.get("name", "").lower() or query in folder.get("description", "").lower():
                results.append({
                    "type": "folder",
                    "title": folder["name"],
                    "subtitle": f"Shared Folder — {folder.get('description', '')}",
                    "url": "/shared-folders",
                })
    except Exception:
        pass

    # Deduplicate and limit
    seen = set()
    unique = []
    for r in results:
        key = (r["type"], r["title"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
        if len(unique) >= limit * 2:
            break

    return {"results": unique[:limit * 2], "query": q, "total": len(unique)}
