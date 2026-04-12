# Reddit Client

## Overview

A native Reddit browsing and archiving app inside TinyAgentOS. Browse public subreddits and threads with no configuration. Authenticate with Reddit OAuth to access saved posts and personalised feeds. Every thread can be saved to the Knowledge Base with one click — after which it is indexed, summarised, embedded, and monitored for changes by the IngestPipeline.

Build order: #3 in the Knowledge Capture Pipeline (after Knowledge Base Service and Library App).

---

## Architecture

```
desktop/src/
├── apps/RedditClientApp.tsx          # Main app, view state machine (feed | thread | diff)
└── lib/reddit.ts                     # Typed fetch wrappers for /api/reddit/* endpoints

tinyagentos/
├── knowledge_fetchers/__init__.py    # Package marker
├── knowledge_fetchers/reddit.py      # RedditFetcher: fetch_thread, fetch_saved, flatten_to_text
└── routes/reddit.py                  # /api/reddit/* endpoints (browse proxy + OAuth flow)

tests/
├── test_knowledge_fetcher_reddit.py  # Backend fetcher tests (pytest-asyncio + respx)
└── fixtures/reddit_thread.json       # Realistic Reddit .json response fixture

desktop/tests/
└── reddit.test.ts                    # Frontend lib/reddit.ts tests (Vitest, mocked fetch)
```

Registered in `app-registry.ts` as:
- `id: "reddit"`
- `name: "Reddit"`
- `icon: "scroll-text"`
- `category: "platform"`
- `launchpadOrder: 14`
- `singleton: true`
- `pinned: false`
- `defaultSize: { w: 1000, h: 650 }`
- `minSize: { w: 550, h: 400 }`

---

## Auth Tiers

Three modes in priority order:

### Tier 1 — .json scraping (default, zero config)
Append `.json` to any `reddit.com` URL. GET with `User-Agent: TinyAgentOS/1.0`. Rate limit: 10 req/min unauthenticated. Works for all public content. The backend proxy at `/api/reddit/thread` and `/api/reddit/subreddit` uses this tier unless an OAuth token is present in SecretsStore.

### Tier 2 — OAuth script app (recommended)
User creates a Reddit "script" app at `reddit.com/prefs/apps`. Stores `client_id` and `client_secret` via the Secrets app. The backend OAuth flow at `/api/reddit/oauth/start` initiates the standard authorization_code flow with scopes `identity read history save`. Tokens stored in SecretsStore under keys `reddit_access_token`, `reddit_refresh_token`, `reddit_username`. Rate limit: 100 req/min, ~10K/month. Unlocks: saved posts, user subscriptions, full metadata, voting data.

### Tier 3 — Agent Browser cookies (fallback)
Read session cookies from an agent browser profile via `/api/agent-browsers/{profile}/cookies?domain=reddit.com`. The backend attaches `Cookie: reddit_session=...` header to requests instead of a Bearer token. Stub endpoint wired; full implementation in the Agent Browsers build step.

---

## Layout

Three views managed by a `view` state variable: `feed` (default), `thread`, `diff`.

### Feed View

```
┌────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌───────────────────────────────────┐ │
│ │  Sidebar     │ │ [Search bar...]     [hot|new|top]  │ │
│ │              │ │                                   │ │
│ │  Subreddits  │ │ ┌──────────────────────────────┐  │ │
│ │   Home       │ │ │ Thread card                  │  │ │
│ │   r/LocalLLM │ │ │ Title (linked)               │  │ │
│ │   r/SBC      │ │ │ r/subreddit · u/author · Xh  │  │ │
│ │   [+ Add]    │ │ │ ↑ 234  💬 56   [AI/ML]       │  │ │
│ │              │ │ │              [Save to Library]│  │ │
│ │  Saved Posts │ │ └──────────────────────────────┘  │ │
│ │  (OAuth only)│ │                                   │ │
│ │              │ │ ┌──────────────────────────────┐  │ │
│ │  Monitored   │ │ │ Thread card (saved)           │  │ │
│ │              │ │ │ • monitoring dot + last poll  │  │ │
│ │  Status      │ │ └──────────────────────────────┘  │ │
│ │   Auth status│ │                                   │ │
│ └──────────────┘ └───────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

### Thread View

Full replacement — list disappears, thread takes the full content area.

```
┌────────────────────────────────────────────────────────┐
│ ← Back    r/subreddit · u/author · Xh · ↑ 1.2k · 89% │
│                                                        │
│ Thread Title                              [Save] [Open]│
│ [AI/ML] [Tool] flair badge                            │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ Summary (LLM-generated, collapsible)             │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ Selftext rendered (markdown → plain, no XSS)           │
│                                                        │
│ [Comments] [History] [Metadata]                        │
│                                                        │
│ Comments tab (default):                                │
│  u/TopCommenter  ↑ 340  2h                [▶ collapse] │
│    Top comment body text...                           │
│                                                        │
│    ↳ u/Reply  ↑ 45  1h            [▶ collapse]       │
│        Nested reply body...                           │
│                                                        │
│        ↳ [deleted]  ↑ -3  3h                         │
│            [deleted]                                  │
│                                                        │
│ History tab:                                           │
│  Snapshot timeline — poll time, change summary         │
│  Expandable: N new comments / N deleted / vote delta  │
│                                                        │
│ Metadata tab:                                          │
│  subreddit, score over time chart (sparkline),        │
│  upvote_ratio, num_comments, created, flair           │
└────────────────────────────────────────────────────────┘
```

### Diff View

Opened from the History tab snapshot row. Shows the `diff_json` from the `knowledge_snapshots` table as a coloured inline diff: new comments highlighted green, deleted shown red with strikethrough, unchanged neutral.

---

## Item Cards

Thread cards in the feed view show:
- Thread title (clickable, opens thread view)
- Subreddit badge (`r/subreddit` in orange pill)
- Author (`u/name`), upvote count, comment count, relative time
- Flair text if present
- Category pills from Knowledge Base (if already saved)
- Orange monitoring dot + last poll age if thread is already a KnowledgeItem
- "Save to Library" button — calls `/api/knowledge/ingest`, shows spinner → green check → "Saved"

---

## Detail View

### Header
Back button, subreddit + author + age + score + upvote ratio. "Open on Reddit" (external link), "Save to Library" / "Already Saved", "Re-ingest", "Monitor" toggle (on saved items), "Delete" (on saved items). "Shared with: agent-name" contextual line if the thread's categories match any agent subscriptions.

### Body
- Summary box (collapsed by default if >3 lines; LLM-generated via IngestPipeline)
- Selftext rendered safe — strip markdown to plain text for now; proper markdown parser in a later pass. No raw HTML rendering.

### Tabs
1. **Comments** (default) — threaded comment tree, collapsible at each level. Max auto-collapsed depth: 4. `[deleted]` shown in grey italic. "Load more replies" stub for `more` nodes.
2. **History** — snapshot timeline from `/api/knowledge/items/{id}/snapshots`. Each row: poll timestamp, change summary (N new, N deleted, vote delta). Click → diff view.
3. **Metadata** — subreddit, score, upvote_ratio, num_comments, created_utc, flair, KnowledgeItem status, monitor config.

---

## Backend: RedditFetcher

File: `tinyagentos/knowledge_fetchers/reddit.py`

```
RedditPost:
  id, subreddit, title, author, selftext, score, upvote_ratio,
  num_comments, created_utc, url, permalink, flair, is_self

RedditComment:
  id, author, body, score, created_utc, depth, parent_id,
  replies: list[RedditComment], edited: bool | float, distinguished
```

Key functions:
- `fetch_thread(url, http_client, token=None) -> tuple[RedditPost, list[RedditComment]]`
  - Normalise URL: strip query params, strip trailing `.json`, add `.json?limit=500`
  - Use `https://oauth.reddit.com` base if token present, else `https://www.reddit.com`
  - Headers: `User-Agent: TinyAgentOS/1.0`, `Authorization: Bearer {token}` if OAuth
  - Parse listing: `response[0].data.children[0].data` = post, `response[1].data.children` = comments
  - Recursively build comment tree, preserving `depth` field
  - `more` kind nodes: store as stub with `body="[more]"` — not fetched in v1
  - Deleted comments: `body = "[deleted]"`, `author = "[deleted]"` (preserve depth)
- `fetch_subreddit(subreddit, sort, after, http_client, token=None) -> tuple[list[RedditPost], str|None]`
  - Fetch `https://www.reddit.com/r/{subreddit}/{sort}.json?limit=25&after={after}`
  - Returns (posts, next_after_cursor)
- `fetch_saved(token, http_client, after=None) -> tuple[list[RedditPost], str|None]`
  - Fetch `https://oauth.reddit.com/user/me/saved?limit=25&after={after}` with Bearer token
  - Returns (posts, next_after_cursor)
- `flatten_to_text(post, comments) -> str`
  - Markdown-formatted: `# {title}\n\n{selftext}\n\n---\n\n` + each comment indented by depth (2 spaces per level)
  - Suitable for the `content` field of KnowledgeItem
- `extract_metadata(post) -> dict`
  - Returns `{subreddit, score, upvote_ratio, num_comments, created_utc, flair, is_self}`

### IngestPipeline Wire-In

In `tinyagentos/knowledge_ingest.py`, `_download()` method, replace the Reddit placeholder:

```python
if source_type == "reddit":
    from tinyagentos.knowledge_fetchers.reddit import fetch_thread, flatten_to_text, extract_metadata
    post, comments = await fetch_thread(url, self._http_client)
    content = flatten_to_text(post, comments)
    new_meta = extract_metadata(post)
    metadata.update(new_meta)
    return content, post.title, post.author, metadata
```

---

## Backend: Reddit API Routes

File: `tinyagentos/routes/reddit.py`

All routes are backend proxies — the browser never calls Reddit directly (avoids CORS, centralises rate limiting).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/reddit/thread` | `?url=` — fetch thread JSON (post + comments tree) |
| GET | `/api/reddit/subreddit` | `?name=&sort=hot&limit=25&after=` — subreddit listing |
| GET | `/api/reddit/search` | `?q=&subreddit=&sort=relevance&limit=25` — search |
| GET | `/api/reddit/saved` | OAuth only — user's saved posts. 401 if no token. |
| GET | `/api/reddit/auth/status` | `{ authenticated, username }` |
| GET | `/api/reddit/auth/start` | Redirect to Reddit OAuth URL |
| GET | `/api/reddit/auth/callback` | Exchange code, store tokens, redirect to app |

OAuth detail:
- Scopes: `identity read history save`
- Redirect URI: `{TAOS_BASE_URL}/api/reddit/auth/callback`
- Tokens stored in SecretsStore: `reddit_access_token`, `reddit_refresh_token`, `reddit_username`
- On `/api/reddit/saved`: if access token present but call returns 401, attempt one refresh cycle, store new token, retry. If refresh fails, clear tokens and return `{"error": "token_expired"}`.
- If no token at all: `{"error": "not_authenticated", "auth_url": "/api/reddit/auth/start"}`

---

## Frontend: lib/reddit.ts

Thin wrappers — no direct Reddit calls from the browser.

Types:
```typescript
RedditPost { id, subreddit, title, author, selftext, score, upvote_ratio, num_comments, created_utc, url, permalink, flair, is_self }
RedditComment { id, author, body, score, created_utc, depth, parent_id, replies: RedditComment[], edited: boolean, distinguished: string | null }
RedditThread { post: RedditPost; comments: RedditComment[] }
RedditListing { posts: RedditPost[]; after: string | null }
RedditAuthStatus { authenticated: boolean; username?: string }
```

Functions:
```typescript
fetchThread(url: string): Promise<RedditThread | null>
fetchSubreddit(name: string, sort?: string, after?: string): Promise<RedditListing>
searchReddit(query: string, subreddit?: string): Promise<RedditListing>
fetchSaved(after?: string): Promise<RedditListing>
getAuthStatus(): Promise<RedditAuthStatus>
saveToLibrary(url: string, title?: string): Promise<{ id: string; status: string } | null>
```

All functions return null / empty fallbacks on network error (matching knowledge.ts pattern). `saveToLibrary` delegates to the existing `/api/knowledge/ingest` with `source: "reddit-client"`.

---

## Accessibility

- All interactive elements have `aria-label`
- Comment collapse/expand buttons: `aria-expanded`, `aria-controls`
- Save button: `aria-busy` while loading
- Sidebar nav: `aria-label="Reddit navigation"`
- Thread list: `role="list"`, each card `role="listitem"`
- Tab panels: proper `role="tablist"`, `role="tab"`, `role="tabpanel"` with `aria-selected`
- Keyboard: Enter/Space on thread cards opens thread view; Escape on thread view returns to feed

---

## Mobile

`isMobile = window.innerWidth < 640`. On mobile the sidebar is hidden when a subreddit or thread is active. Comment tree depth capped at 2 visible levels (deeper levels behind "load more" tap).

---

## Dependencies

- `httpx` — already in backend
- `pytest-asyncio`, `respx` — already in test suite
- No new Python packages
- No new npm packages (lucide-react, Tailwind, existing UI barrel cover everything)

---

## Out of Scope for This Build Step

- Video/image/gallery post media download (show link only)
- Post submission or commenting (read-only)
- Cookie-based Tier 3 auth (stub wired, full impl in Agent Browsers step)
- Proper markdown rendering (use plain whitespace-pre-wrap for now)
- Infinite scroll (load more button only)
- Reddit live threads
