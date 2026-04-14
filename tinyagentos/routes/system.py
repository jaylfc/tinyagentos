from __future__ import annotations

import asyncio
import logging
import os
import sys

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from tinyagentos.restart_orchestrator import write_pending_restart, read_pending_restart

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/system/prepare-shutdown")
async def prepare_shutdown(request: Request):
    """Gracefully prepare all agents for shutdown. Used by systemd stop hook."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)
    report = await orchestrator.prepare("all", "system-shutdown")
    return {"status": "ready", "report": report}


@router.post("/api/system/restart/prepare")
async def prepare_restart(request: Request):
    """Prepare all agents for update restart, then trigger the restart."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)

    orchestrator._status["phase"] = "restarting"

    report = await orchestrator.prepare("all", "update")

    # Write pending-restart.json with the target SHA if known
    auto_updater = getattr(request.app.state, "auto_updater", None)
    target_sha = ""
    if auto_updater is not None:
        try:
            target_sha = await auto_updater._current_commit()
        except Exception:
            pass
    if target_sha:
        write_pending_restart(target_sha)

    # Trigger restart
    asyncio.create_task(_do_restart(request.app.state))

    return {"status": "restarting", "report": report}


async def _do_restart(app_state) -> None:
    await asyncio.sleep(2)

    notif = getattr(app_state, "notifications", None)

    async def _emit_fail(msg: str) -> None:
        if notif:
            await notif.add(
                title="Couldn't auto-restart — please restart manually",
                message=msg,
                level="error",
                source="system.lifecycle",
            )

    # 1. systemd
    if os.environ.get("INVOCATION_ID") or os.path.exists("/run/systemd/system"):
        for svc in ("taos.service", "tinyagentos.service"):
            for scope_args in (["systemctl", "--user", "is-active", svc], ["systemctl", "is-active", svc]):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *scope_args,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
                    if proc.returncode == 0:
                        restart_args = (
                            ["systemctl", "--user", "restart", svc]
                            if "--user" in scope_args
                            else ["systemctl", "restart", svc]
                        )
                        await asyncio.create_subprocess_exec(*restart_args)
                        sys.exit(0)
                except Exception:
                    pass

    # 2. Docker
    if os.path.exists("/.dockerenv"):
        sys.exit(0)

    # 3. execv
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as exc:
        await _emit_fail(str(exc))


@router.get("/api/system/restart/status")
async def restart_status(request: Request):
    """Return current orchestrator phase and per-agent status."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return JSONResponse({"error": "orchestrator not available"}, status_code=503)
    return orchestrator.get_status()
