# Reddit Client — Implementation Plan

Build Step 3 of the Knowledge Capture Pipeline. Depends on Step 1 (Knowledge Base Service) and Step 2 (Library App) being complete.

---

## Overview

The Reddit Client is a platform app registered in `app-registry.ts` that lets users browse Reddit, view threads with inline comments, save any thread to the knowledge base, and track changes to saved threads over time. It requires no API key for public threads; authenticated features (saved posts, personalised feed) use OAuth stored in SecretsStore with a cookie fallback.

---

## Files to Create

| File | Purpose |
|------|---------|
| `desktop/src/apps/RedditClientApp.tsx` | Main app component |
| `desktop/src/lib/reddit.ts` | Frontend API helpers |
| `tinyagentos/knowledge_fetchers/reddit.py` | Backend Reddit JSON fetcher |
| `tests/test_knowledge_fetcher_reddit.py` | Unit tests for fetcher |

---

## Tasks

### Task 1 — Backend fetcher: `knowledge_fetchers/reddit.py`

Create `tinyagentos/knowledge_fetchers/__init__.py` (empty) and `tinyagentos/knowledge_fetchers/reddit.py`.

The fetcher takes a Reddit thread URL and returns structured data by appending `.json` to the URL and fetching with a browser-like User-Agent (Reddit returns 429 without one). No API key required for public threads.

```
RedditPost:
  id, subreddit, title, author, selftext, score, upvote_ratio,
  num_comments, created_utc, url, permalink, flair, is_self

RedditComment:
  id, author, body, score, created_utc, depth, parent_id,
  replies: list[RedditComment], edited: bool | float, distinguished
```

Key functions:
- `fetch_thread(url, http_client) -> tuple[RedditPost, list[RedditComment]]`
  - Normalise URL: strip query params, ensure `.json` suffix
  - GET with `User-Agent: TinyAgentOS/1.0`
  - Parse listing response: `data[0]` = post, `data[1]` = comments
  - Recursively flatten comment tree, preserving depth for display
  - Deleted comments: set `body = "[deleted]"`, `author = "[deleted]"` (preserve structure)
- `flatten_to_text(post, comments) -> str`
  - Returns markdown-formatted full thread for `content` field in KnowledgeItem
  - Format: `# {title}\n\n{selftext}\n\n---\n\n` then each comment indented by depth
- `extract_metadata(post) -> dict`
  - Returns `{subreddit, score, upvote_ratio, num_comments, created_utc, flair}`

The fetcher is called by `IngestPipeline.run()` when `source_type == "reddit"`. Wire it in there at Step 2 of the pipeline (Download step) — replace any existing Reddit stub with a call to `reddit.fetch_thread()`.

Wire-in location: `tinyagentos/knowledge_ingest.py`, in `run()`, add a branch:

```python
if source_type == "reddit":
    from tinyagentos.knowledge_fetchers.reddit import fetch_thread, flatten_to_text, extract_metadata
    post, comments = await fetch_thread(item["source_url"], self._http_client)
    content = flatten_to_text(post, comments)
    metadata = extract_metadata(post)
    title = title or post.title
    author = post.author
```

---

### Task 2 — Backend API route for Reddit browse

Add a new route file `tinyagentos/routes/reddit.py` (or extend `routes/knowledge.py` if it already exists) with:

- `GET /api/reddit/thread?url={url}` — fetches and returns thread JSON (post + comments) without saving. Used by the frontend browser. Proxies through the backend so the browser never hits Reddit directly (avoids CORS).
- `GET /api/reddit/subreddit?name={subreddit}&sort=hot&limit=25` — fetches subreddit listing via `https://reddit.com/r/{subreddit}/{sort}.json`. Returns list of post stubs.
- `GET /api/reddit/search?q={query}&subreddit={optional}` — Reddit search via `.json` endpoint.
- `GET /api/reddit/saved` — requires Reddit OAuth token from SecretsStore. Fetches `https://oauth.reddit.com/user/{me}/saved.json` with Bearer token. Returns 401 if no token stored.

Auth flow for `/api/reddit/saved`:
1. Look up `reddit_access_token` and `reddit_refresh_token` from SecretsStore.
2. If access token expired, refresh via `https://www.reddit.com/api/v1/access_token` with refresh token.
3. Store new access token back to SecretsStore.
4. If no token at all, return `{"error": "not_authenticated", "oauth_url": "/api/reddit/oauth/start"}`.

OAuth endpoints (standard Reddit app flow, app type = "installed app"):
- `GET /api/reddit/oauth/start` — redirect to Reddit auth URL with scopes: `identity read history save`
- `GET /api/reddit/oauth/callback` — exchange code for tokens, store in SecretsStore under keys `reddit_access_token`, `reddit_refresh_token`, `reddit_username`

---

### Task 3 — Frontend API helpers: `desktop/src/lib/reddit.ts`

Thin wrappers over the backend routes. No direct Reddit calls from the browser.

```typescript
export interface RedditPost { id, subreddit, title, author, selftext, score, upvote_ratio, num_comments, created_utc, url, permalink, flair }
export interface RedditComment { id, author, body, score, created_utc, depth, replies: RedditComment[], edited: boolean }
export interface RedditThread { post: RedditPost; comments: RedditComment[] }
export interface RedditListing { posts: RedditPost[]; after: string | null }

export async function fetchThread(url: string): Promise<RedditThread>
export async function fetchSubreddit(name: string, sort?: string, after?: string): Promise<RedditListing>
export async function searchReddit(query: string, subreddit?: string): Promise<RedditListing>
export async function fetchSaved(): Promise<RedditPost[]>
export async function getAuthStatus(): Promise<{ authenticated: boolean; username?: string }>

// Save to knowledge base — calls existing /api/knowledge/ingest
export async function saveToLibrary(url: string, title?: string): Promise<{ id: string; status: string }>
```

All functions throw on non-2xx. `saveToLibrary` passes `source: "reddit-client"` so the ingest pipeline can log the origin.

---

### Task 4 — Main app component: `desktop/src/apps/RedditClientApp.tsx`

**Registration** — add to `app-registry.ts`:

```typescript
{ id: "reddit", name: "Reddit", icon: "reddit", category: "platform",
  component: () => import("@/apps/RedditClientApp").then(m => ({ default: m.RedditClientApp })),
  defaultSize: { w: 1000, h: 700 }, minSize: { w: 600, h: 450 },
  singleton: true, pinned: false, launchpadOrder: 14 }
```

(Use `MessageSquare` from lucide-react as icon since lucide has no Reddit icon — or use a simple `r/` text badge.)

**Component structure** — three views managed by a `view` state variable:

1. **Feed view** (default) — sidebar with Home / Saved / subreddit input. Main area shows post list cards. Each card: title, subreddit badge, score, comment count, age, author, flair. Monitoring badge (orange dot + last poll time) if thread is already saved. "Save to Library" button per card — calls `saveToLibrary`, shows spinner then green check.

2. **Thread view** — opened by clicking a post card. Header: title, subreddit, score, upvote ratio, author, flair, "Save to Library" / "Already Saved" button, monitoring status badge. Body: `selftext` rendered as markdown (use a simple `<pre>` with whitespace-pre-wrap for now, proper markdown in a later pass). Comments section: recursive component renders comment tree with indentation, author badge, score, age, collapse toggle. Deleted comments shown as `[deleted]` in grey italic. "Back to feed" chevron.

3. **Diff view** — triggered by clicking the monitoring badge on a saved thread. Shows a timeline of snapshots from `/api/knowledge/items/{id}/snapshots`. Each snapshot row shows the poll time and a summary of changes (N new comments, N deleted, vote delta). Expanding a snapshot shows a side-by-side or inline diff: new comments highlighted green, deleted comments in red with strikethrough, unchanged comments neutral. Uses the `diff_json` field from `knowledge_snapshots` table.

**Auth state** — on mount, call `getAuthStatus()`. If not authenticated, show a banner: "Log in with Reddit to see your saved posts and personalised feed" with a "Connect Reddit" button that opens `/api/reddit/oauth/start` in a popup. Banner dismissible. Anonymous browsing (public subreddits + thread fetch) always works.

**State shape:**
```typescript
type View = "feed" | "thread" | "diff"
interface State {
  view: View
  feedMode: "home" | "saved" | "subreddit"
  subreddit: string
  posts: RedditPost[]
  selectedThread: RedditThread | null
  selectedPostId: string | null
  savedItemId: string | null   // knowledge item id if this thread is saved
  authenticated: boolean
  username: string | null
  loading: boolean
  error: string | null
  after: string | null         // pagination cursor
}
```

**Accessibility** — all interactive elements have `aria-label`. Comment collapse buttons: `aria-expanded`. Save button: `aria-busy` while loading. Keyboard navigation: Enter/Space on post cards opens thread.

---

### Task 5 — Backend: monitoring badge data endpoint

The thread view needs to show whether a URL is already saved and its last monitoring status. Add to the knowledge routes:

`GET /api/knowledge/lookup?url={encoded_url}` — returns the KnowledgeItem for a given source URL if it exists (or `null`). Used by the frontend to show monitoring badges without the user having to open the Library app.

Response: `{ item: KnowledgeItem | null }` — include `monitor.last_poll`, `monitor.current_interval`, and the latest snapshot summary if available.

Also add: `GET /api/knowledge/items/{id}/snapshots` — returns list of snapshots for diff view. Already planned in the spec; implement here if not done in Step 1/2.

---

### Task 6 — Unit tests: `tests/test_knowledge_fetcher_reddit.py`

Test against a fixture JSON file (checked in at `tests/fixtures/reddit_thread.json`) that mirrors a real Reddit `.json` response structure.

Tests:
- `test_fetch_thread_parses_post` — assert post fields (title, author, score, subreddit) from fixture
- `test_fetch_thread_parses_comments` — assert top-level comment count and first comment body
- `test_fetch_thread_nested_comments` — assert a reply at depth > 0 has correct `parent_id` and `depth`
- `test_deleted_comment_preserved` — fixture includes a `[deleted]` comment; assert body is `"[deleted]"` and depth/structure intact
- `test_flatten_to_text_includes_title` — assert post title in flattened output
- `test_flatten_to_text_includes_comments` — assert comment body appears in flattened text
- `test_extract_metadata_fields` — assert subreddit, score, upvote_ratio, num_comments present
- `test_url_normalisation` — pass URL with query params and trailing slash; assert `.json` suffix added cleanly
- `test_http_error_raises` — mock 429 response; assert `httpx.HTTPStatusError` propagates

Use `pytest-asyncio` + `respx` (or `unittest.mock`) for HTTP mocking. Keep consistent with the test patterns already in `/home/jay/tinyagentos/tests/`.

---

### Task 7 — Wire-up and smoke test

1. Register the route module in `app.py` / the route loader (wherever other route files are included).
2. Run `pytest tests/test_knowledge_fetcher_reddit.py -v` — all tests green.
3. Start the dev server, open Reddit Client app, browse `r/LocalLLaMA`, open a thread, click "Save to Library", verify item appears in the Library app with status `ready` after pipeline completes.
4. Verify the monitoring badge appears on the saved thread card on next visit.

---

## Dependencies

- `httpx` — already used throughout the backend
- `pytest-asyncio`, `respx` — already used in test suite (check `conftest.py`)
- No new Python packages required for the fetcher
- No new npm packages required for the frontend (lucide-react, tailwind, existing UI components cover it)

## Out of Scope for This Step

- Reddit OAuth refresh token rotation (implement a simple one-time refresh; proper token lifecycle is a SecretsStore concern)
- Video/image gallery posts (show a link; no media download)
- Post submission or commenting (read-only per spec)
- Cookie fallback auth from browser container (stub the endpoint, implement in Step 7 Agent Browsers)
