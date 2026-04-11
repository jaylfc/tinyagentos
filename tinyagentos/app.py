from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tinyagentos.auth import AuthManager
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
from tinyagentos.backend_adapters import check_backend_health
from tinyagentos.benchmark import BenchmarkStore
from tinyagentos.installation_state import InstallationState
from tinyagentos.scheduler import BackendCatalog, HistoryStore, ScoreCache, TaskScheduler
from tinyagentos.scheduler.discovery import build_scheduler as build_resource_scheduler
from tinyagentos.torrent_settings import TorrentSettingsStore
from tinyagentos.relationships import RelationshipManager
from tinyagentos.secrets import SecretsStore
from tinyagentos.training import TrainingManager
from tinyagentos.conversion import ConversionManager
from tinyagentos.agent_messages import AgentMessageStore
from tinyagentos.shared_folders import SharedFolderManager
from tinyagentos.streaming import StreamingSessionStore
from tinyagentos.expert_agents import ExpertAgentStore
from tinyagentos.app_orchestrator import AppOrchestrator
from tinyagentos.computer_use import ComputerUseManager
from tinyagentos.webhook_notifier import WebhookNotifier
from tinyagentos.llm_proxy import LLMProxy
from tinyagentos.channel_hub.router import MessageRouter
from tinyagentos.channel_hub.adapter_manager import AdapterManager
from tinyagentos.chat.message_store import ChatMessageStore
from tinyagentos.chat.channel_store import ChatChannelStore
from tinyagentos.chat.hub import ChatHub
from tinyagentos.chat.canvas import CanvasStore
from tinyagentos.desktop_settings import DesktopSettingsStore
from tinyagentos.user_memory import UserMemoryStore
from tinyagentos.installed_apps import InstalledAppsStore
from tinyagentos.skills import SkillStore

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
    torrent_settings_store = TorrentSettingsStore(data_dir / "torrent_settings.json")
    download_manager = DownloadManager(torrent_settings_store=torrent_settings_store)
    secrets_store = SecretsStore(data_dir / "secrets.db")
    relationship_mgr = RelationshipManager(data_dir / "relationships.db")
    channel_store = ChannelStore(data_dir / "channels.db")
    scheduler = TaskScheduler(data_dir / "scheduler.db")
    benchmark_store = BenchmarkStore(data_dir / "benchmarks.db")
    score_cache = ScoreCache(benchmark_store, poll_interval_seconds=15.0)
    scheduler_history_store = HistoryStore(data_dir / "scheduler_history.db")

    async def _probe_backend(backend: dict) -> dict:
        return await check_backend_health(http_client, backend)

    backend_catalog = BackendCatalog(
        backends=config.backends,
        probe_fn=_probe_backend,
        interval_seconds=30.0,
    )
    fallback = BackendFallback(config.backends, http_client)
    cluster_manager = ClusterManager(notifications=notif_store)
    task_router = TaskRouter(cluster_manager, http_client)
    cap_checker = CapabilityChecker(hardware_profile, cluster_manager)
    cluster_manager._capabilities = cap_checker  # wire after creation (circular dep)
    training_manager = TrainingManager(data_dir / "training.db")
    conversion_manager = ConversionManager(data_dir / "conversion.db")
    agent_messages = AgentMessageStore(data_dir / "agent_messages.db")
    shared_folders = SharedFolderManager(data_dir / "shared_folders.db", data_dir / "shared-folders")
    streaming_sessions = StreamingSessionStore(data_dir / "streaming.db")
    expert_agents = ExpertAgentStore(data_dir / "expert_agents.db")
    app_orchestrator = AppOrchestrator(cluster_manager, streaming_sessions, http_client)
    computer_use = ComputerUseManager()
    auth_manager = AuthManager(data_dir)
    webhook_notifier = WebhookNotifier(config.to_dict())
    notif_store.set_webhook_notifier(webhook_notifier)
    llm_proxy = LLMProxy(port=4000)
    channel_hub_router = MessageRouter()
    adapter_manager = AdapterManager(channel_hub_router)
    chat_messages = ChatMessageStore(data_dir / "chat.db")
    chat_channels = ChatChannelStore(data_dir / "chat.db")
    chat_hub = ChatHub()
    canvas_store = CanvasStore(data_dir / "canvas.db")
    desktop_settings = DesktopSettingsStore(data_dir / "desktop.db")
    user_memory = UserMemoryStore(data_dir / "user_memory.db")
    installed_apps = InstalledAppsStore(data_dir / "installed_apps.db")
    skills = SkillStore(data_dir / "skills.db")

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
        await conversion_manager.init()
        await agent_messages.init()
        await shared_folders.init()
        await streaming_sessions.init()
        await expert_agents.init()
        await chat_messages.init()
        await chat_channels.init()
        await canvas_store.init()
        await desktop_settings.init()
        await user_memory.init()
        await installed_apps.init()
        await skills.init()
        await benchmark_store.init()
        await scheduler_history_store.init()
        app.state.config = config
        app.state.config_path = config_path
        app.state.data_dir = data_dir
        # Per-agent state lives on the host and is mounted into containers.
        # See docs/design/framework-agnostic-runtime.md.
        app.state.agent_workspaces_dir = data_dir / "agent-workspaces"
        app.state.agent_memory_dir = data_dir / "agent-memory"
        app.state.agent_workspaces_dir.mkdir(parents=True, exist_ok=True)
        app.state.agent_memory_dir.mkdir(parents=True, exist_ok=True)
        app.state.models_dir = data_dir / "models"
        app.state.models_dir.mkdir(parents=True, exist_ok=True)
        app.state.metrics = metrics_store
        app.state.notifications = notif_store
        app.state.qmd_client = qmd_client
        app.state.http_client = http_client
        app.state.download_manager = download_manager
        app.state.torrent_settings_store = torrent_settings_store
        app.state.secrets = secrets_store
        app.state.relationships = relationship_mgr
        app.state.channels = channel_store
        app.state.fallback = fallback
        app.state.scheduler = scheduler
        app.state.cluster_manager = cluster_manager
        app.state.task_router = task_router
        app.state.capabilities = cap_checker
        app.state.training = training_manager
        app.state.conversion = conversion_manager
        app.state.agent_messages = agent_messages
        app.state.shared_folders = shared_folders
        app.state.streaming_sessions = streaming_sessions
        app.state.expert_agents = expert_agents
        app.state.app_orchestrator = app_orchestrator
        app.state.computer_use = computer_use
        app.state.auth = auth_manager
        app.state.webhook_notifier = webhook_notifier
        app.state.llm_proxy = llm_proxy
        app.state.channel_hub_router = channel_hub_router
        app.state.adapter_manager = adapter_manager
        app.state.channel_hub_connectors = {}
        app.state.deploy_tasks = {}
        app.state.chat_messages = chat_messages
        app.state.chat_channels = chat_channels
        app.state.chat_hub = chat_hub
        app.state.canvas_store = canvas_store
        app.state.desktop_settings = desktop_settings
        app.state.user_memory = user_memory
        app.state.installed_apps = installed_apps
        app.state.skills = skills
        app.state.benchmark_store = benchmark_store
        app.state.score_cache = score_cache
        app.state.scheduler_history_store = scheduler_history_store
        # Optionally start LiteLLM proxy (non-fatal if not installed)
        try:
            await llm_proxy.start(config.backends)
        except Exception:
            pass  # LiteLLM is optional
        # Start background health monitor
        from tinyagentos.health import HealthMonitor
        monitor = HealthMonitor(config, metrics_store, qmd_client, http_client, notif_store)
        app.state.registry = registry
        app.state.hardware_profile = hardware_profile
        app.state.health_monitor = monitor
        await monitor.start()
        await cluster_manager.start()
        # Start the live backend catalog — everything that asks "what's
        # available?" reads from this rather than the filesystem.
        try:
            await backend_catalog.start()
        except Exception:
            logger.exception("backend catalog failed to start — routes will fall back to static config")
        app.state.backend_catalog = backend_catalog

        # Joined view of the registry cache + live catalog probes.
        # Used by the Store / Dashboard / Models routes instead of
        # registry.is_installed() / list_installed() directly.
        app.state.installation_state = InstallationState(registry, backend_catalog)

        # LiteLLM config reload on catalog change — keeps the proxy's
        # routing table in sync with live backend state. Subscriber is
        # a no-op if the proxy isn't running (LiteLLM not installed) or
        # if the catalog signature hasn't changed.
        async def _reload_llm_proxy_on_catalog_change() -> None:
            if not llm_proxy.is_running():
                return
            await llm_proxy.reload_config(config.backends)

        backend_catalog.subscribe(_reload_llm_proxy_on_catalog_change)

        # Start the score cache — bridges the async benchmark store to the
        # scheduler's sync admission path via a 15s polling loop.
        try:
            await score_cache.start()
        except Exception:
            logger.exception("score cache failed to start — scheduler will route by tier only")

        # Build the resource scheduler from hardware profile + live catalog.
        # Phase 1: local resources only (NPU + CPU), capability-based routing
        # with fallback and priority. Cluster-aware dispatch is Phase 3.
        try:
            resource_scheduler = build_resource_scheduler(
                hardware_profile,
                backend_catalog,
                benchmark_store=benchmark_store,
                score_cache=score_cache,
                history_store=scheduler_history_store,
            )
            app.state.resource_scheduler = resource_scheduler
            logger.info(
                "resource scheduler ready: %s",
                [r.name for r in resource_scheduler.resources()],
            )
        except Exception:
            logger.exception("resource scheduler failed to build — routes will use static config")
            app.state.resource_scheduler = None
        # Detect and set container runtime
        from tinyagentos.containers.backend import detect_runtime, set_backend
        from tinyagentos.containers.lxc import LXCBackend
        from tinyagentos.containers.docker import DockerBackend
        runtime = getattr(config, "container_runtime", "auto")
        if runtime == "auto":
            runtime = detect_runtime()
        if runtime == "lxc":
            set_backend(LXCBackend())
        elif runtime in ("docker", "podman"):
            set_backend(DockerBackend(binary=runtime))
        yield
        adapter_manager.stop_all()
        for c in list(getattr(app.state, "channel_hub_connectors", {}).values()):
            await c.stop()
        await score_cache.stop()
        await backend_catalog.stop()
        await cluster_manager.stop()
        llm_proxy.stop()
        await monitor.stop()
        await scheduler_history_store.close()
        await benchmark_store.close()
        await skills.close()
        await installed_apps.close()
        await user_memory.close()
        await desktop_settings.close()
        await canvas_store.close()
        await chat_channels.close()
        await chat_messages.close()
        await expert_agents.close()
        await streaming_sessions.close()
        await shared_folders.close()
        await agent_messages.close()
        await conversion_manager.close()
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

    # Auth middleware — must be added before GZip so it runs first
    from tinyagentos.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)

    # GZip compression for faster transfers on slow SD card / network
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Set state eagerly so it's available even without lifespan (e.g. tests)
    app.state.config = config
    app.state.config_path = config_path
    app.state.data_dir = data_dir
    app.state.agent_workspaces_dir = data_dir / "agent-workspaces"
    app.state.agent_memory_dir = data_dir / "agent-memory"
    app.state.agent_workspaces_dir.mkdir(parents=True, exist_ok=True)
    app.state.agent_memory_dir.mkdir(parents=True, exist_ok=True)
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
    app.state.conversion = conversion_manager
    app.state.agent_messages = agent_messages
    app.state.shared_folders = shared_folders
    app.state.streaming_sessions = streaming_sessions
    app.state.expert_agents = expert_agents
    app.state.app_orchestrator = app_orchestrator
    app.state.computer_use = computer_use
    app.state.auth = auth_manager
    app.state.webhook_notifier = webhook_notifier
    app.state.llm_proxy = llm_proxy
    app.state.channel_hub_router = channel_hub_router
    app.state.adapter_manager = adapter_manager
    app.state.channel_hub_connectors = {}
    app.state.deploy_tasks = {}
    app.state.chat_messages = chat_messages
    app.state.chat_channels = chat_channels
    app.state.chat_hub = chat_hub
    app.state.canvas_store = canvas_store
    app.state.desktop_settings = desktop_settings
    app.state.user_memory = user_memory
    app.state.installed_apps = installed_apps
    app.state.skills = skills

    # Detect and set container runtime (eager, so tests work without lifespan)
    try:
        from tinyagentos.containers.backend import detect_runtime, set_backend
        from tinyagentos.containers.lxc import LXCBackend
        from tinyagentos.containers.docker import DockerBackend
        _runtime = getattr(config, "container_runtime", "auto")
        if _runtime == "auto":
            _runtime = detect_runtime()
        if _runtime == "lxc":
            set_backend(LXCBackend())
        elif _runtime in ("docker", "podman"):
            set_backend(DockerBackend(binary=_runtime))
    except Exception:
        pass  # Container runtime detection is non-fatal

    # Mount static files
    static_dir = PROJECT_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Mount workspace for serving generated images and other workspace files
    workspace_dir = data_dir / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/data/workspace", StaticFiles(directory=str(workspace_dir)), name="workspace")

    # Desktop SPA assets are served by the desktop route handler (routes/desktop.py)

    # Templates
    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))
    templates.env.globals["cap"] = cap_checker
    app.state.templates = templates

    # Import and include routers
    from tinyagentos.routes.auth import router as auth_router
    app.include_router(auth_router)

    from tinyagentos.routes.dashboard import router as dashboard_router
    app.include_router(dashboard_router)

    from tinyagentos.routes.agents import router as agents_router
    app.include_router(agents_router)

    from tinyagentos.routes.memory import router as memory_router
    app.include_router(memory_router)

    from tinyagentos.routes.user_memory import router as user_memory_router
    app.include_router(user_memory_router)

    from tinyagentos.routes.settings import router as settings_router
    app.include_router(settings_router)

    from tinyagentos.routes.store import router as store_router
    app.include_router(store_router)

    from tinyagentos.routes.store_install import router as store_install_router
    app.include_router(store_install_router)

    from tinyagentos.routes.models import router as models_router
    app.include_router(models_router)

    from tinyagentos.routes.images import router as images_router
    app.include_router(images_router)

    from tinyagentos.routes.scheduler import router as scheduler_router
    app.include_router(scheduler_router)

    from tinyagentos.routes.benchmarks import router as benchmarks_router
    app.include_router(benchmarks_router)

    from tinyagentos.routes.torrent import router as torrent_router
    app.include_router(torrent_router)

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

    from tinyagentos.routes.conversion import router as conversion_router
    app.include_router(conversion_router)

    from tinyagentos.routes.workspace import router as workspace_router
    app.include_router(workspace_router)

    from tinyagentos.routes.user_workspace import router as user_workspace_router
    app.include_router(user_workspace_router)

    from tinyagentos.routes.shared_folders import router as shared_folders_router
    app.include_router(shared_folders_router)

    from tinyagentos.routes.providers import router as providers_router
    app.include_router(providers_router)

    from tinyagentos.routes.channel_hub import router as channel_hub_router_routes
    app.include_router(channel_hub_router_routes)

    from tinyagentos.routes.search import router as search_router
    app.include_router(search_router)

    from tinyagentos.routes.streaming import router as streaming_router
    app.include_router(streaming_router)

    from tinyagentos.routes.templates import router as templates_router
    app.include_router(templates_router)

    from tinyagentos.routes.chat import router as chat_router
    app.include_router(chat_router)

    from tinyagentos.routes.desktop import router as desktop_router
    app.include_router(desktop_router)

    from tinyagentos.routes.games import router as games_router
    app.include_router(games_router)

    from tinyagentos.routes.terminal import router as terminal_router
    app.include_router(terminal_router)

    from tinyagentos.routes.skills import router as skills_router
    app.include_router(skills_router)

    from tinyagentos.routes.skill_exec import router as skill_exec_router
    app.include_router(skill_exec_router)

    from tinyagentos.routes.activity import router as activity_router
    app.include_router(activity_router)

    from tinyagentos.routes.frameworks import router as frameworks_router
    app.include_router(frameworks_router)

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
    uvicorn.run(app, host=config.server.get("host", "0.0.0.0"), port=config.server.get("port", 6969))


def gui():
    """Launch the TinyAgentOS web UI in a browser window."""
    import subprocess
    import webbrowser
    port = 6969
    url = f"http://localhost:{port}"
    # Try Chromium in app mode first (cleanest look), fall back to default browser
    for browser in ["chromium-browser", "chromium", "google-chrome"]:
        try:
            subprocess.Popen([browser, f"--app={url}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue
    # Fallback: open in default browser
    webbrowser.open(url)
