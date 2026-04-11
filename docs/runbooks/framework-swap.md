# Framework Swap

**Goal:** change the framework a running agent uses — LangChain to Autogen,
Autogen to CrewAI, CrewAI to a bespoke loop — without losing a single byte of
the agent's memory, workspace, secrets, or conversation history.

This runbook is the operational face of the
[framework-agnostic runtime rule](../design/framework-agnostic-runtime.md).
If this runbook stops working, the rule has been violated somewhere and the
violation is a bug.

## Pre-flight

Before swapping, confirm the following — they should be true of every agent
produced by `taos agent deploy`, but a one-second check costs nothing:

1. `data/agent-workspaces/{name}/` exists on the host and contains the
   agent's files.
2. `data/agent-memory/{name}/` exists on the host. This is what the
   container sees at `/memory`.
3. The target framework is present in the catalog
   (`GET /api/catalog/apps?type=agent-framework`) or is a raw pip-installable
   package name.

## Procedure

```bash
# 1. Stop the running container. State on disk is untouched.
taos agent stop my-research-agent

# 2. Destroy the container. Only the container is destroyed — the mounted
#    /workspace and /memory directories survive because they live on the
#    host, not inside the container image.
taos agent undeploy my-research-agent

# 3. Redeploy with the new framework. The deployer bind-mounts the existing
#    workspace and memory directories into the new container, so the agent
#    wakes up with every previous memory intact.
taos agent deploy \
    --name my-research-agent \
    --framework autogen \
    --model qwen3-4b-q4 \
    --memory-limit 2GB

# 4. Verify the agent retains its state.
taos agent exec my-research-agent -- ls /workspace
taos agent exec my-research-agent -- ls /memory
```

The deploy in step 3 is identical to a first-time deploy. The deployer
doesn't know (or care) that this name previously existed — it creates the
host-side directories if missing (idempotent) and mounts them into the new
container. That's what makes this operation free.

## What carries over

| Thing | Carries? | Why |
|---|---|---|
| Workspace files | **Yes** | Lives in `data/agent-workspaces/{name}/`, mounted |
| Vector store / embeddings | **Yes** | Lives in `data/agent-memory/{name}/`, mounted |
| User memory grants | **Yes** | Lives in `data/user_memory.db` on host, agent reaches it via `TAOS_USER_MEMORY_URL` |
| Secret grants | **Yes** | Lives in `data/secrets.db` on host, agent fetches via API |
| Skill assignments | **Yes** | Lives in `data/skills.db` on host, agent reaches them via `TAOS_SKILLS_URL` |
| Chat / conversation history | **Yes** | Lives in `data/chat.db` on host |
| Agent-to-agent messages | **Yes** | Lives in `data/agent_messages.db` on host |
| LLM proxy API key | **No** | Rotated on deploy — new key minted, old key revoked |
| In-flight pip install cache | **No** | Container-local, expected to vanish |
| Framework-specific ephemeral state | **No** | That's the point — the new framework is a clean slate |

## What does NOT carry over, and why that's usually fine

- **In-memory conversation**. If the agent was mid-conversation, the mid-
  conversation buffer is lost. The persisted chat history in `data/chat.db`
  is untouched, so the agent can resume by re-reading the last N messages.
- **Framework-specific prompt / tool shims**. If the old framework was
  LangChain and used `langchain.agents.Tool` objects, the new framework
  will re-register tools against its own wrappers. This is the intended
  behaviour — shims are code, not state.
- **Container-local caches** (`~/.cache/pip`, `node_modules`, etc). These
  are rebuilt on deploy. Cost: ~60-180 seconds depending on framework.

## Troubleshooting

**"Agent starts with empty memory"**: the mount didn't land. Check
`incus config device show taos-agent-{name}` (LXC) or `docker inspect
taos-agent-{name}` (Docker) for the `/workspace` and `/memory` mounts. If
they're missing, the deployer wasn't given `data_dir` — this is a bug,
file an issue.

**"Agent can't reach the LLM proxy"**: the `OPENAI_BASE_URL` env var
wasn't injected. Check with `taos agent exec {name} -- env | grep OPENAI`.
If empty, the host-side LiteLLM proxy was likely down during deploy.
Restart the service and redeploy.

**"Embedding calls fail"**: the host-side LiteLLM proxy doesn't have an
embedding model configured. See
[framework-agnostic-runtime.md](../design/framework-agnostic-runtime.md)
and [model-torrent-mesh.md](../design/model-torrent-mesh.md) — add an
embedding model to the catalog and LiteLLM config, then redeploy (or
just restart the agent, since `TAOS_EMBEDDING_URL` is the same).

## Test

An automated test of this runbook lives at
`tests/test_framework_swap.py`. It deploys an agent with framework A,
writes a file into `/workspace`, destroys the container, redeploys with
framework B, and asserts the file is still there. If that test breaks,
this runbook is lying.
