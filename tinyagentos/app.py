from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tinyagentos.backend_fallback import BackendFallback
from tinyagentos.capabilities import CapabilityChecker
from tinyagentos.cluster.manager import ClusterManager
from tinyagentos.cluster.router import TaskRouter
from tinyagentos.config import load_config
from tinyagentos.channels import ChannelStore
from tinyagentos.download_manager import DownloadManager
from tinyagentos.metrics import MetricsStore
from tinyagentos.notifications import NotificationStore
from tinyagentos.qmd_client import QmdClient
from tinyagentos.scheduler import TaskScheduler
from tinyagentos.relationships import RelationshipManager
from tinyagentos.secrets import SecretsStore
from tinyagentos.training import TrainingManager

PROJECT_DIR = Path(__file__).parent.parent


def create_app(data_dir: Path | None = None, catalog_dir: Path | None = None) -> FastAPI:
    from tinyagentos.registry import AppRegistry
    from tinyagentos.hardware import get_hardware_profile

    data_dir = data_dir or PROJECT_DIR / "data"
    config_path = data_dir / "config.yaml"
    # Copy example config on first run
    if not config_path.exists():
        example = data_dir / "config.yaml.example"
        if example.exists():
            import shutil
            shutil.copy2(example, config_path)
    config = load_config(config_path)

    catalog_dir = catalog_dir or PROJECT_DIR / "app-catalog"
    hardware_path = data_dir / "hardware.json"
    hardware_profile = get_hardware_profile(hardware_path)
    installed_path = data_dir / "installed.json"
    registry = AppRegistry(catalog_dir=catalog_dir, installed_path=installed_path)

    metrics_store = MetricsStore(data_dir / "metrics.db")
    notif_store = NotificationStore(data_dir / "notifications.db")
    qmd_client = QmdClient(config.qmd.get("url", "http://localhost:7832"))
    http_client = httpx.AsyncClient(timeout=30)
    download_manager = DownloadManager()
    secrets_store = SecretsStore(data_dir / "secrets.db")
    relationship_mgr = RelationshipManager(data_dir / "relationships.db")
    channel_store = ChannelStore(data_dir / "channels.db")
    scheduler = TaskScheduler(data_dir / "scheduler.db")
    fallback = BackendFallback(config.backends, http_client)
    cluster_manager = ClusterManager(notifications=notif_store)
    task_router = TaskRouter(cluster_manager, http_client)
    cap_checker = CapabilityChecker(hardware_profile, cluster_manager)
    cluster_manager._capabilities = cap_checker  # wire after creation (circular dep)
    training_manager = TrainingManager(data_dir / "training.db")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await metrics_store.init()
        await notif_store.init()
        await qmd_client.init()
        await secrets_store.init()
        await relationship_mgr.init()
        await channel_store.init()
        await scheduler.init()
        await training_manager.init()
        app.state.config = config
        app.state.config_path = config_path
        app.state.metrics = metrics_store
        app.state.notifications = notif_store
        app.state.qmd_client = qmd_client
        app.state.http_client = http_client
        app.state.download_manager = download_manager
        app.state.secrets = secrets_store
        app.state.relationships = relationship_mgr
        app.state.channels = channel_store
        app.state.fallback = fallback
        app.state.scheduler = scheduler
        app.state.cluster_manager = cluster_manager
        app.state.task_router = task_router
        app.state.capabilities = cap_checker
        app.state.training = training_manager
        # Start background health monitor
        from tinyagentos.health import HealthMonitor
        monitor = HealthMonitor(config, metrics_store, qmd_client, http_client, notif_store)
        app.state.registry = registry
        app.state.hardware_profile = hardware_profile
        app.state.health_monitor = monitor
        await monitor.start()
        await cluster_manager.start()
        yield
        await cluster_manager.stop()
        await monitor.stop()
        await training_manager.close()
        await scheduler.close()
        await channel_store.close()
        await relationship_mgr.close()
        await secrets_store.close()
        await notif_store.close()
        await metrics_store.close()
        await qmd_client.close()
        await http_client.aclose()

    app = FastAPI(title="TinyAgentOS", version="0.1.0", lifespan=lifespan)

    # GZip compression for faster transfers on slow SD card / network
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Set state eagerly so it's available even without lifespan (e.g. tests)
    app.state.config = config
    app.state.config_path = config_path
    app.state.metrics = metrics_store
    app.state.notifications = notif_store
    app.state.qmd_client = qmd_client
    app.state.http_client = http_client
    app.state.download_manager = download_manager
    app.state.secrets = secrets_store
    app.state.relationships = relationship_mgr
    app.state.channels = channel_store
    app.state.fallback = fallback
    app.state.scheduler = scheduler
    app.state.registry = registry
    app.state.hardware_profile = hardware_profile
    app.state.cluster_manager = cluster_manager
    app.state.task_router = task_router
    app.state.capabilities = cap_checker
    app.state.training = training_manager

    # Mount static files
    static_dir = PROJECT_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Templates
    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))
    templates.env.globals["cap"] = cap_checker
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

    from tinyagentos.routes.images import router as images_router
    app.include_router(images_router)

    from tinyagentos.routes.video import router as video_router
    app.include_router(video_router)

    from tinyagentos.routes.notifications import router as notifications_router
    app.include_router(notifications_router)

    from tinyagentos.routes.relationships import router as relationships_router
    app.include_router(relationships_router)

    from tinyagentos.routes.secrets import router as secrets_router
    app.include_router(secrets_router)

    from tinyagentos.routes.channels import router as channels_router
    app.include_router(channels_router)

    from tinyagentos.routes.tasks import router as tasks_router
    app.include_router(tasks_router)

    from tinyagentos.routes.import_data import router as import_router
    app.include_router(import_router)

    from tinyagentos.routes.cluster import router as cluster_router
    app.include_router(cluster_router)

    from tinyagentos.routes.training import router as training_router
    app.include_router(training_router)

    # Lobby demo (internal only — not included in public builds)
    try:
        from tinyagentos.lobby.routes import router as lobby_router
        app.include_router(lobby_router)
    except ImportError:
        pass  # Lobby not present in public release

    return app


def main():
    import uvicorn
    config = load_config(PROJECT_DIR / "data" / "config.yaml")
    app = create_app()
    uvicorn.run(app, host=config.server.get("host", "0.0.0.0"), port=config.server.get("port", 8888))
