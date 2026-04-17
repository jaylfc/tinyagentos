# Runbook: Agent Archive, Restore, and Purge

**Audience:** taOS admins and power users operating via the local API.
**Auth:** all examples use the local token. Adapt if you have a browser session.

---

## When to use this

- **Archive a misbehaving agent** — stop it cleanly and preserve history for
  post-mortem, without hard-deleting anything.
- **Free resources without losing history** — archive stops the container and
  frees RAM/CPU. The workspace, memory, and trace data are all preserved.
- **Clone an agent** — archive the original, restore it under a new name
  (slug collision handling gives you `foo-2` automatically), then restore the
  original too if you want both.
- **Roll back a bad deploy** — archive the broken agent and restore from an
  earlier archive bucket.

---

## Archive flow

`DELETE /api/agents/{slug}` archives instead of hard-deleting. The container
is stopped and renamed to `taos-archived-{slug}-{timestamp}`. The home,
workspace, and memory directories are moved under
`data/archive/{slug}-{timestamp}/`. The LiteLLM key is revoked. The DM
channel is flagged archived. The config entry moves from `agents` to
`archived_agents`.

```bash
curl -s -X DELETE http://127.0.0.1:6969/api/agents/<slug> \
  -H "Authorization: Bearer $(cat data/.auth_local_token)"
```

Expected response on success:

```json
{
  "status": "archived",
  "name": "my-agent",
  "id": "a1b2c3d4e5f6",
  "archived_at": "20260416T143022",
  "container": "taos-archived-my-agent-20260416T143022",
  "container_renamed": true
}
```

`container_renamed: false` means the container did not exist before the
archive (e.g. a partial deploy). That is not an error — directories and
config are still moved correctly.

**What happens on the host:**

```
data/
  archive/
    my-agent-20260416T143022/
      home/       ← was agent-home/my-agent/  (includes .taos/trace/)
      workspace/  ← was agent-workspaces/my-agent/
      memory/     ← was agent-memory/my-agent/
```

The incus container is renamed to `taos-archived-my-agent-20260416T143022`
and left stopped.

---

## Listing archives

```bash
curl -s http://127.0.0.1:6969/api/agents/archived \
  -H "Authorization: Bearer $(cat data/.auth_local_token)" | jq
```

Each entry contains `id`, `archived_at`, `archived_slug`,
`archive_container`, `archive_dir`, and an `original` snapshot of the agent
config at archive time.

---

## Restore flow

```bash
curl -s -X POST \
  http://127.0.0.1:6969/api/agents/archived/<archive_id>/restore \
  -H "Authorization: Bearer $(cat data/.auth_local_token)"
```

Expected response on success:

```json
{
  "status": "restored",
  "id": "a1b2c3d4e5f6",
  "name": "my-agent",
  "display_name": "My Agent",
  "container_renamed": true,
  "new_llm_key": true
}
```

**What restore does:**

1. Resolves slug collision — if `my-agent` already exists as a live agent,
   the restored agent gets `my-agent-2`, then `my-agent-3`, and so on.
2. Renames the archived container back to `taos-agent-{final_slug}`.
3. Moves the home, workspace, and memory directories back to their standard
   locations under `agent-home/`, `agent-workspaces/`, `agent-memory/`.
4. Mints a new LiteLLM key (the old one was revoked at archive time).
5. Writes the new key into `agent-home/{slug}/.openclaw/env` via
   `tinyagentos/agent_env.py::update_agent_env_file`. No framework reinstall
   is needed — only `OPENAI_API_KEY` is updated; all other env vars survive.
6. Unflags the DM channel.
7. Adds the agent back to `config.agents` with `status: stopped`.

The agent is **not** auto-started. Start it manually after verifying state:

```bash
curl -s -X POST http://127.0.0.1:6969/api/agents/<slug>/start \
  -H "Authorization: Bearer $(cat data/.auth_local_token)"
```

---

## Purge flow

Purge is permanent. There is no undo.

```bash
curl -s -X DELETE \
  http://127.0.0.1:6969/api/agents/archived/<archive_id> \
  -H "Authorization: Bearer $(cat data/.auth_local_token)"
```

Expected response:

```json
{"status": "purged", "id": "a1b2c3d4e5f6"}
```

**What purge destroys:**

- The archived container (force-stopped and deleted via `incus delete --force`).
- The entire `data/archive/{slug}-{timestamp}/` directory tree, including
  the home folder with all trace history, workspace files, and memory index.
- The DM channel and its message history.

**You lose:** every trace event, every workspace file, every embedded memory
chunk, and the chat history for this agent. There is no recovery path.

---

## Failure modes and troubleshooting

**Archive returns 500 "could not rename container".**
The container was running when the rename was attempted and the force-stop did
not take effect in time. Restart taOS (`systemctl restart tinyagentos`), then
retry the archive. If the container is stuck, use `incus stop <name> --force`
directly and retry.

**Archive succeeds but `container_renamed: false`.**
The container did not exist (partial deploy, or manually deleted earlier). Not
an error. Directories and config were still moved correctly.

**Restore succeeds but agent stays at `status: stopped`.**
Expected. Always start the agent explicitly after restore; auto-start would
surprise users who are inspecting state before trusting the restored container.

**Restore returns 500 "Archive entry is corrupted (no slug)".**
The archive entry in `config.yaml` is missing `archived_slug` and the
`original.name` field. This should not occur under normal operation — file a
bug with the raw archive entry from `GET /api/agents/archived`.

**Archive dir collision (timestamp collision).**
Two archives of the same agent within the same UTC second share a bucket key.
This is rare (the timestamp is to-the-second). If it occurs, the second
archive's `shutil.move` will fail with a directory-already-exists error logged
at WARNING level. The config entry will still be moved to `archived_agents`.
Fix manually: rename one of the two archive buckets on disk and update the
`archive_dir` field in `config.yaml` accordingly.

**Container name conflict on restore.**
By design the restore endpoint resolves slug collisions before renaming the
container. A `taos-agent-{slug}` name collision at the incus layer after the
slug check would indicate a race or a manually-created container with that
name. If it happens, file a bug — the endpoint should not leave the system in
a half-restored state.

---

## Related

- `docs/design/framework-agnostic-runtime.md` — "Agent archive / restore"
  section for the design rationale
- `tinyagentos/routes/agents.py` — `_archive_agent_fully`,
  `restore_archived_agent`, `purge_archived_agent`
- `tinyagentos/agent_env.py` — env file rewrite on restore
