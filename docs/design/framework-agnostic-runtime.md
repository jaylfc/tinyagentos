# Framework-Agnostic Runtime

**Status:** Active — load-bearing architectural rule. All container, agent, and
service work must honour it. Supersedes any previous pattern that baked state
into a container image.

The rule that makes TinyAgentOS a platform instead of a framework:

> **Containers hold code. Hosts hold state.**

Everything else — framework swap, container upgrade, agent cloning, backup,
fresh-install test, cluster dispatch — falls out of this cleanly. If a design
decision conflicts with this rule, the rule wins.

## The rule, stated precisely

An agent container is allowed to contain:

- The base OS (Debian bookworm, Alpine, whatever)
- The agent framework (LangChain, Autogen, CrewAI, a bespoke loop, anything)
- Framework runtime dependencies (Python venv, node_modules, compiled binaries)
- Read-only configuration that's known at deploy time (ports, endpoints, the
  agent's own identity)

An agent container must **not** contain:

- Per-agent memory (chat history, embeddings, vector stores, retrieved facts)
- The user's workspace or any files the agent has produced
- Secrets or API credentials
- Cached embeddings or trained weights produced at runtime
- SQLite databases of any kind
- Tool state (browser profiles, shell history, MCP server state)
- Anything a user would lose sleep over losing

If you can't throw the container away, rebuild the image from scratch, and
bring the agent back up with **zero user-visible state loss**, the rule is
being violated and the violation is a bug.

## Why

**Framework swap on the fly.** If a user wants to move their "Research Assistant"
agent from LangChain to Autogen, the flow is: stop container, change the
`framework:` field in the agent config, start a new container against the same
mounts. The agent retains every memory, every embedded doc, every workspace
file, every secret grant. The framework is a costume, not the person.

**Container upgrade is free.** When we release a new base image with a security
fix, users `taos update` and every agent container is rebuilt from a fresh image
overnight. State is untouched because it was never in the image.

**Backups are a single rsync.** Back up `/data/` on the host and you've backed
up every agent. No container snapshots, no layered image exports, no
per-framework export format.

**Cluster dispatch is coherent.** An agent running on worker A can migrate to
worker B with zero data transfer if the host mounts are network-backed (NFS,
Tailscale-shared FUSE, whatever). The container is ephemeral; the state is the
identity.

**Memory is embedder-agnostic.** If we later swap QMD for sqlite-vec, or
upgrade the embedding model, we re-embed once on the host side and every agent
container keeps working without knowing anything changed.

## Current state vs. the rule

Audit as of **2026-04-11**. Pass = aligned with rule. Fail = needs migration.

| Concern | Where it lives today | Verdict |
|---|---|---|
| LLM chat routing | LiteLLM proxy on host, containers call via injected `OPENAI_BASE_URL` | **Pass** |
| Skills / MCP tools | Skill MCP server on host, containers call via injected `TAOS_SKILLS_URL` | **Pass** |
| User memory | SQLite on host (`data/user_memory.db`), containers call via `TAOS_USER_MEMORY_URL` | **Pass** |
| Agent-to-agent messages | SQLite on host (`data/agent_messages.db`) | **Pass** |
| Secrets | SQLite on host (`data/secrets.db`), agents fetch via API on demand | **Pass** |
| Workspace files | `/data/agent-workspaces/{name}` mounted into Docker containers at `/workspace` | **Pass (Docker only)** |
| Agent memory dir | `/data/agent-memory/{name}` mounted into Docker containers at `/memory` | **Pass (Docker only)** |
| QMD embedding + index service | Single host `qmd.service` systemd unit on :7832 routing per-tenant via `dbPath` | **Pass** |
| Per-agent memory isolation | `data/agent-memory/{name}/index.sqlite` mounted at `/memory`, addressed by dbPath | **Pass** |
| LiteLLM `/v1/embeddings` | Auto-discovers ollama-compatible backends, exposes `taos-embedding-default` alias | **Pass** |
| LXC container mounts | LXC backend now attaches `/workspace` and `/memory` via incus disk devices | **Pass** |
| Skills executor workspace | Resolved per-agent from `app.state.agent_workspaces_dir` | **Pass** |
| Container upgrade / framework swap | Runbooks in `docs/runbooks/`, automated test pending | **Gap** |

## Migration — what changes

### 1. Move QMD out of the container

One QMD process runs on the host, managed by systemd as ``qmd.service``.
It exposes the model-side primitives (``/embed``, ``/embed-batch``,
``/rerank``, ``/expand``, ``/tokenize``) plus the index-side endpoints
(``/search``, ``/vsearch``, ``/browse``, ``/collections``, ``/status``,
``/ingest``, ``/delete-chunk``).

**Per-tenant routing.** Every index endpoint accepts an optional
``dbPath`` (query param for GET, body field for POST) that selects
which SQLite file to operate on. One serve process can host many
tenant indexes — TinyAgentOS uses this to give every agent its own
memory file at ``data/agent-memory/{name}/index.sqlite`` while
keeping the user's personal index (``~/.cache/qmd/index.sqlite``) as
the default. Stores are opened lazily on first use and cached for
the process lifetime.

The user's index and each agent's index are fully isolated: Agent A
cannot search, browse, or delete from Agent B's memory, and the
user's memory is invisible to agents unless they have an explicit
``can_read_user_memory`` grant. This is the load-bearing piece of
per-agent privacy and the reason ingestion, search, browse,
collection listing, and chunk deletion all thread the calling
``agent`` through ``_agent_db_path`` in
``tinyagentos/routes/memory.py``.

LiteLLM also exposes an OpenAI-compatible ``/v1/embeddings`` endpoint
that routes to the same backends, so frameworks consuming the OpenAI
embeddings API work unchanged. Every agent container gets:

```
OPENAI_BASE_URL=http://host.docker.internal:4000/v1
TAOS_EMBEDDING_URL=http://host.docker.internal:4000/v1/embeddings
TAOS_EMBEDDING_MODEL=taos-embedding-default
```

Frameworks that want a native embedder shim against
``TAOS_EMBEDDING_URL``; everything else just sees an OpenAI endpoint
and Just Works.

This removes the ``npm install qmd`` step from ``deployer.py`` and
the per-container systemd unit generation. The deployer gets smaller,
not larger.

**Unblocks:** #29 (memory retrieval through scheduler), #30 (LLM chat
through scheduler — already mostly wired, this makes the embedding
half possible).

### 2. Close the LXC mount gap

`tinyagentos/containers/lxc.py` must mount the same paths Docker does:

- `/data/agent-workspaces/{name}` → `/workspace`
- `/data/agent-memory/{name}` → `/memory`

Plus whatever new mounts the QMD migration introduces (likely none — the host
endpoint is reached over the network, not the filesystem).

Without this, LXC containers violate the rule by default and we can't honestly
claim "containers hold code". Fix before the LXC backend is shipped to users.

### 3. Remove the `/tmp/agent-workspace` hardcode

`tinyagentos/skill_exec.py:43,62` currently writes skill execution artefacts to
`/tmp/agent-workspace`, which is ephemeral and shared across invocations. Route
skill execution through the calling agent's mounted `/workspace` instead, keyed
by agent name. This is a correctness bug even before the rule — two agents
executing skills concurrently today will stomp each other's files.

### 4. Document and test the framework swap path

`docs/runbooks/framework-swap.md` (new): the exact steps to change a running
agent's framework. Must include:

1. Stop the container (`taos agent stop foo`).
2. Edit `agents/foo.yaml`, change `framework: langchain` to `framework: autogen`.
3. Start the agent (`taos agent start foo`).
4. Verify the agent has access to the same memory, workspace, and secrets.

Plus an automated test that runs this flow against a dummy agent and asserts
memory contents survive the swap. This test is the single best proof that the
rule actually holds.

### 5. Document and test the container upgrade path

Same idea, different runbook: `docs/runbooks/container-upgrade.md`. Rebuild the
image from scratch, re-launch the container, assert zero state loss. Worth
wiring into the fresh-install test (#2) once that's unblocked.

## Per-agent home (new)

Every container gets `/root` bind-mounted from `{data_dir}/agent-home/{slug}/` on the host. Framework configs (`~/.config/*`, `~/.local/share/*`), shell dotfiles, caches, and any code the agent clones live there, so:

- Destroying and rebuilding the container from the image loses no user state.
- Archiving the agent is just moving `agent-home/{slug}/` (plus the existing workspace and memory dirs) into an archive bucket.
- Cross-agent file sharing in the future is a symlink or overlay mount from another agent's `agent-home/`, no new plumbing needed.

The container also sees `TAOS_AGENT_HOME=/root` so runtimes can write to a well-known path.

## Rule application checklist (for future changes)

When adding a new feature that touches an agent container, answer these
before merging:

1. Does this add any new state that lives inside the container? If yes, where
   should it live on the host instead?
2. How is this state reached from inside the container — mount, injected env
   var pointing at a host service, or host API callback?
3. If the container is destroyed and rebuilt, does the feature come back
   identically without manual intervention?
4. If the user swaps the framework, does the feature come back identically?
5. Is there a test that proves #3 and #4, or is that being added alongside
   this change?

A "no" on any of these is a conversation, not necessarily a block — but it
needs to be surfaced in the PR, not discovered a year later when the upgrade
path breaks.

## Related

- `docs/design/model-torrent-mesh.md` — model weights distribution (host-side
  concern; containers don't hold weights either)
- `docs/design/cluster-dispatch.md` — migrating agents across workers (the rule
  makes this almost free)
- `docs/superpowers/specs/2026-04-11-taos-framework-integration-bridge-design.md`
  — TAOS Framework Integration Bridge: the concrete design for routing an
  OpenClaw agent through Hermes and back, enabled by this rule
- Issues #29, #30, #32, #33, #34 — backend-driven scheduler wiring, the
  reason this cleanup unblocks real work
