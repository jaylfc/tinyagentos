from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import yaml

VALID_BACKEND_TYPES = {"rkllama", "ollama", "llama-cpp", "vllm"}

DEFAULT_CONFIG = {
    "server": {"host": "0.0.0.0", "port": 8888},
    "backends": [],
    "qmd": {"url": "http://localhost:7832"},
    "agents": [],
    "metrics": {"poll_interval": 30, "retention_days": 30},
}

_config_lock = asyncio.Lock()

@dataclass
class AppConfig:
    server: dict = field(default_factory=lambda: DEFAULT_CONFIG["server"].copy())
    backends: list[dict] = field(default_factory=list)
    qmd: dict = field(default_factory=lambda: DEFAULT_CONFIG["qmd"].copy())
    agents: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=lambda: DEFAULT_CONFIG["metrics"].copy())
    config_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "server": self.server,
            "backends": self.backends,
            "qmd": self.qmd,
            "agents": self.agents,
            "metrics": self.metrics,
        }

def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig(config_path=path)
    text = path.read_text()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")
    if not isinstance(data, dict):
        raise ValueError("Invalid YAML: expected a mapping at top level")
    return AppConfig(
        server=data.get("server", DEFAULT_CONFIG["server"].copy()),
        backends=data.get("backends", []),
        qmd=data.get("qmd", DEFAULT_CONFIG["qmd"].copy()),
        agents=data.get("agents", []),
        metrics=data.get("metrics", DEFAULT_CONFIG["metrics"].copy()),
        config_path=path,
    )

def save_config(config: AppConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False))

async def save_config_locked(config: AppConfig, path: Path) -> None:
    async with _config_lock:
        save_config(config, path)

def validate_config(config: AppConfig) -> list[str]:
    errors = []
    for i, b in enumerate(config.backends):
        if "url" not in b:
            errors.append(f"backends[{i}]: missing 'url'")
        if b.get("type") not in VALID_BACKEND_TYPES:
            errors.append(f"backends[{i}]: invalid type '{b.get('type')}', must be one of {VALID_BACKEND_TYPES}")
    seen_agents = set()
    for i, a in enumerate(config.agents):
        name = a.get("name", "")
        if name in seen_agents:
            errors.append(f"agents[{i}]: duplicate agent name '{name}'")
        seen_agents.add(name)
    return errors
