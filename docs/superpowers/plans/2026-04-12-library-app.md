# Library App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Library App — a React TypeScript desktop app that provides a unified view of all saved knowledge items across all platforms. It talks to the `/api/knowledge/*` endpoints built in Step 1 (Knowledge Base Service).

**Architecture:** A three-panel layout: left sidebar (filters + categories), centre list (results grid), right detail panel (item content, diff view, agent subscriptions). A tabbed toolbar switches between the main library view, the category manager, the agent subscriptions panel, and the monitoring dashboard. API calls go through a dedicated `knowledge.ts` client helper. The app is registered in `app-registry.ts` under id `library`.

**Tech Stack:** React 18, TypeScript, Tailwind CSS via the existing `bg-shell-*` / `text-shell-*` token set, lucide-react icons, existing `Button / Card / Input` from `@/components/ui`, fetch-based API helpers (same pattern as `cluster.ts`).

---

## File Map

| File | Role |
|---|---|
| `desktop/src/lib/knowledge.ts` | API client — typed helpers for all `/api/knowledge/*` endpoints |
| `desktop/src/apps/LibraryApp.tsx` | Main app component — layout, state, all views |
| `desktop/src/registry/app-registry.ts` | Register `library` entry in the apps array |

---

### Task 1: API client — `desktop/src/lib/knowledge.ts`

**File:** Create `desktop/src/lib/knowledge.ts`

- [ ] Define TypeScript types mirroring the data model from the spec:

```ts
export type SourceType = "reddit" | "youtube" | "x" | "github" | "article" | "file" | "manual";
export type ItemStatus = "pending" | "processing" | "ready" | "error";

export interface KnowledgeItem {
  id: string;
  source_type: SourceType;
  source_url: string;
  source_id?: string;
  title: string;
  author: string;
  summary: string;
  content: string;
  media_path?: string;
  thumbnail?: string;
  categories: string[];
  tags: string[];
  metadata: Record<string, unknown>;
  status: ItemStatus;
  monitor?: MonitorConfig;
  created_at: number;
  updated_at: number;
}

export interface MonitorConfig {
  frequency: number;       // minutes
  decay_rate: number;
  last_poll?: number;
  pinned: boolean;
}

export interface KnowledgeSnapshot {
  id: number;
  item_id: string;
  snapshot_at: number;
  content_hash: string;
  diff_json?: string;
  metadata_json?: string;
}

export interface CategoryRule {
  id: number;
  pattern: string;
  match_on: "source_url" | "source_type" | "author" | "title" | "subreddit" | "channel";
  category: string;
  priority: number;
}

export interface AgentSubscription {
  agent_name: string;
  category: string;
  auto_ingest: boolean;
}

export interface KnowledgeListParams {
  q?: string;
  search_mode?: "keyword" | "semantic" | "hybrid";
  source_type?: SourceType;
  category?: string;
  author?: string;
  status?: ItemStatus;
  since?: number;    // unix seconds
  until?: number;
  limit?: number;
  offset?: number;
}

export interface KnowledgeListResponse {
  items: KnowledgeItem[];
  total: number;
}

export interface IngestRequest {
  url: string;
  title?: string;
  text?: string;
  categories?: string[];
  source?: string;
}
```

- [ ] Write typed fetch helpers following the `cluster.ts` pattern — all return typed responses, swallow network errors gracefully and return empty/null rather than throwing:

```ts
const API = "/api/knowledge";

export async function listItems(params: KnowledgeListParams = {}): Promise<KnowledgeListResponse> { ... }
export async function getItem(id: string): Promise<KnowledgeItem | null> { ... }
export async function deleteItem(id: string): Promise<boolean> { ... }
export async function ingestUrl(req: IngestRequest): Promise<{ id: string; status: ItemStatus } | null> { ... }

// Categories
export async function listCategories(): Promise<string[]> { ... }
export async function listCategoryRules(): Promise<CategoryRule[]> { ... }
export async function createCategoryRule(rule: Omit<CategoryRule, "id">): Promise<CategoryRule | null> { ... }
export async function deleteCategoryRule(id: number): Promise<boolean> { ... }
export async function renameCategory(from: string, to: string): Promise<boolean> { ... }
export async function mergeCategories(sources: string[], target: string): Promise<boolean> { ... }

// Agent subscriptions
export async function listSubscriptions(): Promise<AgentSubscription[]> { ... }
export async function upsertSubscription(sub: AgentSubscription): Promise<boolean> { ... }
export async function deleteSubscription(agent_name: string, category: string): Promise<boolean> { ... }

// Monitor / snapshots
export async function listSnapshots(item_id: string): Promise<KnowledgeSnapshot[]> { ... }
export async function getMonitorStatus(): Promise<{ active: number; due_soon: number; last_run?: number }> { ... }
```

---

### Task 2: App skeleton + registration

**Files:**
- Create: `desktop/src/apps/LibraryApp.tsx`
- Edit: `desktop/src/registry/app-registry.ts`

- [ ] Add the `library` entry to `app-registry.ts` after the `memory` entry (launchpadOrder 8.5):

```ts
{ id: "library", name: "Library", icon: "library", category: "platform", component: () => import("@/apps/LibraryApp").then((m) => ({ default: m.LibraryApp })), defaultSize: { w: 1100, h: 720 }, minSize: { w: 700, h: 450 }, singleton: true, pinned: false, launchpadOrder: 8.5 },
```

- [ ] Write the top-level `LibraryApp` component shell with:
  - Four tabs in the toolbar: `library`, `categories`, `subscriptions`, `monitor`
  - Local `activeTab` state toggling which panel renders
  - Outer layout: `flex flex-col h-full bg-shell-bg text-shell-text select-none`
  - Toolbar row with `Library` heading, lucide `library` icon, and tab buttons (same `aria-pressed` pattern as ModelsApp source filter)
  - Placeholder sections for each tab so the file compiles and hot-reloads cleanly

---

### Task 3: Library tab — item list with search and filters

**File:** `desktop/src/apps/LibraryApp.tsx`

- [ ] Implement the sidebar filter panel (left, `w-52 shrink-0`):
  - Source type filter pills: All, Reddit, YouTube, X, GitHub, Article, File, Manual
  - Category filter list — populated from `listCategories()` — with scroll
  - Status filter pills: All, Ready, Processing, Pending, Error
  - Each filter updates a `filters` state object and re-fetches via `listItems()`

- [ ] Implement the main results grid (centre):
  - `useEffect` on `filters` change calls `listItems()` and sets `items` state
  - Items rendered as cards (same `Card / CardHeader / CardContent` pattern as MemoryApp):
    - Source type badge with colour: reddit=orange, youtube=red, github=purple, x=sky, article=zinc, file=teal
    - Title, author, summary (2-line clamp), category pills, relative timestamp
    - Status badge in top-right: ready=emerald, processing=amber, pending=zinc, error=red
  - Empty state when no results, loading spinner while fetching
  - Click a card sets `selectedItem` and opens detail panel

- [ ] Implement keyword / semantic search:
  - Search input in toolbar with `Search` icon (same pattern as MemoryApp)
  - `searchMode` toggle: Keyword / Semantic / Hybrid (same radio group pattern as MemoryApp)
  - Debounce input (300ms) then call `listItems({ q, search_mode })`
  - Clear button (X icon) when input is non-empty (same as ModelsApp)

---

### Task 4: Detail panel — item content and diff viewer

**File:** `desktop/src/apps/LibraryApp.tsx`

- [ ] Implement a right-side detail panel (`w-96 shrink-0 border-l border-white/5`) that appears when `selectedItem` is set:
  - Header: title, author, source badge, external link icon to `source_url` (opens in browser app)
  - Summary block in a muted card
  - Full content in a scrollable `<pre>` / `prose` block
  - Tags row (same pill style as category pills in list)
  - Close button (X icon, sets `selectedItem` to null)
  - ARIA: `role="complementary"` with `aria-label="Item details"`

- [ ] Implement the diff viewer sub-section inside the detail panel:
  - "History" heading with snapshot count badge
  - List of snapshots from `listSnapshots(item.id)` — each showing relative timestamp and content hash
  - Select two snapshots to compare: renders a simple line-by-line diff where additions are `text-emerald-400` and removals are `text-red-400 line-through`
  - Parse `diff_json` from the snapshot if present; fall back to client-side diff of `content` fields
  - Show metadata deltas (upvotes, views, comment count) as a small table when `metadata_json` is present

---

### Task 5: Categories tab — management UI

**File:** `desktop/src/apps/LibraryApp.tsx`

- [ ] Implement the categories tab panel:
  - Left column: list of all categories from `listCategories()` — click to select; selected shows item count (from list response `total` filtered by that category)
  - Inline rename: click the category name to enter edit mode, confirm saves via `renameCategory()`
  - Merge button: select two+ categories then merge into a typed target name via `mergeCategories()`
  - Delete button on each category (confirmation inline, not a modal) calls `renameCategory` to remove or a dedicated delete if the API supports it

- [ ] Implement the category rules sub-panel (right column):
  - Rules table: pattern, match_on, category, priority — loaded from `listCategoryRules()`
  - Add rule form: four inputs (pattern text, match_on select, category text, priority number) + Save button; calls `createCategoryRule()`
  - Delete rule row button per rule; calls `deleteCategoryRule(id)`
  - Rules listed in priority order (highest first)

---

### Task 6: Subscriptions tab — agent subscription management

**File:** `desktop/src/apps/LibraryApp.tsx`

- [ ] Fetch agents from `/api/agents` (same pattern as MemoryApp) and categories from `listCategories()` in parallel on tab mount

- [ ] Render a grid where rows = agents and columns = categories:
  - Each cell has a toggle button: not subscribed (dim circle), notify only (bell icon, amber), auto-ingest (bolt icon, emerald)
  - Clicking cycles through the three states and calls `upsertSubscription()` or `deleteSubscription()`
  - ARIA: each toggle button has `aria-label="Subscribe {agent} to {category} — {current state}"`

- [ ] For small screens or many categories, fall back to a list view: one agent at a time, categories as rows with the same toggle buttons

---

### Task 7: Monitor tab — polling dashboard and manual ingest

**File:** `desktop/src/apps/LibraryApp.tsx`

- [ ] Implement the monitor status banner at the top:
  - Calls `getMonitorStatus()` on mount and every 30 seconds
  - Shows: active monitored items count, items due for poll soon, last poll run timestamp
  - Status dot: green if last run < 90 seconds ago, amber if 90s–5min, red if older

- [ ] Implement the active monitors list:
  - Fetches items with `monitor` config set (pass a `monitored=true` param or filter client-side)
  - Each row: source badge, title, next poll ETA (computed from `last_poll + frequency`), decay rate, pinned toggle
  - Pin button toggles `monitor.pinned` via `PATCH /api/knowledge/{id}` (a direct fetch, not through knowledge.ts helpers that don't need a full typed wrapper here)
  - "View diff" link opens that item in the detail panel with the History section expanded

- [ ] Implement the manual URL ingest form:
  - Text input for URL, optional title override, optional category chips (same pill-style multi-select as existing filter chips)
  - Ingest button calls `ingestUrl()`, shows spinner during request, then shows a success card with the item id and status badge
  - Error state shown inline below the form
  - ARIA: form `aria-label="Ingest a URL"`, submit button `aria-label="Start ingest"`
