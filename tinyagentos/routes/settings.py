from __future__ import annotations
import datetime
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from tinyagentos.config import AppConfig, save_config_locked, validate_config

router = APIRouter()

class ConfigUpdate(BaseModel):
    yaml: str

@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    config = request.app.state.config
    templates = request.app.state.templates
    config_yaml = yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False)
    config_path = request.app.state.config_path
    last_saved = None
    if config_path.exists():
        mtime = config_path.stat().st_mtime
        last_saved = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    return templates.TemplateResponse(request, "config.html", {
        "active_page": "config",
        "config_yaml": config_yaml, "last_saved": last_saved,
    })

@router.get("/api/config")
async def get_config(request: Request):
    config = request.app.state.config
    return {"yaml": yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False)}

@router.put("/api/config")
async def save_config_endpoint(request: Request, body: ConfigUpdate, validate_only: bool = False):
    try:
        data = yaml.safe_load(body.yaml)
    except yaml.YAMLError as e:
        return JSONResponse({"error": f"Invalid YAML: {e}"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "Config must be a YAML mapping"}, status_code=400)
    new_config = AppConfig(
        server=data.get("server", {}),
        backends=data.get("backends", []),
        qmd=data.get("qmd", {}),
        agents=data.get("agents", []),
        metrics=data.get("metrics", {}),
        config_path=request.app.state.config_path,
    )
    errors = validate_config(new_config)
    if errors:
        return JSONResponse({"error": "Validation failed", "details": errors}, status_code=400)
    if validate_only:
        return {"status": "valid", "message": "Config is valid"}
    await save_config_locked(new_config, request.app.state.config_path)
    request.app.state.config = new_config
    return {"status": "saved", "message": "Config saved successfully"}
