from __future__ import annotations

from pathlib import Path

import yaml

_README = "# {name}\n\nProject workspace managed by taOS.\n"


def project_dir(root: Path, slug: str) -> Path:
    return root / slug


def ensure_project_layout(root: Path, slug: str, name: str | None = None) -> Path:
    base = project_dir(root, slug)
    for sub in ("memory", "canvas", "files"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    readme = base / "README.md"
    if not readme.exists():
        readme.write_text(_README.format(name=name or slug))
    return base


def write_project_yaml(root: Path, slug: str, payload: dict) -> Path:
    base = project_dir(root, slug)
    base.mkdir(parents=True, exist_ok=True)
    target = base / "project.yaml"
    target.write_text(yaml.safe_dump(payload, sort_keys=False))
    return target


def read_project_yaml(root: Path, slug: str) -> dict | None:
    target = project_dir(root, slug) / "project.yaml"
    if not target.exists():
        return None
    return yaml.safe_load(target.read_text())
