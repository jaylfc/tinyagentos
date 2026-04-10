"""Skill execution runtime.

Exposes assigned skills as HTTP endpoints so deployed agents can discover and
invoke them at runtime. Each built-in skill maps to an in-process implementation
function; agents first hit ``GET /api/skill-exec/tools`` to discover the tool
schemas for their assigned skills, then POST to ``/api/skill-exec/{id}/call``
to execute them.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Built-in skill implementations
# ---------------------------------------------------------------------------


async def _skill_memory_search(args: dict, request: Request) -> dict:
    """Search agent memory via QMD.

    Agents have their own QMD — this is a stub that would proxy to the agent's
    QMD_SERVER. For now, return an empty result with a hint.
    """
    _ = args.get("query", "")
    _ = args.get("limit", 10)
    return {
        "status": "ok",
        "results": [],
        "note": "Route queries via agent's QMD_SERVER",
    }


async def _skill_file_read(args: dict, request: Request) -> dict:
    """Read a file from the agent workspace."""
    from pathlib import Path

    path = args.get("path", "")
    data_dir = Path("/tmp/agent-workspace")
    data_dir.mkdir(exist_ok=True)
    target = (data_dir / path).resolve()
    try:
        if data_dir not in target.parents and target != data_dir:
            return {"error": "Path outside workspace"}
        if not target.is_file():
            return {"error": "File not found"}
        return {"content": target.read_text(errors="replace")}
    except Exception as exc:
        return {"error": str(exc)}


async def _skill_file_write(args: dict, request: Request) -> dict:
    """Write a file to the agent workspace."""
    from pathlib import Path

    path = args.get("path", "")
    content = args.get("content", "")
    data_dir = Path("/tmp/agent-workspace")
    data_dir.mkdir(exist_ok=True)
    target = (data_dir / path).resolve()
    try:
        if data_dir not in target.parents and target != data_dir:
            return {"error": "Path outside workspace"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {"status": "written", "bytes": len(content)}
    except Exception as exc:
        return {"error": str(exc)}


async def _skill_web_search(args: dict, request: Request) -> dict:
    """Search the web via SearXNG (if available)."""
    import httpx

    query = args.get("query", "")
    max_results = args.get("max_results", 5)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"http://localhost:8888/search?q={query}&format=json"
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"results": data.get("results", [])[:max_results]}
    except Exception:
        pass
    return {"error": "Web search not configured. Install SearXNG."}


async def _skill_code_exec(args: dict, request: Request) -> dict:
    """Execute Python code in a basic sandbox."""
    import subprocess

    code = args.get("code", "")
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Execution timed out (10s limit)"}
    except Exception as exc:
        return {"error": str(exc)}


async def _skill_http_request(args: dict, request: Request) -> dict:
    """Make an HTTP request to an external URL."""
    import httpx

    url = args.get("url", "")
    method = args.get("method", "GET")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(method, url)
            return {
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.text[:10000],
            }
    except Exception as exc:
        return {"error": str(exc)}


async def _skill_image_generation(args: dict, request: Request) -> dict:
    """Generate an image via local Stable Diffusion."""
    try:
        from tinyagentos.tools.image_tool import execute_image_generation

        result = await execute_image_generation(
            prompt=args.get("prompt", ""),
            size=args.get("size", "512x512"),
            steps=args.get("steps", 4),
        )
        return result
    except Exception as exc:
        return {"error": str(exc)}


SKILL_IMPLEMENTATIONS = {
    "memory_search": _skill_memory_search,
    "file_read": _skill_file_read,
    "file_write": _skill_file_write,
    "web_search": _skill_web_search,
    "code_exec": _skill_code_exec,
    "http_request": _skill_http_request,
    "image_generation": _skill_image_generation,
}


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


@router.get("/api/skill-exec/tools")
async def list_tools(request: Request, agent_name: str):
    """Return tool schemas for an agent's assigned skills.

    Agents call this on startup to discover their available tools. The response
    format matches the OpenAI / MCP tool definition so adapters can pass it
    straight through to framework tool registries.
    """
    skill_store = request.app.state.skills
    skills = await skill_store.get_agent_skills(agent_name)

    tools = []
    for skill in skills:
        schema = skill.get("tool_schema") or {}
        if not schema:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": schema.get("name", skill["id"]),
                    "description": schema.get(
                        "description", skill.get("description", "")
                    ),
                    "parameters": schema.get("input_schema", {}),
                },
                "skill_id": skill["id"],
                "exec_url": f"/api/skill-exec/{skill['id']}/call",
            }
        )

    return JSONResponse({"tools": tools})


@router.post("/api/skill-exec/{skill_id}/call")
async def execute_skill(skill_id: str, request: Request):
    """Execute a skill with the given arguments."""
    body = await request.json()
    args = body.get("args", {})

    skill_store = request.app.state.skills
    skill = await skill_store.get_skill(skill_id)
    if not skill:
        return JSONResponse(
            {"error": f"Skill {skill_id} not found"}, status_code=404
        )

    impl = SKILL_IMPLEMENTATIONS.get(skill_id)
    if not impl:
        return JSONResponse(
            {"error": f"No implementation for {skill_id}"}, status_code=501
        )

    try:
        result = await impl(args, request)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
