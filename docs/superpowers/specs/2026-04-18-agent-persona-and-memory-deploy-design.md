# Agent persona + memory deploy — design spec

**Date:** 2026-04-18
**Status:** Proposed

## Summary

Adds a Persona step to the agent deploy wizard, dedicated Persona and Memory tabs in Agent Settings, per-agent Librarian controls, a Store "Memory" category, and plumbing so every agent turn is archived and Librarian enrichment is scoped per-agent. Closes the gap where taOS has 1150+ persona/template entries but no UI path to use them, and no visible way to see or configure the memory system that's already running under every agent.

## Scope

**In scope:**

- Persona selection at deploy (library, create-new, blank).
- `soul_md` + `agent_md` as two separately-editable fields on the agent record.
- System prompt assembly from layered pieces (strict-read directive → taosmd usage guide → soul → agent.md → framework runtime).
- Per-agent memory plugin field (`"taosmd" | "none"`).
- Per-agent Librarian controls (enable, model, 8 task toggles, fanout).
- Agent Settings → Persona tab, Agent Settings → Memory tab.
- Store: new Memory category; split "Plugins & MCP" into separate Plugins and MCP Servers categories.
- Emoji picker revamp (remove framework-default auto-fill, full emoji picker with search).
- One-shot migration: existing agents auto-enrol in taosmd with a one-time banner.
- Trace capture gaps in the bridge path so tool calls, tool results, errors, and reasoning reach the Archive tagged by agent.
- Per-agent scoping of Librarian enrichment jobs.
- User persona library (`user_personas` table) so inline-authored personas can be reused.

**Out of scope:**

- The wrong-date-in-chat-messages bug (`MessagesApp.tsx:137-147` expects ISO but backend emits unix seconds). Separate PR.
- A formal memory-plugin SDK / contract. Future spec once a second memory backend exists.
- Heuristic soul/agent.md splitting for library personas. All library personas route to `soul_md`; users move operational rules to `agent_md` manually.
- "Featured" / curated persona views. Single list + source filter is the first cut.
- Per-agent memory plugin beyond taosmd. The dropdown is forward-compatible but there are no alternatives in the catalogue yet.
- Perf/quality benchmarks for Librarian. Owned by the taosmd repo.

## Data model

New fields on the `agents` record:

| Field | Type | Default | Notes |
|---|---|---|---|
| `display_name` | text | user-chosen | Any case, numbers, spaces. |
| `slug` | text matching `[a-z0-9-]+`, unique | auto-derived from `display_name` | Used for `taosmd.agents.register_agent`, container name, API paths. Editable at deploy. |
| `soul_md` | text | `""` | Identity layer (Layer 3 of the system prompt). |
| `agent_md` | text | `""` | Operational rules (Layer 4). |
| `memory_plugin` | enum `"taosmd" \| "none"` | `"taosmd"` | Forward-compatible; only taosmd is implemented. |
| `source_persona_id` | text, nullable | `null` | Provenance: `"builtin:<id>"`, `"awesome-openclaw:<id>"`, `"prompt-library:<id>"`, `"user:<uuid>"`, or `null`. |
| `migrated_to_v2_personas` | bool | `false` for pre-existing rows, `true` for new deploys | Gates the one-time migration banner. |

Existing `name` column stays as primary key for back-compat; `slug` supersedes it on new surfaces. Migration copies `name → slug` when valid, otherwise slugifies and persists (see §Migration).

New table `user_personas`:

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `name` | text | Not unique — users can have duplicates. |
| `description` | text, nullable | |
| `soul_md` | text | |
| `agent_md` | text | |
| `created_at` | int (UTC seconds) | Stored in UTC to avoid the timezone ambiguity the message-store timestamps have. |

Clean-up in `tinyagentos/agent_templates.py` — strip `model`, `framework`, `memory_limit`, `cpu_limit` from the 12 built-ins. Personas are soul-only; those fields misled the wizard into thinking personas dictate runtime.

## System prompt assembly

The agent record stores pieces; a pure function assembles at prompt time. No denormalised cached prompt.

```python
# tinyagentos/prompt_assembly.py (new module)

STRICT_READ_DIRECTIVE = (
    "Read this document end-to-end. Do not skim, summarise, or truncate. "
    "Every section below is load-bearing."
)

def assemble_system_prompt(agent) -> str:
    parts = [STRICT_READ_DIRECTIVE]
    if agent.memory_plugin == "taosmd":
        parts.append(taosmd_agent_rules(agent.slug))
    if agent.soul_md:
        parts.append(agent.soul_md)
    if agent.agent_md:
        parts.append(agent.agent_md)
    return "\n\n---\n\n".join(parts)
```

`taosmd_agent_rules(slug)` reads `docs/agent-rules.md` from the installed taosmd package (the path follows the installed package so it stays in lockstep with whichever version is pulled) and substitutes `<your-agent-name>` with `slug`. Verbatim per upstream contract — the wording is the memory layer's contract.

Framework runtime (tool schemas, function-calling protocol) is appended by the framework downstream; it is not stored on the agent record.

Every turn recomputes the system prompt from the current pieces. Editing `soul_md` or `agent_md` or swapping `memory_plugin` takes effect on the next turn — no container redeploy, matching the established "model change = LiteLLM only" rule.

## Deploy wizard

New step sequence: **Persona → Name → Framework → Model → Permissions → Failure → Review.**

### Step 0 — Persona

Three peer tabs inside the step:

- **Browse.** Single list with search and a source filter (built-in / awesome-openclaw / prompt-library). Clicking a row previews `soul_md` in a side panel. "Use this persona" commits.
- **Create new.** Two text areas — "Soul" and "Agent.md" — each with a short helper line explaining what belongs there. Checkbox: "Save to my persona library for reuse" → writes to `user_personas` on deploy. Users can also pick from `user_personas` inside Browse (fourth source filter).
- **Blank.** Single button: "Deploy with no persona →". `soul_md` and `agent_md` both stay empty. `source_persona_id` null.

### Step 1 — Name

- **Display name** input. Flexible charset: upper/lower/numbers/spaces. Stored verbatim.
- **Slug** shown live beneath: `→ atlas-researcher`. Clicking it reveals an editable text field constrained to `[a-z0-9-]+` with uniqueness validation. Collisions show an inline error and suggest `atlas-researcher-2`.

### Emoji picker (within Step 1)

- Remove framework-default auto-fill. Delete `defaultEmojiForFramework` use in `AgentsApp.tsx:382, 643, 679-681, 1186`. `resolveAgentEmoji` (read-side fallback for agents already deployed with no emoji, seen at `:125, :311, :1365`) stays — changing it would affect existing agents rendering.
- Field starts empty. No default, no auto-suggestion.
- "None" is valid. Empty → agent record stores `null`; list view renders a neutral default (first letter of display name in a coloured circle).
- Replace the `EMOJI_QUICK_PICKS` row with a button that opens a full emoji library (category tabs, search, skin-tone). The library chosen in writing-plans must support keyboard navigation, text search, and current Unicode category coverage; `emoji-picker-react` and `emoji-mart` are both acceptable candidates. Picker opens in a popover anchored to the emoji field.
- Remove `defaultEmojiForFramework` and `EMOJI_QUICK_PICKS` exports from `@/lib/agent-emoji` once no callers remain (writing-plans sub-task).

### Deploy side-effects (on wizard submit)

Executed in order; first failure aborts cleanly with no partial state:

1. `taosmd.agents.register_agent(slug)` — creates the per-agent index. Must be idempotent upstream (existing upstream behaviour); if "already registered" is raised, treat as success.
2. Insert `agents` row with `display_name`, `slug`, `soul_md`, `agent_md`, `memory_plugin="taosmd"`, `source_persona_id`, `migrated_to_v2_personas=true`.
3. Apply Librarian defaults — no explicit call needed; upstream `_default_librarian()` returns sensible defaults on first `get_librarian(slug)` so we skip an explicit `set_librarian` for a fresh agent.
4. Existing container provisioning runs.
5. Smoke-check: `archive.record("agent_deployed", {"slug": slug}, agent_name=slug)` then `archive.query(agent_name=slug, limit=1)`. Failure here does not abort — it surfaces a warning banner in the agent's Logs tab so a transient archive issue doesn't block deploy.
6. If user ticked "Save to my persona library" in Create-new → insert into `user_personas`.

Failure at step 1 or 4 aborts the deploy with an error toast. Failure at step 2 after step 1 succeeded leaves the agent registered in taosmd with an empty per-agent index (harmless — a retry will be idempotent).

## Agent Settings — new Persona tab

New tab in `AgentsApp.tsx`'s detail view, inserted between Logs and Memory (final order: **Logs, Persona, Memory, Skills, Messages**).

Layout:

- **Source badge** at top. "From library: Research Partner (built-in)" or "Custom" (when inline-authored) or "Blank" (when both fields empty and `source_persona_id` is null). A **Swap** button next to the badge opens the same picker used at deploy.
- **Soul** — large textarea, monospace.
- **Agent.md** — separate textarea labelled "Operational rules — project context, guardrails, tool guidance."
- **Save** button at bottom. Single atomic commit updates both fields.

Swap flow: picker opens. On selection, confirmation dialog: "Replace Soul with [new persona]? Agent.md stays as-is." Overwrites `soul_md` only; `agent_md` untouched; `source_persona_id` updated.

## Agent Settings — new Memory tab

Replaces the current (absent) per-agent memory surface.

**Per-agent section:**

- **Memory plugin** dropdown. Options: `taOSmd (built-in)` and `none`, plus a terminal "Get more memory plugins →" link as the last option (deep-links to Store Memory category).
- **Description** of the currently selected plugin.
- **Stats strip** (three cells): notes count, graph edges, relative timestamp of last archive write (e.g., `2m ago`). Fetched from taosmd scoped to this agent's slug. Cells show `—` if taosmd is unreachable.
- **Links row**: "Open Memory app →" (deep-links to Memory app filtered to this agent) and "Get more plugins →" (deep-links to Store).

**Librarian section (per-agent):**

- **Enable** toggle → `set_librarian(slug, enabled=...)`.
- **Model picker** → `set_librarian(slug, model=...)` or `clear_model=True`. Options:
  - "Use install default" (null; the upstream fallback).
  - `ollama:qwen3:4b` with a ✓ recommended badge on x86/GPU hardware.
  - `dulimov/Qwen3-4B-rk3588-1.2.1-base` with ✓ recommended on RK3588.
  - Hardware is detected once per desktop app session; the ✓ follows detection.
- **Show advanced…** expander reveals:
  - Eight task toggles (one row each, task name + short description + switch): `fact_extraction, preference_extraction, intake_classification, crystallise, reflect, catalog_enrichment, query_expansion, verification`. All wire to `set_librarian(slug, tasks={...})`.
  - Fanout level dropdown (`off / low / med / high`).
  - Auto-scale checkbox.

All controls read their state from `get_librarian(slug)` on mount; writes are debounced and optimistic with rollback on error.

## Store — new categories

- New **Memory** category in the sidebar. Initial sidebar order around the changes: `… → Memory → Plugins → MCP Servers → Services → …`.
- **Split "Plugins & MCP"** into **Plugins** and **MCP Servers**. Entries retagged by their `type` field: `type === "mcp"` → MCP Servers, everything else → Plugins. Existing data migration is a one-line tag retag, not a schema change.
- taOSmd itself is not listed in the Memory category — it's built-in. Initial state of the Memory category is empty with an empty-state card: "No third-party memory plugins yet. taOSmd is installed by default and available on every agent. Check back soon."
- "Get more plugins →" deep-links use a query param (`?category=memory`) so clicks from the Memory tab land on the Memory category pre-selected.

## Migration (existing agents)

One-shot migration runs at first startup on the new version. Idempotent (version-marker gated).

1. **Per-agent record update** for every existing `agents` row:
   - `memory_plugin = "taosmd"`, `soul_md = ""`, `agent_md = ""`, `source_persona_id = null`.
   - `display_name = name` (1:1 copy).
   - `slug = name` if `name` already matches `[a-z0-9-]+`, else slugify. Uniqueness collisions append `-2`, `-3`, etc. Log the before/after for any slug change.
   - `migrated_to_v2_personas = false`.
2. **Register with taosmd** — call `register_agent(slug)`. Wrap in try/except for "already registered".
3. **Banner** — Agent Settings shows a one-time banner: "Memory upgraded — this agent now knows how to use taOSmd. Add a persona to give it character. [Add persona →]". Click or dismiss sets `migrated_to_v2_personas = true`. One per agent, per user.

No retroactive persona assignment — the user picks. Librarian defaults apply automatically via upstream `_default_librarian()`.

Rollback: revert the version marker; all new fields have neutral defaults so an older build reading the DB keeps working.

## Trace capture + Librarian access

The taOS side of taosmd's archive contract has real gaps today. This spec closes them.

**Current state (audit):**

| Surface | Archived today | Per-agent tagged |
|---|---|---|
| User message (HTTP chat) — `routes/chat.py:222-233` | Yes | Yes (`agent_name=body["author_id"]`) |
| Agent response (HTTP chat) | Yes | Yes |
| Channel-hub outbound — `router.py:262` | Yes | Yes |
| Tool calls (openclaw bridge) — `bridge_session.py:317` | No, trace store only | — |
| Tool results (openclaw bridge) — `bridge_session.py:332` | No, trace store only | — |
| Errors (bridge) — `bridge_session.py:348` | No | — |
| Reasoning events (bridge) | No | — |
| Librarian enrichment scope — `job_worker.py:113-131` | Session-scoped, not agent-scoped | — |

### Changes

**Archive all bridge events.** `BridgeSessionRegistry.record_reply()` and the tool-call / tool-result / error / reasoning paths in `bridge_session.py` gain an `archive.record(...)` call alongside the existing trace-store write. Payload:

```python
archive.record(
    event_type="tool_call" | "tool_result" | "error" | "reasoning",
    data={"tool": ..., "input": ..., "output": ..., "session_id": ...},
    agent_name=session.agent_slug,   # BridgeSession already knows this
    summary=...
)
```

The trace store stays — it's load-bearing for the live observability UI and has different retention semantics. Archive write is additive.

**Per-agent enrichment scoping.** `JobQueue` already carries `agent_name` (`job_queue.py:37`, indexed at `:50`). Update `JobWorker._do_enrich()` (`job_worker.py:113`) to pass `agent_name` through to `catalog.enrich_session()` and upstream `Librarian.process()`. Librarian filters archive rows by `agent_name` before enriching. Result: one agent's Librarian never sees another agent's traces.

**Registration on deploy.** Covered by the deploy side-effects in §Deploy wizard — `register_agent(slug)` runs as step 1.

**Container → host IPC.** The openclaw bridge endpoint `/api/openclaw/sessions/{agent}/reply` receives container-side events and writes them to the trace store today. After the change above, the same handler also forwards to the archive. No new container-side code; containers don't need archive credentials or direct DB access.

**Smoke-check on deploy.** Covered by step 5 of the deploy side-effects.

## Error handling

| Failure | Behaviour |
|---|---|
| `register_agent` fails at deploy | Abort deploy, show error toast, no partial record. User retries. |
| Slug conflict at wizard Name step | Inline validation error; suggest `atlas-researcher-2`. |
| Taosmd unreachable during Memory-tab stats fetch | Stats cells show `—`, small "Unable to reach taosmd" status. Plugin dropdown + Librarian controls stay usable (config writes, retries on next fetch). |
| Librarian model not pulled locally | Warning next to model picker: `⚠ Model not found. Pull via: ollama pull qwen3:4b`. Detected by pre-render probe. Non-blocking (config still saves). |
| `docs/agent-rules.md` missing from installed taosmd | Assembly falls back to empty Layer 2 with a warning in agent Logs. Agent still boots. |
| Persona library fetch fails (awesome-openclaw / prompt-library) | Browse tab shows built-ins (shipped in-repo) + red error banner for external sources. Built-ins, Create-new, and Blank remain usable. |
| User pastes >8KB into `soul_md` | Soft warn: "Long personas crowd the context window — keep it tight." No hard cap. |
| Archive write during bridge event fails | Warning logged; trace store write already succeeded so observability UI is intact. Agent turn continues. |
| Archive smoke-check on deploy fails | Warning banner in Logs tab; deploy still completes. |

## Testing

**Unit (`tinyagentos/tests/`):**

- `prompt_assembly.assemble_system_prompt`: all combinations of `memory_plugin` on/off × `soul_md` empty/non-empty × `agent_md` empty/non-empty. Verbatim inclusion of `agent-rules.md` with correct `<your-agent-name>` substitution. Strict directive always first, separator always `\n\n---\n\n`.
- Slug derivation: valid/invalid input, deterministic output, collision handling.
- Migration function: idempotent (two runs same result), valid existing name, invalid existing name needing slugify, collision handling.
- `user_personas` CRUD.
- Bridge event handlers write to both trace store and archive; `agent_name` correct in archive payload.

**Integration:**

- End-to-end deploy for each persona path (Browse / Create-new with Save / Blank) — verify `agents` row fields, taosmd `register_agent` called once, `user_personas` row written only when Save ticked.
- Librarian config round-trip: basic (enable, model) and advanced (task toggles, fanout, auto-scale) via the UI → upstream `set_librarian` called with correct kwargs; `get_librarian` returns the round-trip value.
- Persona swap preserves `agent_md`.
- Assembly changes flow to the next prompt without redeploy.
- Enrichment job for agent A doesn't read or mutate traces tagged to agent B.

**Playwright (desktop):**

- Wizard happy path × 3 persona flows.
- Slug live-preview, user edit, validation error on collision.
- Full emoji picker opens, searches, selects, and leaving it blank also works.
- Memory tab: Librarian enable toggle, model change, "Show advanced" reveals 8 tasks + fanout.
- Store Memory category deep-link from "Get more plugins →".
- Migration banner appears once per agent, dismisses, doesn't return.
- Deploy with a mocked archive-smoke-check failure surfaces a warning banner in Logs.

**Out of scope:** Librarian quality/perf benchmarks (owned by the taosmd repo).

## Open questions

None blocking. Future decisions that will be made when their time comes:

- When a second memory plugin exists, the dropdown and Store listing need a proper plugin contract (manifest file with id/name/description/usage-prompt, lifecycle hooks). Deferred until there's a real second implementation.
- Curated "Featured" persona view. Deferred until the raw library picker is live and we see what users actually reach for.
- Multi-human chat channels and sender-side typing exclusion — already handled server-side per user note on 2026-04-18; no further work here.
