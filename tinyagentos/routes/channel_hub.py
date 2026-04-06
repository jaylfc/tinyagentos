from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/channel-hub", tags=["channel-hub"])


@router.get("/status")
async def channel_hub_status(request: Request):
    """Show active connectors, adapters, and message counts."""
    router_obj = request.app.state.channel_hub_router
    adapter_mgr = request.app.state.adapter_manager
    connectors = getattr(request.app.state, "channel_hub_connectors", {})

    return {
        "connectors": {
            name: {"platform": c.__class__.__name__.replace("Connector", "").lower(), "agent": c.agent_name}
            for name, c in connectors.items()
        },
        "adapters": {
            name: {"port": port}
            for name, port in router_obj._agent_ports.items()
        },
        "channel_assignments": dict(router_obj._channel_assignments),
    }


@router.post("/connect")
async def connect_bot(request: Request):
    """Connect a Telegram/Discord bot. Body: {platform, bot_token_secret, agent_name}."""
    body = await request.json()
    platform = body.get("platform", "")
    bot_token_secret = body.get("bot_token_secret", "")
    agent_name = body.get("agent_name", "")

    if not platform or not bot_token_secret or not agent_name:
        return JSONResponse({"error": "platform, bot_token_secret, and agent_name are required"}, status_code=400)

    # Resolve the bot token from secrets store
    secrets_store = request.app.state.secrets
    secret_record = await secrets_store.get(bot_token_secret)
    if not secret_record:
        return JSONResponse({"error": f"Secret '{bot_token_secret}' not found"}, status_code=404)
    bot_token = secret_record.get("value", "")

    router_obj = request.app.state.channel_hub_router
    connectors = getattr(request.app.state, "channel_hub_connectors", {})

    connector_key = f"{platform}:{agent_name}"

    if platform == "telegram":
        from tinyagentos.channel_hub.telegram_connector import TelegramConnector
        connector = TelegramConnector(bot_token=bot_token, agent_name=agent_name, router=router_obj)
        router_obj.assign_channel(platform, bot_token_secret, agent_name)
        await connector.start()
        connectors[connector_key] = connector
        request.app.state.channel_hub_connectors = connectors
        return {"status": "connected", "platform": platform, "agent_name": agent_name}
    else:
        return JSONResponse({"error": f"Platform '{platform}' not yet supported"}, status_code=400)


@router.post("/disconnect")
async def disconnect_bot(request: Request):
    """Disconnect a bot. Body: {platform, agent_name}."""
    body = await request.json()
    platform = body.get("platform", "")
    agent_name = body.get("agent_name", "")

    connectors = getattr(request.app.state, "channel_hub_connectors", {})
    connector_key = f"{platform}:{agent_name}"

    connector = connectors.pop(connector_key, None)
    if connector:
        await connector.stop()
        request.app.state.channel_hub_connectors = connectors
        return {"status": "disconnected", "platform": platform, "agent_name": agent_name}
    else:
        return JSONResponse({"error": "Connector not found"}, status_code=404)


@router.get("/adapters")
async def list_adapters(request: Request):
    """List running adapters."""
    router_obj = request.app.state.channel_hub_router
    adapter_mgr = request.app.state.adapter_manager

    adapters = []
    for name, port in router_obj._agent_ports.items():
        running = name in adapter_mgr._processes and adapter_mgr._processes[name].poll() is None
        adapters.append({
            "agent_name": name,
            "port": port,
            "running": running,
        })

    return {"adapters": adapters}
