# MCP App — Design Spec

## Overview

Add a new platform app called **MCP** for managing Model Context Protocol servers that users have installed from the Store. Think "the Agents app, but for MCP servers".

## Problem

taOS already ships 43 MCP plugins in the Store (filesystem, git, fetch, github, slack, supabase, etc.). Users can install them but there's no UI to manage what's actually running, inspect logs, start/stop, configure env vars, or see which agents are using a given server. Today they'd have to edit YAML files by hand.

## Design

### App registration

Registry entry:
- `id: "mcp"`
- `name: "MCP"` (or "MCP Servers")
- `icon: "plug"` (or similar)
- `category: "platform"`
- `pinned: false`, `launchpadOrder: 9.5`

### Layout

Split-view via `MobileSplitView` — list on the left, detail on the right.

**List (grouped by status):**
- **Running** — servers actively connected with a green dot
- **Stopped** — installed but not running, grey dot
- **Failed** — crashed / error state, red dot
- **Installing / Updating** — spinner

Each row shows:
- Icon (from catalog)
- Server name
- Transport type badge (stdio / http / ws)
- Small text: last activity, PID, memory usage

**Detail (when a server is selected):**
- **Status header** — big status pill, start/stop/restart buttons, uninstall (dangerous)
- **Description** — what the server does, from catalog metadata
- **Capabilities** — tools/prompts/resources the server exposes, with counts
- **Environment** — editable env vars (API keys, etc.), secured via SecretsStore integration
- **Config** — JSON editor for custom config overrides
- **Logs** — live tail of stdout/stderr, colour-coded errors, copyable
- **Used by** — list of agents currently using this server, with tap-through
- **Usage metrics** — requests served, avg response time, error rate (where instrumentation exists)

### Install flow

**Empty state** — if no servers installed: large "Install from Store" button that opens Store filtered to `type=mcp`.

**In-detail install button** — "Add to an agent" opens a picker listing all agents; selecting one adds this MCP server to that agent's config and hot-reloads.

### Backend

Builds on existing MCP plugin infrastructure:
- `tinyagentos/mcp/` — existing plugin catalog, runtime supervisor
- Add/extend `/api/mcp/servers` → list installed servers with status
- `/api/mcp/servers/{id}/start` `/stop` `/restart`
- `/api/mcp/servers/{id}/logs?since=<ts>&limit=1000`
- `/api/mcp/servers/{id}/config` — GET/PUT
- `/api/mcp/servers/{id}/env` — GET/PUT (delegates to SecretsStore)

Runtime state (PID, started_at, logs) is tracked in memory on the controller — no persistence needed beyond the catalog/config files that already exist.

### Mobile

Same split-view pattern as other refactored apps:
- List fills on mobile, tap → slides to detail
- Detail shows status pill + action buttons inline (full-width on mobile)
- Logs open in a full-height sub-view
- Env editor becomes a bottom sheet

### Permissions

MCP servers can be powerful (filesystem access, Slack control, etc.). Show a clear permissions summary on install:
- "This server wants to: read /home, write /tmp, talk to api.github.com"
- Confirm before starting

## Out of Scope

- Custom / uploaded MCP servers not from the catalog — add later
- MCP sandbox isolation (container per server) — future; today they run in-process on the controller
- OAuth flows for servers that need them (github, slack) — covered by SecretsStore integration but the UX wizard is future work

## Implementation Order

1. Read existing `tinyagentos/mcp/` — understand what backend infra already exists
2. Create `MCPApp.tsx` with MobileSplitView skeleton and static mock data
3. Wire list to existing `/api/mcp/servers` endpoint (or add it)
4. Add start/stop/logs/env endpoints
5. Implement live log streaming via SSE
6. "Add to agent" picker flow
