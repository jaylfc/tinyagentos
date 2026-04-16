# openclaw install script

`install.sh` runs once inside a fresh Debian bookworm LXC container to set up the minimal openclaw agent runtime.

## What it does

1. Creates `/opt/openclaw` and a Python venv there.
2. Pip-installs `fastapi`, `uvicorn`, `httpx`, and `openai` (pinned versions for reproducible arm64 builds).
3. Writes `/opt/openclaw/server.py` — a FastAPI app that proxies messages to the host LiteLLM proxy.
4. Installs and starts `openclaw.service` via systemd.
5. Polls `http://127.0.0.1:8100/health` for up to 20 seconds before declaring success.

## Port and endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness probe — returns `{"status":"ok"}` |
| `/message` | POST | Chat — body `{"text":"...", "from":"..."}`, returns `{"content":"..."}` |

## Env vars consumed (injected by the deployer)

| Var | Purpose |
|---|---|
| `TAOS_AGENT_NAME` | Agent display name |
| `TAOS_MODEL` | Model ID passed to LiteLLM |
| `OPENAI_BASE_URL` | LiteLLM `/v1` root on the host |
| `OPENAI_API_KEY` | Per-agent virtual key from LiteLLM |

## Debugging

SSH into the container and check the service log:

```bash
incus exec taos-agent-<name> bash
journalctl -u openclaw -f
```

Re-run the health check manually:

```bash
curl http://127.0.0.1:8100/health
```
