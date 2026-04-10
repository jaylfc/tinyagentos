from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx

router = APIRouter()


@router.post("/api/games/chess/move")
async def chess_move(request: Request):
    """Ask an agent to pick a chess move.

    Request: {agent_name, fen, legal_moves: [...], history: [...]}
    Response: {move, commentary}
    """
    body = await request.json()
    agent_name = body.get("agent_name")
    fen = body.get("fen", "")
    legal_moves = body.get("legal_moves", [])
    history = body.get("history", [])

    if not agent_name or not legal_moves:
        return JSONResponse({"error": "Missing agent_name or legal_moves"}, status_code=400)

    # Build prompt for the agent
    prompt = f"""You are playing chess. Current position (FEN): {fen}

Move history: {' '.join(history) if history else 'Game start'}

Your legal moves: {', '.join(legal_moves)}

Pick your next move. Respond with ONLY the move in UCI format (e.g. e2e4) from the legal moves list. No explanation."""

    # Resolve the agent's adapter URL via the channel hub router
    url = None
    try:
        hub_router = getattr(request.app.state, "channel_hub_router", None)
        if hub_router is not None:
            port = None
            if hasattr(hub_router, "get_adapter_port"):
                port = hub_router.get_adapter_port(agent_name)
            if port:
                url = f"http://localhost:{port}"
        # Fallback: some deployments expose an adapter manager with get_adapter_url
        if url is None:
            adapter_mgr = getattr(request.app.state, "channel_hub", None)
            if adapter_mgr and hasattr(adapter_mgr, "get_adapter_url"):
                url = adapter_mgr.get_adapter_url(agent_name)
    except Exception:
        url = None

    if not url:
        # Fallback: random legal move
        import random
        return JSONResponse({
            "move": random.choice(legal_moves),
            "commentary": f"(Agent '{agent_name}' not reachable — random move)"
        })

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{url}/message", json={"text": prompt, "from_name": "Chess"})
            data = resp.json()
            response_text = (data.get("content") or data.get("text") or "").strip()

            # Find a legal move in the response
            for move in legal_moves:
                if move in response_text:
                    return JSONResponse({"move": move, "commentary": response_text})

            # No valid move found, return random
            import random
            return JSONResponse({
                "move": random.choice(legal_moves),
                "commentary": f"Agent returned: {response_text[:100]}"
            })
    except Exception as e:
        import random
        return JSONResponse({
            "move": random.choice(legal_moves),
            "commentary": f"Error: {str(e)[:100]}"
        })
