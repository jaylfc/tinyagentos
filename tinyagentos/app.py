from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tinyagentos.config import load_config
from tinyagentos.metrics import MetricsStore
from tinyagentos.qmd_client import QmdClient

PROJECT_DIR = Path(__file__).parent.parent


def create_app(data_dir: Path | None = None, catalog_dir: Path | None = None) -> FastAPI:
    from tinyagentos.registry import AppRegistry
    from tinyagentos.hardware import get_hardware_profile

    data_dir = data_dir or PROJECT_DIR / "data"
    config_path = data_dir / "config.yaml"
    config = load_config(config_path)

    catalog_dir = catalog_dir or PROJECT_DIR / "app-catalog"
    hardware_path = data_dir / "hardware.json"
    hardware_profile = get_hardware_profile(hardware_path)
    installed_path = data_dir / "installed.json"
    registry = AppRegistry(catalog_dir=catalog_dir, installed_path=installed_path)

    metrics_store = MetricsStore(data_dir / "metrics.db")
    qmd_client = QmdClient(config.qmd.get("url", "http://localhost:7832"))
    http_client = httpx.AsyncClient(timeout=30)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await metrics_store.init()
        await qmd_client.init()
        app.state.config = config
        app.state.config_path = config_path
        app.state.metrics = metrics_store
        app.state.qmd_client = qmd_client
        app.state.http_client = http_client
        # Start background health monitor
        from tinyagentos.health import HealthMonitor
        monitor = HealthMonitor(config, metrics_store, qmd_client, http_client)
        app.state.registry = registry
        app.state.hardware_profile = hardware_profile
        app.state.health_monitor = monitor
        await monitor.start()
        yield
        await monitor.stop()
        await metrics_store.close()
        await qmd_client.close()
        await http_client.aclose()

    app = FastAPI(title="TinyAgentOS", version="0.1.0", lifespan=lifespan)

    # Set state eagerly so it's available even without lifespan (e.g. tests)
    app.state.config = config
    app.state.config_path = config_path
    app.state.metrics = metrics_store
    app.state.qmd_client = qmd_client
    app.state.http_client = http_client
    app.state.registry = registry
    app.state.hardware_profile = hardware_profile

    # Mount static files
    static_dir = PROJECT_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Templates
    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))
    app.state.templates = templates

    # Import and include routers
    from tinyagentos.routes.dashboard import router as dashboard_router
    app.include_router(dashboard_router)

    from tinyagentos.routes.agents import router as agents_router
    app.include_router(agents_router)

    from tinyagentos.routes.memory import router as memory_router
    app.include_router(memory_router)

    from tinyagentos.routes.settings import router as settings_router
    app.include_router(settings_router)

    from tinyagentos.routes.store import router as store_router
    app.include_router(store_router)

    from tinyagentos.routes.models import router as models_router
    app.include_router(models_router)

    return app


def main():
    import uvicorn
    config = load_config(PROJECT_DIR / "data" / "config.yaml")
    app = create_app()
    uvicorn.run(app, host=config.server.get("host", "0.0.0.0"), port=config.server.get("port", 8888))
