# Agent persona + memory deploy — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the persona step at deploy, the per-agent Persona + Memory tabs in Agent Settings, the Store Memory category and Plugins/MCP split, the emoji picker revamp, the existing-agent migration, and the trace-capture gaps that let Librarian enrichment run per-agent.

**Architecture:** Backend-first. New agent dict fields live in the existing YAML config. A new SQLite store backs `user_personas`. System prompt is assembled lazily from agent fields + taosmd's shipped `agent-rules.md`. Bridge events additionally write to the Archive (dual-write alongside the trace store). UI work is split cleanly between the deploy wizard and Agent Settings tabs.

**Tech Stack:** Python 3.11, FastAPI, pytest, SQLite3 (stdlib), dataclasses; React 18 + TypeScript + Vite, Tailwind + shadcn/ui, Playwright.

**Spec:** `docs/superpowers/specs/2026-04-18-agent-persona-and-memory-deploy-design.md` — the plan tracks that spec section-for-section.

**Branch:** All changes on a single feature branch `feat/agent-persona-memory` off master. One PR at the end, or split per phase at the executor's discretion.

---

## File structure

**New files:**

- `tinyagentos/prompt_assembly.py` — pure function that assembles the agent system prompt from its pieces.
- `tinyagentos/user_personas.py` — SQLite-backed store for user-authored personas.
- `tinyagentos/migrations/persona_v2.py` — one-shot migration for existing agents.
- `tinyagentos/migrations/__init__.py` — version marker + runner.
- `tinyagentos/routes/user_personas.py` — CRUD endpoints for user personas.
- `tinyagentos/routes/librarian.py` — per-agent Librarian config GET/PATCH.
- `tests/test_prompt_assembly.py` — unit tests for assembly function.
- `tests/test_user_personas.py` — unit tests for CRUD store.
- `tests/test_migration_persona_v2.py` — idempotency and slug-safety tests.
- `tests/test_bridge_session_archive.py` — archive dual-write tests.
- `desktop/src/components/persona-picker/PersonaPicker.tsx` — Browse/Create/Blank tabs.
- `desktop/src/components/persona-picker/PersonaBrowse.tsx` — single list with search + source filter.
- `desktop/src/components/persona-picker/PersonaCreate.tsx` — Soul + Agent.md editor + save-to-library.
- `desktop/src/components/persona-picker/PersonaBlank.tsx` — single-button blank panel.
- `desktop/src/components/EmojiPicker.tsx` — wraps the chosen picker library in a popover.
- `desktop/src/components/agent-settings/PersonaTab.tsx` — new Persona tab content.
- `desktop/src/components/agent-settings/MemoryTab.tsx` — new Memory tab content.
- `desktop/src/components/MigrationBanner.tsx` — one-time upgrade banner.
- `desktop/tests/e2e/persona-deploy.spec.ts` — Playwright for the three deploy paths.
- `desktop/tests/e2e/agent-settings-memory.spec.ts` — Playwright for Memory tab.
- `desktop/tests/e2e/store-memory-category.spec.ts` — Playwright for Store deep-link.

**Modified files:**

- `tinyagentos/config.py` — extend `normalize_agent` with new fields.
- `tinyagentos/agent_templates.py` — strip `model`, `framework`, `memory_limit`, `cpu_limit` from built-ins.
- `tinyagentos/routes/agents.py` — extend `DeployAgentRequest`, call `register_agent`, archive smoke-check, persona+memory PATCH endpoints.
- `tinyagentos/bridge/bridge_session.py` — archive dual-write on tool_call / tool_result / error / reasoning events.
- `tinyagentos/scheduling/job_worker.py` — pass `agent_name` through enrichment.
- `tinyagentos/app.py` — run persona_v2 migration on startup; register new routers.
- `desktop/src/apps/AgentsApp.tsx` — new Step 0 (persona picker), slug preview, remove framework-default emoji auto-fill, new Persona + Memory tabs.
- `desktop/src/apps/StoreApp.tsx` — add Memory category, split Plugins & MCP into two categories, query-param deep-link.
- `desktop/src/lib/agent-emoji.ts` — remove `defaultEmojiForFramework` and `EMOJI_QUICK_PICKS` exports once the last caller is gone.

---

## Phase 1 — Foundation

### Task 1.1: Extend agent record with new fields

**Files:**
- Modify: `tinyagentos/config.py` (add new fields to `normalize_agent`)
- Test: `tests/test_config_normalize.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_normalize.py`:

```python
from tinyagentos.config import normalize_agent

def test_normalize_agent_adds_persona_fields_with_defaults():
    agent = {"name": "atlas", "display_name": "Atlas", "framework": "openclaw"}
    normalize_agent(agent)
    assert agent["soul_md"] == ""
    assert agent["agent_md"] == ""
    assert agent["memory_plugin"] == "taosmd"
    assert agent["source_persona_id"] is None
    assert agent["migrated_to_v2_personas"] is False

def test_normalize_agent_preserves_existing_persona_fields():
    agent = {
        "name": "atlas", "display_name": "Atlas", "framework": "openclaw",
        "soul_md": "You are Atlas", "agent_md": "Always use tools",
        "memory_plugin": "none", "source_persona_id": "builtin:research",
        "migrated_to_v2_personas": True,
    }
    normalize_agent(agent)
    assert agent["soul_md"] == "You are Atlas"
    assert agent["agent_md"] == "Always use tools"
    assert agent["memory_plugin"] == "none"
    assert agent["source_persona_id"] == "builtin:research"
    assert agent["migrated_to_v2_personas"] is True
```

- [ ] **Step 2: Run — expect FAIL**

`pytest tests/test_config_normalize.py -v` → FAIL (fields missing).

- [ ] **Step 3: Minimal implementation**

In `tinyagentos/config.py` find `normalize_agent` (near line 140). Add at the end of the function:

```python
    agent.setdefault("soul_md", "")
    agent.setdefault("agent_md", "")
    agent.setdefault("memory_plugin", "taosmd")
    agent.setdefault("source_persona_id", None)
    # False for pre-existing rows; new deploys flip to True explicitly.
    agent.setdefault("migrated_to_v2_personas", False)
```

- [ ] **Step 4: Run — expect PASS**

`pytest tests/test_config_normalize.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/config.py tests/test_config_normalize.py
git commit -m "feat(config): add persona + memory fields to agent normalize"
```

---

### Task 1.2: Create prompt_assembly.py

**Files:**
- Create: `tinyagentos/prompt_assembly.py`
- Test: `tests/test_prompt_assembly.py`

- [ ] **Step 1: Write the failing test (happy path + empty-parts)**

```python
# tests/test_prompt_assembly.py
import pytest
from tinyagentos.prompt_assembly import assemble_system_prompt, STRICT_READ_DIRECTIVE

class _Agent:
    def __init__(self, slug="atlas", soul="", agent_md="", memory_plugin="taosmd"):
        self.slug = slug
        self.soul_md = soul
        self.agent_md = agent_md
        self.memory_plugin = memory_plugin

def test_directive_always_first():
    out = assemble_system_prompt(_Agent(memory_plugin="none"))
    assert out.startswith(STRICT_READ_DIRECTIVE)

def test_taosmd_rules_included_and_substituted(monkeypatch):
    monkeypatch.setattr(
        "tinyagentos.prompt_assembly._load_agent_rules",
        lambda: "rules for <your-agent-name>",
    )
    out = assemble_system_prompt(_Agent(slug="atlas", memory_plugin="taosmd"))
    assert "rules for atlas" in out
    assert "<your-agent-name>" not in out

def test_memory_none_skips_rules(monkeypatch):
    monkeypatch.setattr(
        "tinyagentos.prompt_assembly._load_agent_rules",
        lambda: "rules for <your-agent-name>",
    )
    out = assemble_system_prompt(_Agent(memory_plugin="none"))
    assert "rules for" not in out

def test_soul_and_agent_md_concatenated_in_order(monkeypatch):
    monkeypatch.setattr(
        "tinyagentos.prompt_assembly._load_agent_rules",
        lambda: "MEMORY",
    )
    out = assemble_system_prompt(_Agent(soul="SOUL", agent_md="AGENT"))
    idx_mem = out.index("MEMORY")
    idx_soul = out.index("SOUL")
    idx_agent = out.index("AGENT")
    assert idx_mem < idx_soul < idx_agent

def test_empty_soul_and_agent_md_are_skipped(monkeypatch):
    monkeypatch.setattr("tinyagentos.prompt_assembly._load_agent_rules", lambda: "M")
    out = assemble_system_prompt(_Agent(soul="", agent_md=""))
    # Only directive + memory block
    assert out.count("\n\n---\n\n") == 1

def test_missing_agent_rules_logs_and_returns_empty(monkeypatch, caplog):
    monkeypatch.setattr(
        "tinyagentos.prompt_assembly._load_agent_rules",
        lambda: "",  # missing
    )
    out = assemble_system_prompt(_Agent(soul="SOUL"))
    assert "SOUL" in out
    # When memory rules missing, the directive still ships.
    assert out.startswith(STRICT_READ_DIRECTIVE)
```

- [ ] **Step 2: Run — expect FAIL (module missing)**

`pytest tests/test_prompt_assembly.py -v` → FAIL.

- [ ] **Step 3: Minimal implementation**

```python
# tinyagentos/prompt_assembly.py
"""System prompt assembly — layered pieces → single string."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STRICT_READ_DIRECTIVE = (
    "Read this document end-to-end. Do not skim, summarise, or truncate. "
    "Every section below is load-bearing."
)

_SEPARATOR = "\n\n---\n\n"


def _load_agent_rules() -> str:
    """Read `docs/agent-rules.md` from the installed taosmd package.

    Falls back to empty string with a warning log if the file is missing —
    agents still boot, but without the memory-usage contract.
    """
    try:
        import taosmd
    except ImportError:
        logger.warning("taosmd not installed — skipping agent-rules block")
        return ""
    pkg_root = Path(taosmd.__file__).resolve().parent.parent
    rules_path = pkg_root / "docs" / "agent-rules.md"
    if not rules_path.exists():
        logger.warning("taosmd agent-rules.md missing at %s", rules_path)
        return ""
    return rules_path.read_text(encoding="utf-8")


def _taosmd_agent_rules(slug: str) -> str:
    raw = _load_agent_rules()
    if not raw:
        return ""
    return raw.replace("<your-agent-name>", slug)


def assemble_system_prompt(agent) -> str:
    """Assemble the agent's system prompt from its record fields.

    Pure function — call every turn rather than caching.
    """
    parts: list[str] = [STRICT_READ_DIRECTIVE]
    if getattr(agent, "memory_plugin", "taosmd") == "taosmd":
        rules = _taosmd_agent_rules(agent.slug)
        if rules:
            parts.append(rules)
    if getattr(agent, "soul_md", ""):
        parts.append(agent.soul_md)
    if getattr(agent, "agent_md", ""):
        parts.append(agent.agent_md)
    return _SEPARATOR.join(parts)
```

- [ ] **Step 4: Run — expect PASS**

`pytest tests/test_prompt_assembly.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/prompt_assembly.py tests/test_prompt_assembly.py
git commit -m "feat(prompts): add layered system-prompt assembly for agents"
```

---

### Task 1.3: Wire assembler into the prompt send path

**Files:**
- Modify: `tinyagentos/bridge/bridge_session.py` (or wherever the current system-prompt string is assembled on turn send)
- Test: `tests/test_bridge_session_prompt.py`

- [ ] **Step 1: Locate existing prompt assembly**

```bash
grep -rn "system_prompt\|systemPrompt" tinyagentos/bridge/ tinyagentos/routes/openclaw.py | head -20
```

Identify where the framework runtime is handed the system string today. Likely the openclaw bootstrap payload.

- [ ] **Step 2: Write the failing test**

A small adapter test that, given an agent dict with persona fields, produces a bootstrap payload containing the assembled prompt in the expected field. Use a fake agent dict with `slug`, `soul_md`, `agent_md`, `memory_plugin`. Stub `_load_agent_rules` to a known string.

```python
def test_bootstrap_uses_assembled_prompt(monkeypatch):
    monkeypatch.setattr(
        "tinyagentos.prompt_assembly._load_agent_rules",
        lambda: "MEMORY_RULES",
    )
    agent = type("A", (), {
        "slug": "atlas", "soul_md": "SOUL",
        "agent_md": "", "memory_plugin": "taosmd",
    })()
    from tinyagentos.bridge.bridge_session import build_bootstrap_system_prompt
    out = build_bootstrap_system_prompt(agent)
    assert "MEMORY_RULES" in out
    assert "SOUL" in out
```

- [ ] **Step 3: Implementation**

Add a thin wrapper in the file that owns bootstrap-construction (likely `bridge_session.py`):

```python
from tinyagentos.prompt_assembly import assemble_system_prompt

def build_bootstrap_system_prompt(agent) -> str:
    """Single call-site that bootstrap + any future prompt send-points use."""
    return assemble_system_prompt(agent)
```

Then grep every existing site that currently constructs a system prompt string for the agent and replace with `build_bootstrap_system_prompt(agent)`. If today there's no such construction (system prompt was empty before), add the call at the bootstrap site so the prompt ships on the first turn.

- [ ] **Step 4: Run**

`pytest tests/test_bridge_session_prompt.py -v` → PASS.
Manually smoke: run an agent locally, check the bootstrap payload contains the memory rules block.

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/bridge/bridge_session.py tests/test_bridge_session_prompt.py
git commit -m "feat(bridge): send assembled system prompt on agent bootstrap"
```

---

### Task 1.4: Strip irrelevant fields from agent_templates.py built-ins

**Files:**
- Modify: `tinyagentos/agent_templates.py`
- Test: `tests/test_agent_templates.py`

- [ ] **Step 1: Write the failing test**

```python
from tinyagentos.agent_templates import list_templates, BUILTIN_TEMPLATES

def test_builtin_templates_have_no_runtime_fields():
    for tpl in BUILTIN_TEMPLATES:
        for banned in ("model", "framework", "memory_limit", "cpu_limit"):
            assert banned not in tpl, f"{tpl['id']} still has {banned}"

def test_builtin_templates_have_persona_fields():
    for tpl in BUILTIN_TEMPLATES:
        assert "id" in tpl
        assert "name" in tpl
        assert "system_prompt" in tpl
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

Edit `tinyagentos/agent_templates.py` — for each dict in `BUILTIN_TEMPLATES` remove `model`, `framework`, `memory_limit`, `cpu_limit`. Keep `id`, `name`, `category`, `description`, `system_prompt`, `color`, `emoji` (if present).

Update any helper functions (`list_templates`, `get_template`) that may assume those keys exist.

- [ ] **Step 4: Run — expect PASS**

`pytest tests/test_agent_templates.py -v` → PASS. Also run existing templates tests to confirm nothing downstream breaks.

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/agent_templates.py tests/test_agent_templates.py
git commit -m "refactor(templates): drop runtime fields from built-in personas"
```

---

### Task 1.5: Create user_personas SQLite store

**Files:**
- Create: `tinyagentos/user_personas.py`
- Test: `tests/test_user_personas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_user_personas.py
import pytest
from tinyagentos.user_personas import UserPersonaStore

@pytest.fixture
def store(tmp_path):
    return UserPersonaStore(tmp_path / "personas.db")

def test_create_and_get(store):
    pid = store.create(name="My Persona", soul_md="SOUL", agent_md="AGENT", description="desc")
    row = store.get(pid)
    assert row["name"] == "My Persona"
    assert row["soul_md"] == "SOUL"
    assert row["agent_md"] == "AGENT"
    assert row["description"] == "desc"

def test_list_newest_first(store):
    a = store.create(name="A", soul_md="")
    b = store.create(name="B", soul_md="")
    rows = store.list()
    assert [r["id"] for r in rows] == [b, a]

def test_update(store):
    pid = store.create(name="X", soul_md="old")
    store.update(pid, soul_md="new")
    assert store.get(pid)["soul_md"] == "new"

def test_delete(store):
    pid = store.create(name="X", soul_md="")
    store.delete(pid)
    assert store.get(pid) is None

def test_created_at_is_utc_seconds(store):
    pid = store.create(name="X", soul_md="")
    ts = store.get(pid)["created_at"]
    assert isinstance(ts, int)
    import time; now = int(time.time())
    assert now - 5 < ts <= now
```

- [ ] **Step 2: Run — expect FAIL (module missing)**

- [ ] **Step 3: Implementation**

```python
# tinyagentos/user_personas.py
"""SQLite-backed store for user-authored personas."""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_personas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    soul_md     TEXT NOT NULL DEFAULT '',
    agent_md    TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);
"""


class UserPersonaStore:
    def __init__(self, db_path: Path):
        self._db = Path(db_path)
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        return con

    def create(
        self,
        *,
        name: str,
        soul_md: str,
        agent_md: str = "",
        description: str | None = None,
    ) -> str:
        pid = uuid.uuid4().hex
        with self._conn() as con:
            con.execute(
                "INSERT INTO user_personas (id, name, description, soul_md, agent_md, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, name, description, soul_md, agent_md, int(time.time())),
            )
        return pid

    def get(self, pid: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT id, name, description, soul_md, agent_md, created_at "
                "FROM user_personas WHERE id = ?",
                (pid,),
            ).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id, name, description, soul_md, agent_md, created_at "
                "FROM user_personas ORDER BY created_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def update(self, pid: str, **fields) -> None:
        allowed = {"name", "description", "soul_md", "agent_md"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"unknown fields: {sorted(bad)}")
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [pid]
        with self._conn() as con:
            con.execute(f"UPDATE user_personas SET {assignments} WHERE id = ?", values)

    def delete(self, pid: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM user_personas WHERE id = ?", (pid,))
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/user_personas.py tests/test_user_personas.py
git commit -m "feat(personas): add SQLite store for user-authored personas"
```

---

## Phase 2 — Trace capture (backend, independently shippable)

### Task 2.1: Archive dual-write on bridge tool_call / tool_result

**Files:**
- Modify: `tinyagentos/bridge/bridge_session.py` (lines 317 and 332 per the audit)
- Test: `tests/test_bridge_session_archive.py`

- [ ] **Step 1: Inspect current bridge event methods**

```bash
grep -n "def.*tool_call\|def.*tool_result\|trace_store\|archive" tinyagentos/bridge/bridge_session.py | head -30
```

Identify the exact methods that handle tool_call and tool_result events and where the trace-store write sits.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_bridge_session_archive.py
from unittest.mock import MagicMock

def test_tool_call_dual_writes_to_archive(monkeypatch, tmp_path):
    from tinyagentos.bridge import bridge_session as bs
    archive = MagicMock()
    trace = MagicMock()
    session = bs.BridgeSession(agent_slug="atlas", trace_store=trace, archive=archive)
    session.record_tool_call(
        session_id="s1", tool="file_write",
        input={"path": "hello.txt"}, output=None,
    )
    trace.append.assert_called_once()
    archive.record.assert_called_once()
    call_kwargs = archive.record.call_args.kwargs
    assert call_kwargs["event_type"] == "tool_call"
    assert call_kwargs["agent_name"] == "atlas"
    assert call_kwargs["data"]["tool"] == "file_write"
```

- [ ] **Step 3: Implementation**

In `BridgeSession.__init__`, accept and stash an `archive` argument (keep None-tolerant for tests that don't pass one). In `record_tool_call` and `record_tool_result`, after the existing trace-store write add:

```python
if self.archive is not None:
    try:
        self.archive.record(
            event_type="tool_call",  # or "tool_result"
            data={
                "tool": tool,
                "input": input,
                "output": output,
                "session_id": session_id,
            },
            agent_name=self.agent_slug,
            summary=f"{tool}({self._summarise_args(input)})",
        )
    except Exception:
        logger.exception("archive dual-write failed (tool_call)")
```

Wire the registry (`BridgeSessionRegistry`) to pass `app.state.archive` to new sessions.

- [ ] **Step 4: Run — expect PASS**

`pytest tests/test_bridge_session_archive.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/bridge/bridge_session.py tests/test_bridge_session_archive.py
git commit -m "feat(bridge): dual-write tool_call/tool_result to archive"
```

---

### Task 2.2: Archive dual-write on bridge error + reasoning

**Files:**
- Modify: `tinyagentos/bridge/bridge_session.py` (line 348 and reasoning-event handler)
- Test: extend `tests/test_bridge_session_archive.py`

- [ ] **Step 1: Extend tests**

Add two tests mirroring Task 2.1 structure for `record_error` and `record_reasoning`. Assert `event_type` matches (`"error"` / `"reasoning"`), `agent_name` correct, payload shape reasonable.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

In `record_error` and the reasoning event handler, mirror the dual-write pattern from Task 2.1.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/bridge/bridge_session.py tests/test_bridge_session_archive.py
git commit -m "feat(bridge): dual-write error/reasoning to archive"
```

---

### Task 2.3: Per-agent enrichment scoping in job_worker

**Files:**
- Modify: `tinyagentos/scheduling/job_worker.py` (line 113 `_do_enrich`)
- Test: `tests/test_job_worker_agent_scope.py`

- [ ] **Step 1: Read `_do_enrich` context**

```bash
sed -n '100,145p' tinyagentos/scheduling/job_worker.py
```

Note the current call signature into `catalog.enrich_session`.

- [ ] **Step 2: Write the failing test**

```python
from unittest.mock import MagicMock
from tinyagentos.scheduling.job_worker import JobWorker

def test_enrich_passes_agent_name_to_catalog(monkeypatch):
    catalog = MagicMock()
    worker = JobWorker.__new__(JobWorker)
    worker._catalog = catalog
    worker._librarian = MagicMock()
    worker._do_enrich({"session_id": "s1", "agent_name": "alice"})
    catalog.enrich_session.assert_called_once()
    kwargs = catalog.enrich_session.call_args.kwargs
    assert kwargs.get("agent_name") == "alice"
```

- [ ] **Step 3: Implementation**

In `_do_enrich`, extract `agent_name` from the job payload and pass it through:

```python
def _do_enrich(self, payload: dict) -> None:
    session_id = payload["session_id"]
    agent_name = payload.get("agent_name")
    self._catalog.enrich_session(session_id, agent_name=agent_name)
```

Then update `SessionCatalog.enrich_session` (in taosmd) to accept `agent_name` and pass it to `Librarian.process`. Since `taosmd` is a git+dep, this change needs to happen upstream in taosmd and the version bumped in `pyproject.toml`. Sub-task:

- Open a PR on the taosmd repo adding `agent_name` kwarg to `enrich_session` and `Librarian.process`. Once merged, bump the taosmd git ref in our `pyproject.toml`.

- [ ] **Step 4: Run — expect PASS**

`pytest tests/test_job_worker_agent_scope.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/scheduling/job_worker.py tests/test_job_worker_agent_scope.py
git commit -m "feat(jobs): pass agent_name to catalog.enrich_session"
```

---

### Task 2.4: Archive smoke-check on deploy

**Files:**
- Modify: `tinyagentos/routes/agents.py` (inside `deploy_agent_endpoint` after container provisioning)
- Test: `tests/test_agents_deploy_smoke.py`

- [ ] **Step 1: Write the failing test**

Use FastAPI `TestClient` with a monkeypatched archive that records calls. Deploy a stub agent; assert the archive received `event_type="agent_deployed"` with `agent_name=<slug>`. Then simulate archive failure and assert the deploy response includes a warning indicator.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

In `deploy_agent_endpoint`, after the existing container provisioning step:

```python
archive = request.app.state.archive
try:
    await archive.record(
        event_type="agent_deployed",
        data={"slug": unique_slug, "framework": body.framework},
        agent_name=unique_slug,
        summary=f"deployed {unique_slug}",
    )
    # Round-trip verification
    rows = await archive.query(agent_name=unique_slug, limit=1)
    smoke_ok = bool(rows)
except Exception:
    logger.exception("archive smoke-check failed for %s", unique_slug)
    smoke_ok = False

# Response includes smoke_ok flag so the UI can show a warning banner in Logs
return {
    "status": "created",
    "name": unique_slug,
    "display_name": display_name,
    "archive_smoke_ok": smoke_ok,
}
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/agents.py tests/test_agents_deploy_smoke.py
git commit -m "feat(agents): archive smoke-check on deploy"
```

---

## Phase 3 — Deploy flow backend

### Task 3.1: Extend DeployAgentRequest with persona fields

**Files:**
- Modify: `tinyagentos/routes/agents.py` (`DeployAgentRequest`, `deploy_agent_endpoint`)
- Test: `tests/test_agents_deploy_persona.py`

- [ ] **Step 1: Write the failing test**

```python
def test_deploy_stores_persona_fields(client, app):
    resp = client.post("/api/agents/deploy", json={
        "name": "Atlas",
        "framework": "openclaw",
        "soul_md": "You are Atlas",
        "agent_md": "Always verify",
        "memory_plugin": "taosmd",
        "source_persona_id": "builtin:research",
    })
    assert resp.status_code == 200
    slug = resp.json()["name"]
    agent = next(a for a in app.state.config.agents if a["name"] == slug)
    assert agent["soul_md"] == "You are Atlas"
    assert agent["agent_md"] == "Always verify"
    assert agent["memory_plugin"] == "taosmd"
    assert agent["source_persona_id"] == "builtin:research"
    assert agent["migrated_to_v2_personas"] is True
    assert agent["display_name"] == "Atlas"

def test_deploy_with_save_to_library_writes_user_persona(client, app):
    resp = client.post("/api/agents/deploy", json={
        "name": "Custom One",
        "framework": "openclaw",
        "soul_md": "Custom soul",
        "agent_md": "",
        "memory_plugin": "taosmd",
        "save_to_library": {"name": "My Custom", "description": "for reuse"},
    })
    assert resp.status_code == 200
    rows = app.state.user_persona_store.list()
    assert any(r["name"] == "My Custom" for r in rows)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

Extend `DeployAgentRequest`:

```python
class DeployAgentRequest(BaseModel):
    name: str
    framework: str = "none"
    model: str | None = None
    color: str = "#888888"
    emoji: str | None = None
    memory_limit: str | None = None
    cpu_limit: int | None = None
    can_read_user_memory: bool = False
    target_worker: str | None = None
    on_worker_failure: str = "pause"
    fallback_models: list[str] = []
    # Persona fields (new)
    soul_md: str = ""
    agent_md: str = ""
    memory_plugin: str = "taosmd"          # Literal["taosmd", "none"] once pydantic>=2 Literal is OK
    source_persona_id: str | None = None
    save_to_library: dict | None = None    # {"name": str, "description": str|None}
```

In `deploy_agent_endpoint`, after computing `unique_slug` and before calling `save_config_locked`, apply the new fields to the `agent` dict:

```python
agent["soul_md"] = body.soul_md
agent["agent_md"] = body.agent_md
agent["memory_plugin"] = body.memory_plugin
agent["source_persona_id"] = body.source_persona_id
agent["migrated_to_v2_personas"] = True
```

If `body.save_to_library`:

```python
if body.save_to_library:
    request.app.state.user_persona_store.create(
        name=body.save_to_library.get("name") or body.name,
        description=body.save_to_library.get("description"),
        soul_md=body.soul_md,
        agent_md=body.agent_md,
    )
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/agents.py tests/test_agents_deploy_persona.py
git commit -m "feat(agents): deploy accepts persona fields and save-to-library"
```

---

### Task 3.2: Call `register_agent(slug)` as deploy step 1

**Files:**
- Modify: `tinyagentos/routes/agents.py` (`deploy_agent_endpoint`)
- Test: extend `tests/test_agents_deploy_persona.py`

- [ ] **Step 1: Add the test**

```python
def test_deploy_registers_agent_with_taosmd(client, app, monkeypatch):
    calls = []
    def fake_register(name):
        calls.append(name)
    import taosmd.agents as tm_agents
    monkeypatch.setattr(tm_agents, "register_agent", fake_register)
    resp = client.post("/api/agents/deploy", json={"name": "Atlas", "framework": "openclaw"})
    assert resp.status_code == 200
    assert calls == ["atlas"]

def test_deploy_aborts_if_register_agent_fails(client, app, monkeypatch):
    def fake_register(name):
        raise RuntimeError("taosmd down")
    import taosmd.agents as tm_agents
    monkeypatch.setattr(tm_agents, "register_agent", fake_register)
    resp = client.post("/api/agents/deploy", json={"name": "Atlas", "framework": "openclaw"})
    assert resp.status_code == 500
    # Agent must not have been added to the config
    assert not any(a["name"] == "atlas" for a in app.state.config.agents)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

In `deploy_agent_endpoint`, after validating name and computing `unique_slug`, and BEFORE appending to `config.agents`:

```python
import taosmd.agents as tm_agents

try:
    tm_agents.register_agent(unique_slug)
except tm_agents.AgentAlreadyRegisteredError:
    pass  # idempotent
except Exception as e:
    logger.exception("register_agent(%s) failed", unique_slug)
    return JSONResponse(
        {"error": f"Could not register agent with taosmd: {e}"},
        status_code=500,
    )
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/agents.py tests/test_agents_deploy_persona.py
git commit -m "feat(agents): register_agent with taosmd as deploy step 1"
```

---

## Phase 4 — Backend APIs

### Task 4.1: PATCH `/api/agents/{slug}/persona`

**Files:**
- Modify: `tinyagentos/routes/agents.py`
- Test: `tests/test_agents_persona_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_patch_persona_updates_both_fields(client, app):
    client.post("/api/agents", json={"name": "Atlas"})
    resp = client.patch("/api/agents/atlas/persona", json={
        "soul_md": "new soul", "agent_md": "new rules",
    })
    assert resp.status_code == 200
    agent = next(a for a in app.state.config.agents if a["name"] == "atlas")
    assert agent["soul_md"] == "new soul"
    assert agent["agent_md"] == "new rules"

def test_patch_persona_partial(client, app):
    client.post("/api/agents", json={"name": "Atlas"})
    client.patch("/api/agents/atlas/persona", json={"soul_md": "set soul"})
    client.patch("/api/agents/atlas/persona", json={"agent_md": "only this"})
    agent = next(a for a in app.state.config.agents if a["name"] == "atlas")
    assert agent["soul_md"] == "set soul"
    assert agent["agent_md"] == "only this"

def test_patch_persona_with_source_updates_provenance(client, app):
    client.post("/api/agents", json={"name": "Atlas"})
    resp = client.patch("/api/agents/atlas/persona", json={
        "soul_md": "swap", "source_persona_id": "builtin:support",
    })
    assert resp.status_code == 200
    agent = next(a for a in app.state.config.agents if a["name"] == "atlas")
    assert agent["source_persona_id"] == "builtin:support"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

```python
class PersonaPatch(BaseModel):
    soul_md: str | None = None
    agent_md: str | None = None
    source_persona_id: str | None = None

@router.patch("/api/agents/{slug}/persona")
async def patch_agent_persona(request: Request, slug: str, body: PersonaPatch):
    config = request.app.state.config
    agent = find_agent(config, slug)
    if not agent:
        return JSONResponse({"error": "agent not found"}, status_code=404)
    if body.soul_md is not None:
        agent["soul_md"] = body.soul_md
    if body.agent_md is not None:
        agent["agent_md"] = body.agent_md
    if body.source_persona_id is not None:
        agent["source_persona_id"] = body.source_persona_id
    await save_config_locked(config, config.config_path)
    return {"status": "ok", "agent": agent}
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/agents.py tests/test_agents_persona_api.py
git commit -m "feat(agents): PATCH /persona endpoint for soul_md and agent_md"
```

---

### Task 4.2: PATCH `/api/agents/{slug}/memory`

**Files:**
- Modify: `tinyagentos/routes/agents.py`
- Test: `tests/test_agents_memory_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_patch_memory_toggles_plugin(client, app):
    client.post("/api/agents", json={"name": "Atlas"})
    resp = client.patch("/api/agents/atlas/memory", json={"memory_plugin": "none"})
    assert resp.status_code == 200
    agent = next(a for a in app.state.config.agents if a["name"] == "atlas")
    assert agent["memory_plugin"] == "none"

def test_patch_memory_rejects_unknown_plugin(client, app):
    client.post("/api/agents", json={"name": "Atlas"})
    resp = client.patch("/api/agents/atlas/memory", json={"memory_plugin": "gandalf"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

```python
_ALLOWED_MEMORY_PLUGINS = {"taosmd", "none"}

class MemoryPatch(BaseModel):
    memory_plugin: str

@router.patch("/api/agents/{slug}/memory")
async def patch_agent_memory(request: Request, slug: str, body: MemoryPatch):
    if body.memory_plugin not in _ALLOWED_MEMORY_PLUGINS:
        return JSONResponse(
            {"error": f"memory_plugin must be one of {sorted(_ALLOWED_MEMORY_PLUGINS)}"},
            status_code=400,
        )
    config = request.app.state.config
    agent = find_agent(config, slug)
    if not agent:
        return JSONResponse({"error": "agent not found"}, status_code=404)
    agent["memory_plugin"] = body.memory_plugin
    await save_config_locked(config, config.config_path)
    return {"status": "ok", "memory_plugin": body.memory_plugin}
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/agents.py tests/test_agents_memory_api.py
git commit -m "feat(agents): PATCH /memory endpoint for memory_plugin toggle"
```

---

### Task 4.3: Per-agent Librarian config endpoints

**Files:**
- Create: `tinyagentos/routes/librarian.py`
- Modify: `tinyagentos/app.py` (register router)
- Test: `tests/test_librarian_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_librarian_returns_upstream_config(client, app, monkeypatch):
    from taosmd.agents import get_librarian as real_get
    calls = []
    def fake_get(name):
        calls.append(name)
        return {"enabled": True, "model": None, "tasks": {}, "fanout": {"default": "low", "auto_scale": True}}
    monkeypatch.setattr("taosmd.agents.get_librarian", fake_get)
    client.post("/api/agents", json={"name": "Atlas"})
    resp = client.get("/api/agents/atlas/librarian")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert calls == ["atlas"]

def test_patch_librarian_forwards_kwargs(client, app, monkeypatch):
    captured = {}
    def fake_set(name, **kwargs):
        captured["name"] = name
        captured.update(kwargs)
        return {"enabled": False, "model": "ollama:qwen3:4b", "tasks": {}, "fanout": {"default": "low", "auto_scale": True}}
    monkeypatch.setattr("taosmd.agents.set_librarian", fake_set)
    client.post("/api/agents", json={"name": "Atlas"})
    resp = client.patch("/api/agents/atlas/librarian", json={
        "enabled": False, "model": "ollama:qwen3:4b",
        "tasks": {"fact_extraction": False}, "fanout": "med",
    })
    assert resp.status_code == 200
    assert captured["name"] == "atlas"
    assert captured["enabled"] is False
    assert captured["model"] == "ollama:qwen3:4b"
    assert captured["tasks"] == {"fact_extraction": False}
    assert captured["fanout"] == "med"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

```python
# tinyagentos/routes/librarian.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import taosmd.agents as tm_agents

router = APIRouter()


class LibrarianPatch(BaseModel):
    enabled: bool | None = None
    model: str | None = None
    clear_model: bool = False
    tasks: dict[str, bool] | None = None
    fanout: str | None = None
    fanout_auto_scale: bool | None = None


@router.get("/api/agents/{slug}/librarian")
async def get_agent_librarian(request: Request, slug: str):
    try:
        cfg = tm_agents.get_librarian(slug)
    except tm_agents.AgentNotFoundError:
        return JSONResponse({"error": "agent not registered"}, status_code=404)
    return cfg


@router.patch("/api/agents/{slug}/librarian")
async def patch_agent_librarian(request: Request, slug: str, body: LibrarianPatch):
    kwargs = body.model_dump(exclude_none=True, exclude={"clear_model"})
    if body.clear_model:
        kwargs["clear_model"] = True
    try:
        cfg = tm_agents.set_librarian(slug, **kwargs)
    except tm_agents.AgentNotFoundError:
        return JSONResponse({"error": "agent not registered"}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return cfg
```

In `tinyagentos/app.py` import and include the router:

```python
from tinyagentos.routes import librarian as librarian_routes
app.include_router(librarian_routes.router)
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/librarian.py tinyagentos/app.py tests/test_librarian_api.py
git commit -m "feat(librarian): per-agent GET/PATCH /librarian endpoints"
```

---

### Task 4.4: User personas CRUD endpoints

**Files:**
- Create: `tinyagentos/routes/user_personas.py`
- Modify: `tinyagentos/app.py` (instantiate store on startup, register router)
- Test: `tests/test_user_personas_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_create_list_get_update_delete_persona(client):
    r1 = client.post("/api/user-personas", json={"name": "X", "soul_md": "S"})
    assert r1.status_code == 200
    pid = r1.json()["id"]
    r2 = client.get("/api/user-personas")
    assert any(p["id"] == pid for p in r2.json()["personas"])
    r3 = client.get(f"/api/user-personas/{pid}")
    assert r3.json()["soul_md"] == "S"
    r4 = client.patch(f"/api/user-personas/{pid}", json={"soul_md": "S2"})
    assert r4.status_code == 200
    assert client.get(f"/api/user-personas/{pid}").json()["soul_md"] == "S2"
    r5 = client.delete(f"/api/user-personas/{pid}")
    assert r5.status_code == 200
    assert client.get(f"/api/user-personas/{pid}").status_code == 404
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

```python
# tinyagentos/routes/user_personas.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class PersonaCreate(BaseModel):
    name: str
    soul_md: str = ""
    agent_md: str = ""
    description: str | None = None


class PersonaUpdate(BaseModel):
    name: str | None = None
    soul_md: str | None = None
    agent_md: str | None = None
    description: str | None = None


@router.get("/api/user-personas")
async def list_personas(request: Request):
    store = request.app.state.user_persona_store
    return {"personas": store.list()}


@router.post("/api/user-personas")
async def create_persona(request: Request, body: PersonaCreate):
    store = request.app.state.user_persona_store
    pid = store.create(**body.model_dump())
    return {"id": pid}


@router.get("/api/user-personas/{pid}")
async def get_persona(request: Request, pid: str):
    store = request.app.state.user_persona_store
    row = store.get(pid)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return row


@router.patch("/api/user-personas/{pid}")
async def update_persona(request: Request, pid: str, body: PersonaUpdate):
    store = request.app.state.user_persona_store
    if not store.get(pid):
        return JSONResponse({"error": "not found"}, status_code=404)
    store.update(pid, **body.model_dump(exclude_none=True))
    return {"status": "ok"}


@router.delete("/api/user-personas/{pid}")
async def delete_persona(request: Request, pid: str):
    store = request.app.state.user_persona_store
    store.delete(pid)
    return {"status": "ok"}
```

In `app.py` (startup section):

```python
from tinyagentos.user_personas import UserPersonaStore
from tinyagentos.routes import user_personas as user_personas_routes

app.state.user_persona_store = UserPersonaStore(data_dir / "user_personas.db")
app.include_router(user_personas_routes.router)
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/user_personas.py tinyagentos/app.py tests/test_user_personas_api.py
git commit -m "feat(personas): CRUD endpoints for user-authored personas"
```

---

### Task 4.5: Aggregated persona library endpoint

**Files:**
- Modify: `tinyagentos/routes/templates.py` (add a `/library` endpoint that unions built-in + awesome-openclaw + prompt-library + user)
- Test: `tests/test_persona_library_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_library_combines_all_sources(client, app):
    client.post("/api/user-personas", json={"name": "Mine", "soul_md": "s"})
    resp = client.get("/api/personas/library?source=user")
    assert resp.status_code == 200
    assert any(p["name"] == "Mine" for p in resp.json()["personas"])

def test_library_source_filter_builtin(client):
    resp = client.get("/api/personas/library?source=builtin")
    assert resp.status_code == 200
    # At least the known built-ins appear
    assert any(p["source"] == "builtin" for p in resp.json()["personas"])
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

Add `/api/personas/library` that paginates, supports search and source filter. Shape returned per entry: `{source, id, name, description, preview}`. Full `soul_md` / `agent_md` only via `/api/personas/library/{source}/{id}` detail fetch (already exists for templates; add user variant).

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/templates.py tests/test_persona_library_api.py
git commit -m "feat(personas): aggregated library endpoint (builtin + external + user)"
```

---

## Phase 5 — Migration (existing agents)

### Task 5.1: Write migration function

**Files:**
- Create: `tinyagentos/migrations/__init__.py`
- Create: `tinyagentos/migrations/persona_v2.py`
- Test: `tests/test_migration_persona_v2.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migration_persona_v2.py
from tinyagentos.migrations.persona_v2 import migrate_agents

def test_migration_adds_persona_fields_to_legacy():
    agents = [
        {"name": "alice", "display_name": "Alice", "framework": "openclaw"},
        {"name": "bob",   "display_name": "Bob",   "framework": "smolagents"},
    ]
    migrate_agents(agents, register_fn=lambda n: None)
    for a in agents:
        assert a["soul_md"] == ""
        assert a["agent_md"] == ""
        assert a["memory_plugin"] == "taosmd"
        assert a["source_persona_id"] is None
        assert a["migrated_to_v2_personas"] is False  # banner should show

def test_migration_is_idempotent():
    agents = [{"name": "alice", "display_name": "Alice"}]
    migrate_agents(agents, register_fn=lambda n: None)
    first = dict(agents[0])
    migrate_agents(agents, register_fn=lambda n: None)
    assert agents[0] == first

def test_migration_calls_register_once_per_agent():
    calls = []
    agents = [{"name": "alice", "display_name": "Alice"}, {"name": "bob", "display_name": "Bob"}]
    migrate_agents(agents, register_fn=calls.append)
    assert sorted(calls) == ["alice", "bob"]

def test_migration_handles_register_already_exists():
    def register_fn(name):
        import taosmd.agents as tm
        raise tm.AgentAlreadyRegisteredError(name)
    agents = [{"name": "alice", "display_name": "Alice"}]
    migrate_agents(agents, register_fn=register_fn)  # should not raise
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

```python
# tinyagentos/migrations/persona_v2.py
"""One-shot migration for persona + memory fields on existing agent records."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def migrate_agents(agents: list[dict], *, register_fn) -> None:
    """Bring each legacy agent dict up to the v2 persona shape.

    ``register_fn`` is ``taosmd.agents.register_agent`` (injected for tests).
    Idempotent: running twice leaves state unchanged.
    """
    import taosmd.agents as tm_agents  # lazy for test injection

    for a in agents:
        # Persona fields default in (don't overwrite existing values).
        a.setdefault("soul_md", "")
        a.setdefault("agent_md", "")
        a.setdefault("memory_plugin", "taosmd")
        a.setdefault("source_persona_id", None)
        a.setdefault("migrated_to_v2_personas", False)
        # display_name fallback
        if "display_name" not in a:
            a["display_name"] = a["name"]
        # Register with taosmd
        try:
            register_fn(a["name"])
        except tm_agents.AgentAlreadyRegisteredError:
            pass
        except Exception:
            logger.exception("register_agent(%s) failed during migration", a["name"])
```

```python
# tinyagentos/migrations/__init__.py
from .persona_v2 import migrate_agents as migrate_persona_v2

__all__ = ["migrate_persona_v2"]
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/migrations/ tests/test_migration_persona_v2.py
git commit -m "feat(migrations): persona_v2 — backfill fields and register legacy agents"
```

---

### Task 5.2: Invoke migration at app startup

**Files:**
- Modify: `tinyagentos/app.py` (startup hook)
- Test: `tests/test_app_startup_migration.py`

- [ ] **Step 1: Write the failing test**

Integration test that loads a config with a legacy agent (no persona fields), starts the app, asserts the agent now has persona fields and that `register_agent` was called.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

In `app.py` inside the startup lifespan:

```python
from tinyagentos.migrations import migrate_persona_v2
import taosmd.agents as tm_agents

migrate_persona_v2(app.state.config.agents, register_fn=tm_agents.register_agent)
await save_config_locked(app.state.config, app.state.config.config_path)
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/app.py tests/test_app_startup_migration.py
git commit -m "feat(app): run persona_v2 migration on startup"
```

---

### Task 5.3: Banner dismiss endpoint

**Files:**
- Modify: `tinyagentos/routes/agents.py`
- Test: `tests/test_banner_dismiss.py`

- [ ] **Step 1: Write the failing test**

```python
def test_dismiss_banner_sets_flag(client, app):
    # Seed legacy agent with flag=False
    app.state.config.agents.append({
        "name": "legacy", "display_name": "Legacy",
        "migrated_to_v2_personas": False,
        "soul_md": "", "agent_md": "",
        "memory_plugin": "taosmd", "source_persona_id": None,
    })
    resp = client.post("/api/agents/legacy/dismiss-migration-banner")
    assert resp.status_code == 200
    agent = next(a for a in app.state.config.agents if a["name"] == "legacy")
    assert agent["migrated_to_v2_personas"] is True
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implementation**

```python
@router.post("/api/agents/{slug}/dismiss-migration-banner")
async def dismiss_migration_banner(request: Request, slug: str):
    config = request.app.state.config
    agent = find_agent(config, slug)
    if not agent:
        return JSONResponse({"error": "agent not found"}, status_code=404)
    agent["migrated_to_v2_personas"] = True
    await save_config_locked(config, config.config_path)
    return {"status": "ok"}
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/agents.py tests/test_banner_dismiss.py
git commit -m "feat(agents): dismiss-migration-banner endpoint"
```

---

## Phase 6 — Deploy wizard UI: Persona step (Step 0)

### Task 6.1: PersonaPicker skeleton

**Files:**
- Create: `desktop/src/components/persona-picker/PersonaPicker.tsx`
- Create: `desktop/src/components/persona-picker/types.ts`

- [ ] **Step 1: Create types**

```typescript
// desktop/src/components/persona-picker/types.ts
export type PersonaSource = "builtin" | "awesome-openclaw" | "prompt-library" | "user";

export interface PersonaSummary {
  source: PersonaSource;
  id: string;
  name: string;
  description?: string;
  preview: string;
}

export interface PersonaSelection {
  kind: "library" | "custom" | "blank";
  // library:
  source_persona_id?: string;
  soul_md: string;
  agent_md: string;
  // custom only:
  save_to_library?: { name: string; description?: string };
}
```

- [ ] **Step 2: Skeleton component**

```tsx
// desktop/src/components/persona-picker/PersonaPicker.tsx
import { useState } from "react";
import { PersonaSelection } from "./types";
import { PersonaBrowse } from "./PersonaBrowse";
import { PersonaCreate } from "./PersonaCreate";
import { PersonaBlank } from "./PersonaBlank";

type Tab = "browse" | "create" | "blank";

export function PersonaPicker({
  onSelect,
}: {
  onSelect: (s: PersonaSelection) => void;
}) {
  const [tab, setTab] = useState<Tab>("browse");
  return (
    <div className="flex flex-col gap-3">
      <div role="tablist" className="flex gap-2 border-b">
        {(["browse", "create", "blank"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 ${tab === t ? "border-b-2 border-blue-400 text-blue-400" : "opacity-60"}`}
          >
            {t === "browse" ? "Browse" : t === "create" ? "Create new" : "Blank"}
          </button>
        ))}
      </div>
      {tab === "browse" && <PersonaBrowse onSelect={onSelect} />}
      {tab === "create" && <PersonaCreate onSelect={onSelect} />}
      {tab === "blank" && <PersonaBlank onSelect={onSelect} />}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add desktop/src/components/persona-picker/
git commit -m "feat(persona-picker): skeleton with three tabs"
```

---

### Task 6.2: Browse tab — list + search + source filter

**Files:**
- Create: `desktop/src/components/persona-picker/PersonaBrowse.tsx`
- Create: `desktop/src/lib/personas-api.ts`

- [ ] **Step 1: API client**

```typescript
// desktop/src/lib/personas-api.ts
import { PersonaSource, PersonaSummary } from "@/components/persona-picker/types";

export async function fetchLibrary(opts: {
  source?: PersonaSource;
  q?: string;
  limit?: number;
  offset?: number;
}) {
  const qs = new URLSearchParams();
  if (opts.source) qs.set("source", opts.source);
  if (opts.q) qs.set("q", opts.q);
  if (opts.limit) qs.set("limit", String(opts.limit));
  if (opts.offset) qs.set("offset", String(opts.offset));
  const res = await fetch(`/api/personas/library?${qs}`);
  const j = await res.json();
  return j.personas as PersonaSummary[];
}

export async function fetchPersonaDetail(source: string, id: string) {
  const res = await fetch(`/api/personas/library/${source}/${encodeURIComponent(id)}`);
  return res.json() as Promise<{ soul_md: string; agent_md?: string; name: string; source: string; id: string }>;
}
```

- [ ] **Step 2: Browse component**

```tsx
// desktop/src/components/persona-picker/PersonaBrowse.tsx
import { useEffect, useState } from "react";
import { PersonaSelection, PersonaSource, PersonaSummary } from "./types";
import { fetchLibrary, fetchPersonaDetail } from "@/lib/personas-api";

export function PersonaBrowse({ onSelect }: { onSelect: (s: PersonaSelection) => void }) {
  const [source, setSource] = useState<PersonaSource | "">("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<PersonaSummary[]>([]);
  const [active, setActive] = useState<PersonaSummary | null>(null);
  const [detail, setDetail] = useState<{ soul_md: string; agent_md?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchLibrary({ source: (source || undefined) as PersonaSource | undefined, q, limit: 50 })
      .then((rows) => { if (!cancelled) { setItems(rows); setError(null); } })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [source, q]);

  useEffect(() => {
    if (!active) { setDetail(null); return; }
    fetchPersonaDetail(active.source, active.id).then(setDetail);
  }, [active]);

  return (
    <div className="grid grid-cols-[260px_1fr] gap-4 h-[420px]">
      <div className="flex flex-col gap-2 overflow-hidden">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search personas…"
          className="border rounded px-2 py-1"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as PersonaSource | "")}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="">All sources</option>
          <option value="builtin">Built-in</option>
          <option value="awesome-openclaw">awesome-openclaw</option>
          <option value="prompt-library">prompt-library</option>
          <option value="user">My library</option>
        </select>
        {error && <div className="text-xs text-red-400">{error}</div>}
        <ul className="overflow-y-auto flex-1">
          {items.map((it) => (
            <li
              key={`${it.source}:${it.id}`}
              onClick={() => setActive(it)}
              className={`px-2 py-1 cursor-pointer ${active?.id === it.id ? "bg-blue-950" : ""}`}
              aria-selected={active?.id === it.id}
            >
              <div className="text-sm">{it.name}</div>
              <div className="text-xs opacity-60">{it.source}</div>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-l pl-4 overflow-auto">
        {!active && <div className="opacity-60 text-sm">Pick a persona to preview.</div>}
        {active && detail && (
          <>
            <h3 className="mb-2">{active.name}</h3>
            <pre className="whitespace-pre-wrap text-xs opacity-80">{detail.soul_md}</pre>
            <button
              onClick={() => onSelect({
                kind: "library",
                source_persona_id: `${active.source}:${active.id}`,
                soul_md: detail.soul_md,
                agent_md: detail.agent_md || "",
              })}
              className="mt-3 bg-blue-600 px-3 py-1.5 rounded text-sm"
            >
              Use this persona
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add desktop/src/components/persona-picker/ desktop/src/lib/personas-api.ts
git commit -m "feat(persona-picker): Browse tab with search and source filter"
```

---

### Task 6.3: Create-new tab

**Files:**
- Create: `desktop/src/components/persona-picker/PersonaCreate.tsx`

- [ ] **Step 1: Component**

```tsx
// desktop/src/components/persona-picker/PersonaCreate.tsx
import { useState } from "react";
import { PersonaSelection } from "./types";

export function PersonaCreate({ onSelect }: { onSelect: (s: PersonaSelection) => void }) {
  const [soul, setSoul] = useState("");
  const [agentMd, setAgentMd] = useState("");
  const [save, setSave] = useState(false);
  const [saveName, setSaveName] = useState("");

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase opacity-60">Soul (identity)</span>
        <textarea
          value={soul}
          onChange={(e) => setSoul(e.target.value)}
          rows={6}
          className="border rounded px-2 py-1 font-mono text-sm"
          placeholder="You are…"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase opacity-60">Agent.md (operational rules)</span>
        <textarea
          value={agentMd}
          onChange={(e) => setAgentMd(e.target.value)}
          rows={5}
          className="border rounded px-2 py-1 font-mono text-sm"
          placeholder="Guardrails, project context, tool guidance…"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} />
        Save to my persona library for reuse
      </label>
      {save && (
        <input
          value={saveName}
          onChange={(e) => setSaveName(e.target.value)}
          placeholder="Name for your library entry"
          className="border rounded px-2 py-1"
        />
      )}
      <button
        disabled={!soul.trim() && !agentMd.trim()}
        onClick={() => onSelect({
          kind: "custom",
          soul_md: soul,
          agent_md: agentMd,
          save_to_library: save ? { name: saveName || "Untitled" } : undefined,
        })}
        className="bg-blue-600 px-3 py-1.5 rounded text-sm disabled:opacity-50"
      >
        Use this persona
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add desktop/src/components/persona-picker/PersonaCreate.tsx
git commit -m "feat(persona-picker): Create-new tab with save-to-library"
```

---

### Task 6.4: Blank tab

**Files:**
- Create: `desktop/src/components/persona-picker/PersonaBlank.tsx`

- [ ] **Step 1: Component**

```tsx
// desktop/src/components/persona-picker/PersonaBlank.tsx
import { PersonaSelection } from "./types";

export function PersonaBlank({ onSelect }: { onSelect: (s: PersonaSelection) => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[320px] gap-3 text-center">
      <p className="opacity-70 max-w-sm">
        Deploy with no persona. You can add one later from the Agent Settings &rarr; Persona tab.
      </p>
      <button
        onClick={() => onSelect({ kind: "blank", soul_md: "", agent_md: "" })}
        className="bg-blue-600 px-4 py-2 rounded"
      >
        Deploy with no persona →
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add desktop/src/components/persona-picker/PersonaBlank.tsx
git commit -m "feat(persona-picker): Blank tab"
```

---

### Task 6.5: Wire PersonaPicker as Step 0 of the deploy wizard

**Files:**
- Modify: `desktop/src/apps/AgentsApp.tsx` (wizard step array, payload assembly, state)

- [ ] **Step 1: Add persona state**

In the deploy wizard component, add:

```tsx
import { PersonaPicker } from "@/components/persona-picker/PersonaPicker";
import type { PersonaSelection } from "@/components/persona-picker/types";

const [persona, setPersona] = useState<PersonaSelection | null>(null);
```

- [ ] **Step 2: Insert as step 0**

Update the wizard step array to include Persona as the first step. Step progresses only when `persona !== null`. The step content:

```tsx
{step === 0 && (
  <PersonaPicker onSelect={(sel) => { setPersona(sel); goNext(); }} />
)}
```

Renumber subsequent steps' indices (Name becomes 1, Framework 2, etc.).

- [ ] **Step 3: Include persona fields in deploy payload**

In the submit handler where `/api/agents/deploy` is called:

```tsx
body: JSON.stringify({
  name,
  framework: selectedFramework,
  model: selectedModel,
  color,
  emoji: emoji.trim() || null,
  memory_limit: memoryLimit,
  cpu_limit: cpus ? parseInt(cpus, 10) : null,
  can_read_user_memory: canReadUserMemory,
  on_worker_failure: onWorkerFailure,
  fallback_models: fallbackModels,
  soul_md: persona?.soul_md ?? "",
  agent_md: persona?.agent_md ?? "",
  source_persona_id: persona?.source_persona_id ?? null,
  save_to_library: persona?.save_to_library ?? null,
})
```

- [ ] **Step 4: Manual smoke**

Start desktop (`npm run dev` or however the repo launches it), walk the wizard, confirm each of the three persona paths reaches deploy and the backend response shows the fields set.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/apps/AgentsApp.tsx
git commit -m "feat(deploy-wizard): persona picker as Step 0"
```

---

## Phase 7 — Deploy wizard UI: Name & emoji

### Task 7.1: Slug preview beneath display_name

**Files:**
- Modify: `desktop/src/apps/AgentsApp.tsx` (Name step)

- [ ] **Step 1: Import slugify**

The backend already has `slugify_agent_name` but the UI needs a parallel client-side slugifier for the live preview. Add:

```tsx
function slugifyClient(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 63);
}
```

Place in `@/lib/slug.ts` so both the wizard and tests can use it.

- [ ] **Step 2: Live preview**

In the Name step, under the input:

```tsx
<div className="text-xs opacity-60 mt-1">
  Slug: <code>{slugifyClient(name) || "—"}</code>{" "}
  <button onClick={() => setEditingSlug(true)} className="text-blue-400">edit</button>
</div>
{editingSlug && (
  <input
    value={customSlug ?? slugifyClient(name)}
    onChange={(e) => setCustomSlug(e.target.value)}
    onBlur={() => setEditingSlug(false)}
    className="border rounded px-2 py-1 mt-1 text-sm"
  />
)}
```

Submit path uses `customSlug || slugifyClient(name)` in the `name` field; the server is unchanged and still validates + handles collisions.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/apps/AgentsApp.tsx desktop/src/lib/slug.ts
git commit -m "feat(deploy-wizard): live slug preview with edit"
```

---

### Task 7.2: Remove framework-default emoji auto-fill

**Files:**
- Modify: `desktop/src/apps/AgentsApp.tsx` (lines 382, 643, 679-681, 1186 per the audit)

- [ ] **Step 1: Delete the auto-fill**

Remove:
- `useState` initialiser `defaultEmojiForFramework("")` at :382 → initial value `""`.
- `setEmoji(defaultEmojiForFramework(""))` at :643 in the reset path → `setEmoji("")`.
- The `useEffect` at :679-681 that re-syncs emoji to framework → delete the whole effect.
- The Review-step fallback at :1186 `emoji.trim() || defaultEmojiForFramework(selectedFramework)` → `emoji.trim() || "—"`.

Do NOT delete `resolveAgentEmoji` usages in the agent list (`:125, :311, :1365`) — they are read-side fallbacks for already-deployed records and must continue to render something when emoji is null.

- [ ] **Step 2: Commit**

```bash
git add desktop/src/apps/AgentsApp.tsx
git commit -m "refactor(deploy-wizard): remove framework-default emoji auto-fill"
```

---

### Task 7.3: Integrate full emoji picker library

**Files:**
- Create: `desktop/src/components/EmojiPicker.tsx`
- Modify: `desktop/package.json` (dependency)
- Modify: `desktop/src/apps/AgentsApp.tsx`

- [ ] **Step 1: Install library**

```bash
cd desktop && npm install emoji-picker-react
```

- [ ] **Step 2: Component wrapper**

```tsx
// desktop/src/components/EmojiPicker.tsx
import { useState } from "react";
import Picker, { EmojiClickData, Theme } from "emoji-picker-react";

export function EmojiPickerField({
  value,
  onChange,
}: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="border rounded w-10 h-10 text-xl flex items-center justify-center"
        aria-label="Open emoji picker"
      >
        {value || "+"}
      </button>
      {open && (
        <div className="absolute z-50 mt-1">
          <Picker
            theme={Theme.DARK}
            onEmojiClick={(d: EmojiClickData) => { onChange(d.emoji); setOpen(false); }}
          />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Replace the quick-pick row in AgentsApp.tsx**

Find the block around line :867 that renders `EMOJI_QUICK_PICKS.map(...)`. Replace with:

```tsx
<EmojiPickerField value={emoji} onChange={setEmoji} />
```

Remove the `EMOJI_QUICK_PICKS` import.

- [ ] **Step 4: Commit**

```bash
git add desktop/package.json desktop/package-lock.json desktop/src/components/EmojiPicker.tsx desktop/src/apps/AgentsApp.tsx
git commit -m "feat(deploy-wizard): integrate full emoji picker library"
```

---

### Task 7.4: Remove obsolete exports

**Files:**
- Modify: `desktop/src/lib/agent-emoji.ts`

- [ ] **Step 1: Grep callers**

```bash
grep -rn "defaultEmojiForFramework\|EMOJI_QUICK_PICKS" desktop/src/
```

If the list is empty after Task 7.2 and 7.3, remove the exports. If any callers remain, note them and defer.

- [ ] **Step 2: Remove**

Delete `defaultEmojiForFramework` and `EMOJI_QUICK_PICKS` definitions and their exports.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/lib/agent-emoji.ts
git commit -m "chore(agent-emoji): remove obsolete defaultEmojiForFramework export"
```

---

## Phase 8 — Agent Settings: Persona tab

### Task 8.1: Persona tab skeleton

**Files:**
- Create: `desktop/src/components/agent-settings/PersonaTab.tsx`
- Modify: `desktop/src/apps/AgentsApp.tsx` (tab bar — insert between Logs and Skills)

- [ ] **Step 1: Component**

```tsx
// desktop/src/components/agent-settings/PersonaTab.tsx
import { useEffect, useState } from "react";

export function PersonaTab({ agent, onUpdated }: { agent: any; onUpdated: () => void }) {
  const [soul, setSoul] = useState(agent.soul_md || "");
  const [agentMd, setAgentMd] = useState(agent.agent_md || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSoul(agent.soul_md || "");
    setAgentMd(agent.agent_md || "");
  }, [agent.name]);

  const save = async () => {
    setSaving(true);
    await fetch(`/api/agents/${agent.name}/persona`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ soul_md: soul, agent_md: agentMd }),
    });
    setSaving(false);
    onUpdated();
  };

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase opacity-60">
          {agent.source_persona_id ? `From: ${agent.source_persona_id}` : (soul || agentMd ? "Custom" : "Blank")}
        </div>
        <button className="text-sm text-blue-400">Swap persona…</button>
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase opacity-60">Soul</span>
        <textarea value={soul} onChange={(e) => setSoul(e.target.value)} rows={10} className="border rounded px-2 py-1 font-mono text-sm" />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase opacity-60">Agent.md — operational rules</span>
        <textarea value={agentMd} onChange={(e) => setAgentMd(e.target.value)} rows={8} className="border rounded px-2 py-1 font-mono text-sm" />
      </label>
      <button disabled={saving} onClick={save} className="self-end bg-blue-600 px-3 py-1.5 rounded text-sm disabled:opacity-50">
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Add tab in AgentsApp.tsx**

Insert `Persona` between `Logs` and `Skills` in the tab bar. Render the component when active.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/components/agent-settings/PersonaTab.tsx desktop/src/apps/AgentsApp.tsx
git commit -m "feat(agent-settings): Persona tab with Soul + Agent.md editors"
```

---

### Task 8.2: Swap-persona flow (reuses PersonaPicker)

**Files:**
- Modify: `desktop/src/components/agent-settings/PersonaTab.tsx`

- [ ] **Step 1: Modal + confirmation**

Reuse `PersonaPicker` in a modal. On selection, show confirmation dialog: "Replace Soul with [name]? Agent.md stays as-is." On confirm, PATCH `soul_md` + `source_persona_id` (do NOT touch `agent_md`).

- [ ] **Step 2: Commit**

```bash
git add desktop/src/components/agent-settings/PersonaTab.tsx
git commit -m "feat(agent-settings): swap persona modal preserves agent_md"
```

---

## Phase 9 — Agent Settings: Memory tab

### Task 9.1: Memory tab skeleton

**Files:**
- Create: `desktop/src/components/agent-settings/MemoryTab.tsx`
- Modify: `desktop/src/apps/AgentsApp.tsx` (tab bar)

- [ ] **Step 1: Component**

```tsx
// desktop/src/components/agent-settings/MemoryTab.tsx
import { useEffect, useState } from "react";

export function MemoryTab({ agent, onUpdated }: { agent: any; onUpdated: () => void }) {
  const [plugin, setPlugin] = useState<string>(agent.memory_plugin || "taosmd");
  const [librarian, setLibrarian] = useState<any>(null);
  const [stats, setStats] = useState<{ notes?: number; edges?: number; lastWrite?: string } | null>(null);
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => {
    fetch(`/api/agents/${agent.name}/librarian`).then((r) => r.json()).then(setLibrarian);
    fetch(`/api/memory/stats?agent=${agent.name}`).then((r) => r.ok ? r.json() : null).then(setStats).catch(() => setStats(null));
  }, [agent.name]);

  const changePlugin = async (p: string) => {
    setPlugin(p);
    await fetch(`/api/agents/${agent.name}/memory`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ memory_plugin: p }),
    });
    onUpdated();
  };

  const patchLib = async (patch: any) => {
    const res = await fetch(`/api/agents/${agent.name}/librarian`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    setLibrarian(await res.json());
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Plugin + description */}
      <section>
        <div className="text-xs uppercase opacity-60 mb-1">Memory plugin</div>
        <select value={plugin} onChange={(e) => changePlugin(e.target.value)} className="border rounded px-2 py-1">
          <option value="taosmd">taOSmd (built-in)</option>
          <option value="none">None</option>
        </select>
        <a href="#store?category=memory" className="ml-3 text-blue-400 text-sm">Get more plugins →</a>
        {plugin === "taosmd" && (
          <p className="text-xs opacity-60 mt-2">
            Persistent memory: knowledge graph, archive, crystal store. Usage contract injected at top of every conversation.
          </p>
        )}
      </section>

      {/* Stats */}
      {plugin === "taosmd" && (
        <section className="grid grid-cols-3 gap-2">
          {[{ label: "Notes", value: stats?.notes ?? "—" },
            { label: "Graph edges", value: stats?.edges ?? "—" },
            { label: "Last write", value: stats?.lastWrite ?? "—" }].map((s) => (
              <div key={s.label} className="bg-blue-950/30 rounded p-2">
                <div className="text-lg font-semibold">{s.value}</div>
                <div className="text-[10px] uppercase opacity-60">{s.label}</div>
              </div>
            ))}
        </section>
      )}

      {/* Librarian */}
      {plugin === "taosmd" && librarian && (
        <section className="border-t pt-4 flex flex-col gap-3">
          <div className="text-xs uppercase opacity-60">Librarian</div>
          <label className="flex items-center justify-between">
            <span>Enable Librarian</span>
            <input
              type="checkbox"
              checked={!!librarian.enabled}
              onChange={(e) => patchLib({ enabled: e.target.checked })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs uppercase opacity-60">Model</span>
            <select
              value={librarian.model ?? ""}
              onChange={(e) => patchLib(e.target.value ? { model: e.target.value } : { clear_model: true })}
              className="border rounded px-2 py-1"
            >
              <option value="">Use install default</option>
              <option value="ollama:qwen3:4b">ollama:qwen3:4b ✓ recommended</option>
              <option value="dulimov/Qwen3-4B-rk3588-1.2.1-base">Qwen3-4B NPU (RK3588)</option>
            </select>
          </label>
          <button onClick={() => setAdvanced((a) => !a)} className="self-start text-sm text-blue-400">
            {advanced ? "Hide advanced" : "Show advanced…"}
          </button>
          {advanced && (
            <div className="flex flex-col gap-2 pl-4 border-l">
              {Object.entries(librarian.tasks || {}).map(([task, enabled]) => (
                <label key={task} className="flex items-center justify-between text-sm">
                  <span>{task}</span>
                  <input type="checkbox" checked={!!enabled} onChange={(e) => patchLib({ tasks: { [task]: e.target.checked } })} />
                </label>
              ))}
              <label className="flex items-center justify-between text-sm">
                <span>Fanout</span>
                <select
                  value={librarian.fanout?.default || "low"}
                  onChange={(e) => patchLib({ fanout: e.target.value })}
                  className="border rounded px-2 py-1 text-sm"
                >
                  {["off", "low", "med", "high"].map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <label className="flex items-center justify-between text-sm">
                <span>Auto-scale</span>
                <input
                  type="checkbox"
                  checked={!!librarian.fanout?.auto_scale}
                  onChange={(e) => patchLib({ fanout_auto_scale: e.target.checked })}
                />
              </label>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire tab**

Insert `Memory` tab between `Persona` and `Skills` in the tab bar.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/components/agent-settings/MemoryTab.tsx desktop/src/apps/AgentsApp.tsx
git commit -m "feat(agent-settings): Memory tab with plugin, stats, Librarian controls"
```

---

### Task 9.2: Hardware-aware recommendation badge

**Files:**
- Create: `desktop/src/lib/hw-detect.ts`
- Modify: `desktop/src/components/agent-settings/MemoryTab.tsx`

- [ ] **Step 1: Detection**

```typescript
// desktop/src/lib/hw-detect.ts
export type HwClass = "rk3588" | "gpu" | "cpu";

let _cached: HwClass | null = null;

export async function detectHwClass(): Promise<HwClass> {
  if (_cached) return _cached;
  const r = await fetch("/api/cluster/workers");
  if (!r.ok) { _cached = "cpu"; return _cached; }
  const workers = await r.json();
  for (const w of workers) {
    if (w.capabilities?.includes("npu:rk3588")) { _cached = "rk3588"; return _cached; }
    if (w.capabilities?.includes("gpu")) { _cached = "gpu"; return _cached; }
  }
  _cached = "cpu";
  return _cached;
}
```

- [ ] **Step 2: Use in MemoryTab**

Wrap the option labels: for `rk3588`, append ✓ recommended to the NPU model; otherwise to `ollama:qwen3:4b`.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/lib/hw-detect.ts desktop/src/components/agent-settings/MemoryTab.tsx
git commit -m "feat(memory-tab): hardware-aware Librarian model recommendation"
```

---

## Phase 10 — Store changes

### Task 10.1: Split Plugins & MCP into two categories

**Files:**
- Modify: `desktop/src/apps/StoreApp.tsx`

- [ ] **Step 1: Edit category constants**

In `StoreApp.tsx` around line 32-45 where `CATEGORIES` is defined, replace the `{ id: "plugin", label: "Plugins & MCP", type: "plugin" }` entry with two entries:

```tsx
{ id: "plugin", label: "Plugins", type: "plugin" },
{ id: "mcp-server", label: "MCP Servers", type: "mcp" },
```

Update the filter predicate that currently routes `type === "mcp"` to the plugin category — send them to `mcp-server` instead.

- [ ] **Step 2: Commit**

```bash
git add desktop/src/apps/StoreApp.tsx
git commit -m "refactor(store): split Plugins & MCP into separate categories"
```

---

### Task 10.2: Memory category

**Files:**
- Modify: `desktop/src/apps/StoreApp.tsx`

- [ ] **Step 1: Add category**

Insert ahead of `Plugins`:

```tsx
{ id: "memory", label: "Memory", type: "memory" },
```

- [ ] **Step 2: Empty state**

When category is `memory` and the filtered list is empty, render:

```tsx
<div className="p-6 text-center opacity-70">
  No third-party memory plugins yet. <b>taOSmd</b> is installed by default and available on every agent.
</div>
```

- [ ] **Step 3: Commit**

```bash
git add desktop/src/apps/StoreApp.tsx
git commit -m "feat(store): Memory category with empty state"
```

---

### Task 10.3: Deep-link support (`?category=memory`)

**Files:**
- Modify: `desktop/src/apps/StoreApp.tsx`

- [ ] **Step 1: Read param on mount**

```tsx
useEffect(() => {
  const qs = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const cat = qs.get("category");
  if (cat) setActiveCategory(cat);
}, []);
```

The "Get more plugins →" link in the Memory tab already points at `#store?category=memory`.

- [ ] **Step 2: Commit**

```bash
git add desktop/src/apps/StoreApp.tsx
git commit -m "feat(store): deep-link via ?category=<id>"
```

---

## Phase 11 — Migration banner (UI)

### Task 11.1: Banner component

**Files:**
- Create: `desktop/src/components/MigrationBanner.tsx`
- Modify: `desktop/src/apps/AgentsApp.tsx` (render banner above agent detail when flag is false)

- [ ] **Step 1: Component**

```tsx
// desktop/src/components/MigrationBanner.tsx
export function MigrationBanner({ agent, onDismiss, onAddPersona }: {
  agent: any;
  onDismiss: () => void;
  onAddPersona: () => void;
}) {
  if (agent.migrated_to_v2_personas) return null;
  return (
    <div className="bg-yellow-950/30 border border-yellow-800 rounded px-3 py-2 flex items-center justify-between">
      <span className="text-sm">
        Memory upgraded — this agent now knows how to use taOSmd. Add a persona to give it character.
      </span>
      <div className="flex gap-2">
        <button onClick={onAddPersona} className="text-blue-400 text-sm">Add persona →</button>
        <button onClick={onDismiss} className="opacity-60 text-sm">Dismiss</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Hook up dismiss**

On dismiss or Add-persona click, POST `/api/agents/{slug}/dismiss-migration-banner`. Then refetch the agent so the flag flips and the banner disappears.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/components/MigrationBanner.tsx desktop/src/apps/AgentsApp.tsx
git commit -m "feat(migration): one-time banner for legacy agents"
```

---

## Phase 12 — Playwright E2E

Each test runs the desktop app against a test backend seeded with known data. Assume an existing helper `setupTestEnv()` that starts server + desktop and returns a Playwright `Page`.

### Task 12.1: Three deploy paths

**File:** `desktop/tests/e2e/persona-deploy.spec.ts`

- [ ] **Step 1: Write the test**

Three tests:
1. **Browse → built-in.** Click Browse tab, search "research", click first result, click "Use this persona", complete Name/Framework/Model/Review, submit. Assert new agent has `soul_md` containing a known fragment.
2. **Create new + save.** Click Create, type into Soul + Agent.md, tick save-to-library, name it, submit. Assert agent + `user_personas` entry both exist.
3. **Blank.** Click Blank tab, click deploy-with-no-persona, complete wizard, submit. Assert agent has empty `soul_md` and `agent_md`.

- [ ] **Step 2: Commit**

```bash
git add desktop/tests/e2e/persona-deploy.spec.ts
git commit -m "test(e2e): persona deploy three-path coverage"
```

---

### Task 12.2: Slug preview + validation

**File:** `desktop/tests/e2e/deploy-slug.spec.ts`

- [ ] Type "Atlas Researcher" → slug shows "atlas-researcher". Click edit, change to "foo bar" → validation error. Change to "foo-bar" → passes.
- [ ] Commit with `test(e2e): slug live-preview + edit + validation`.

---

### Task 12.3: Memory tab toggles

**File:** `desktop/tests/e2e/agent-settings-memory.spec.ts`

- [ ] Deploy an agent. Open Settings → Memory. Toggle Librarian off → assert API PATCH sent. Change model to `ollama:qwen3:4b` → assert. Expand advanced → toggle `fact_extraction` off → assert. Change fanout to `med` → assert.
- [ ] Commit with `test(e2e): Memory tab Librarian controls`.

---

### Task 12.4: Store deep-link

**File:** `desktop/tests/e2e/store-memory-category.spec.ts`

- [ ] From Memory tab, click "Get more plugins →". Assert Store is open with Memory category active. Assert empty-state copy is visible.
- [ ] Commit with `test(e2e): store memory category deep-link`.

---

### Task 12.5: Migration banner

**File:** `desktop/tests/e2e/migration-banner.spec.ts`

- [ ] Seed a config with a legacy agent (no persona fields). Start app. Assert banner visible on that agent's settings. Click Dismiss. Reload. Assert banner no longer visible.
- [ ] Commit with `test(e2e): migration banner appears once and dismisses`.

---

### Task 12.6: Emoji picker

**File:** `desktop/tests/e2e/emoji-picker.spec.ts`

- [ ] In deploy wizard, open emoji picker, search "rocket", click 🚀, confirm the button now shows the rocket. Leave blank and verify Review shows `—`.
- [ ] Commit with `test(e2e): emoji picker opens searches selects and empty`.

---

## Self-review checklist (run before handing off)

- [ ] **Spec coverage.** Walk each section of the spec and point at a Task.
  - §Data model → Tasks 1.1, 1.5
  - §System prompt assembly → Tasks 1.2, 1.3
  - §Deploy wizard → Tasks 6.1–6.5, 7.1–7.4, 3.1, 3.2
  - §Persona tab → Tasks 8.1, 8.2
  - §Memory tab → Tasks 9.1, 9.2, 4.2, 4.3
  - §Store → Tasks 10.1, 10.2, 10.3
  - §Migration → Tasks 5.1, 5.2, 5.3, 11.1
  - §Trace capture → Tasks 2.1, 2.2, 2.3, 2.4
  - §Error handling → Each task's FAIL paths + the archive smoke-check warning banner
  - §Testing → Phase 12 (Playwright) + unit tests per task

- [ ] **Placeholder scan.** Grep `TBD|TODO|implement later|similar to Task` in the plan — none expected.

- [ ] **Type consistency.** `soul_md`, `agent_md`, `memory_plugin`, `source_persona_id`, `migrated_to_v2_personas` used consistently across backend and frontend.

---

## Open questions at execution time

- ~~**Upstream dependency (Task 2.3):** `agent_name` kwarg in `enrich_session` / `Librarian.process`.~~ ✅ Closed — taosmd #21, landed on master, pin bumped in `pyproject.toml` (commit `b085f12`).
- ~~**Upstream dependency (Task 1.2):** Ship `docs/agent-rules.md` as package data.~~ ✅ Closed — taosmd #22, landed on master. Follow-up in Task 1.2: switch `_load_agent_rules` from `Path(taosmd.__file__).parent.parent` walk to `importlib.resources.files("taosmd").joinpath("docs/agent-rules.md")` so wheel installs work. Small task, track separately.
- **Files app visibility (separate spec):** Investigation found openclaw agents DO write files successfully (into container rootfs, not the host). Files app reads `{data_dir}/agent-workspaces/{slug}` which is never populated under the snapshot model. Fix: replace `_get_agent_workspace_root` with `incus file list/pull` via `exec_in_container` (pattern already used by `routes/recycle.py`). Not part of this plan — separate small spec+plan after this completes.
- **Openclaw skills_mcp_url null:** Orthogonal; first investigation concluded agents have no tools but follow-up proved they have native openclaw tools (Write/Read/Bash/etc.). `skills_mcp_url = null` only means taOS's hosted skills aren't injected. Non-blocking for this plan; revisit if any task needs taOS-hosted skills injected.
