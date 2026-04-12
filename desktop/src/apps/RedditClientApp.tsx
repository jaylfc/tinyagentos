import { useState, useEffect, useCallback, useRef } from "react";
import {
  ScrollText,
  Lock,
  ChevronLeft,
  ExternalLink,
  Search,
  ChevronDown,
  ChevronRight,
  Plus,
  Check,
  RefreshCw,
  Trash2,
  BookmarkPlus,
  Eye,
} from "lucide-react";
import { Button, Input } from "@/components/ui";
import {
  fetchThread,
  fetchSubreddit,
  searchReddit,
  fetchSaved,
  getAuthStatus,
  saveToLibrary,
} from "@/lib/reddit";
import type {
  RedditPost,
  RedditComment,
  RedditThread,
  RedditListing,
  RedditAuthStatus,
} from "@/lib/reddit";
import { listItems, deleteItem, ingestUrl } from "@/lib/knowledge";
import type { KnowledgeItem } from "@/lib/knowledge";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type View = "feed" | "thread";
type SortMode = "hot" | "new" | "top";
type SidebarSection = "subreddits" | "saved" | "monitored" | "history";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const POPULAR_SUBS = ["LocalLLaMA", "selfhosted", "homelab", "linux"];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

function formatScore(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function stripRedditDomain(url: string): string {
  return url.replace(/^https?:\/\/(www\.)?reddit\.com/, "");
}

/* ------------------------------------------------------------------ */
/*  CommentNode (recursive)                                            */
/* ------------------------------------------------------------------ */

interface CommentNodeProps {
  comment: RedditComment;
  maxDepth?: number;
}

function CommentNode({ comment, maxDepth = 4 }: CommentNodeProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [showReplies, setShowReplies] = useState(comment.depth < maxDepth);

  const isDeleted =
    comment.author === "[deleted]" || comment.body === "[deleted]";

  const toggleCollapse = () => setCollapsed((v) => !v);

  return (
    <li
      role="listitem"
      className="text-sm"
      style={{ marginLeft: comment.depth > 0 ? "2rem" : 0 }}
    >
      {/* Comment header */}
      <div className="flex items-center gap-2 py-0.5">
        <button
          aria-label={collapsed ? "Expand comment" : "Collapse comment"}
          aria-expanded={!collapsed}
          onClick={toggleCollapse}
          className="text-shell-text-tertiary hover:text-shell-text shrink-0"
        >
          {collapsed ? (
            <ChevronRight size={13} />
          ) : (
            <ChevronDown size={13} />
          )}
        </button>
        {isDeleted ? (
          <span className="text-shell-text-tertiary italic text-xs">
            [deleted]
          </span>
        ) : (
          <>
            <span className="font-semibold text-xs text-shell-text">
              u/{comment.author}
            </span>
            {comment.distinguished === "moderator" && (
              <span className="text-[10px] text-green-400 font-semibold">MOD</span>
            )}
            <span className="text-shell-text-tertiary text-xs">
              {formatScore(comment.score)} pts
            </span>
            <span className="text-shell-text-tertiary text-xs">·</span>
            <span className="text-shell-text-tertiary text-xs">
              {timeAgo(comment.created_utc)}
            </span>
            {comment.edited && (
              <span className="text-shell-text-tertiary text-xs italic">
                (edited)
              </span>
            )}
          </>
        )}
      </div>

      {/* Comment body */}
      {!collapsed && !isDeleted && (
        <p className="text-shell-text-secondary text-xs whitespace-pre-wrap mt-0.5 ml-5 pb-1 leading-relaxed">
          {comment.body}
        </p>
      )}

      {/* Replies */}
      {!collapsed && comment.replies.length > 0 && (
        <div className="border-l border-white/5 ml-5 mt-0.5">
          {showReplies || comment.depth < maxDepth ? (
            <ul role="list" className="space-y-1">
              {comment.replies.map((r) => (
                <CommentNode key={r.id} comment={r} maxDepth={maxDepth} />
              ))}
            </ul>
          ) : (
            <button
              className="text-xs text-accent hover:underline ml-3 py-0.5"
              onClick={() => setShowReplies(true)}
              aria-label={`Show ${comment.replies.length} more replies`}
            >
              Show {comment.replies.length} more {comment.replies.length === 1 ? "reply" : "replies"}
            </button>
          )}
        </div>
      )}
    </li>
  );
}

/* ------------------------------------------------------------------ */
/*  PostCard                                                           */
/* ------------------------------------------------------------------ */

interface PostCardProps {
  post: RedditPost;
  savedItem?: KnowledgeItem;
  onOpen: (post: RedditPost) => void;
  onSave: (post: RedditPost) => void;
  saving: boolean;
}

function PostCard({ post, savedItem, onOpen, onSave, saving }: PostCardProps) {
  const isSaved = !!savedItem;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onOpen(post);
    }
  };

  return (
    <div
      className="border border-white/5 rounded-lg p-3 bg-shell-surface/30 hover:bg-shell-surface/50 transition-colors"
      role="article"
    >
      {/* Title row */}
      <div className="flex items-start gap-2 mb-1">
        <div className="flex-1 min-w-0">
          <button
            className="text-left text-sm font-medium text-shell-text hover:text-accent transition-colors leading-snug cursor-pointer"
            onClick={() => onOpen(post)}
            onKeyDown={handleKeyDown}
            tabIndex={0}
            aria-label={`Open thread: ${post.title}`}
          >
            {post.title}
          </button>
        </div>
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-2 flex-wrap mb-1.5">
        <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full bg-orange-500/20 text-orange-400 border border-orange-500/30">
          r/{post.subreddit}
        </span>
        <span className="text-xs text-shell-text-tertiary">
          u/{post.author}
        </span>
        <span className="text-shell-text-tertiary text-xs">·</span>
        <span className="text-xs text-shell-text-tertiary">
          {formatScore(post.score)} pts
        </span>
        <span className="text-shell-text-tertiary text-xs">·</span>
        <span className="text-xs text-shell-text-tertiary">
          {post.num_comments} comments
        </span>
        <span className="text-shell-text-tertiary text-xs">·</span>
        <span className="text-xs text-shell-text-tertiary">
          {timeAgo(post.created_utc)}
        </span>
        {post.flair && (
          <>
            <span className="text-shell-text-tertiary text-xs">·</span>
            <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/5 text-shell-text-tertiary border border-white/10">
              {post.flair}
            </span>
          </>
        )}
      </div>

      {/* Selftext preview */}
      {post.is_self && post.selftext && (
        <p className="text-xs text-shell-text-secondary line-clamp-2 mb-2 leading-relaxed">
          {post.selftext}
        </p>
      )}

      {/* Category pills if saved */}
      {isSaved && savedItem.categories.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {savedItem.categories.map((cat) => (
            <span
              key={cat}
              className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20"
            >
              {cat}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 mt-1">
        <Button
          variant={isSaved ? "secondary" : "ghost"}
          size="sm"
          className="h-6 text-xs gap-1 px-2"
          onClick={() => onSave(post)}
          disabled={saving || isSaved}
          aria-label={isSaved ? "Saved to Library" : "Save to Library"}
        >
          {isSaved ? (
            <>
              <Check size={11} />
              Saved
            </>
          ) : (
            <>
              <BookmarkPlus size={11} />
              {saving ? "Saving…" : "Save to Library"}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  RedditClientApp                                                    */
/* ------------------------------------------------------------------ */

export function RedditClientApp({ windowId: _windowId }: { windowId: string }) {
  /* ---------- view ---------- */
  const [view, setView] = useState<View>("feed");
  const [thread, setThread] = useState<RedditThread | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);

  /* ---------- sidebar ---------- */
  const [activeSub, setActiveSub] = useState<string | null>(null);
  const [subs, setSubs] = useState<string[]>(POPULAR_SUBS);
  const [addSubOpen, setAddSubOpen] = useState(false);
  const [newSub, setNewSub] = useState("");
  const [activeSection, setActiveSection] = useState<SidebarSection>("subreddits");

  /* ---------- feed ---------- */
  const [listing, setListing] = useState<RedditListing>({ posts: [], after: null });
  const [feedLoading, setFeedLoading] = useState(false);
  const [sort, setSort] = useState<SortMode>("hot");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");

  /* ---------- auth ---------- */
  const [authStatus, setAuthStatus] = useState<RedditAuthStatus>({ authenticated: false });

  /* ---------- knowledge items (saved) ---------- */
  const [savedItems, setSavedItems] = useState<KnowledgeItem[]>([]);
  const [savingPostId, setSavingPostId] = useState<string | null>(null);

  /* ---------- thread view ---------- */
  const [threadTab, setThreadTab] = useState<"comments" | "history" | "metadata">("comments");
  const [threadSaved, setThreadSaved] = useState<KnowledgeItem | null>(null);
  const [threadSaving, setThreadSaving] = useState(false);
  const [confirmDeleteThread, setConfirmDeleteThread] = useState(false);
  const [_monitorEnabled, setMonitorEnabled] = useState(false);

  /* ---------- mobile ---------- */
  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;

  const searchRef = useRef<HTMLInputElement>(null);

  /* ---------------------------------------------------------------- */
  /*  Auth + saved items                                               */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    getAuthStatus().then(setAuthStatus);
    refreshSavedItems();
  }, []);

  const refreshSavedItems = useCallback(async () => {
    const { items } = await listItems({ source_type: "reddit", limit: 200 });
    setSavedItems(items);
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Feed loading                                                     */
  /* ---------------------------------------------------------------- */

  const loadFeed = useCallback(
    async (sub: string | null, sortMode: SortMode, query: string) => {
      setFeedLoading(true);
      try {
        let result: RedditListing;
        if (query.trim()) {
          result = await searchReddit(query.trim(), sub ?? undefined);
        } else if (activeSection === "saved" && authStatus.authenticated) {
          result = await fetchSaved();
        } else if (sub) {
          result = await fetchSubreddit(sub, sortMode);
        } else {
          result = { posts: [], after: null };
        }
        setListing(result);
      } catch {
        setListing({ posts: [], after: null });
      }
      setFeedLoading(false);
    },
    [activeSection, authStatus.authenticated],
  );

  useEffect(() => {
    if (view === "feed") {
      loadFeed(activeSub, sort, searchQuery);
    }
  }, [activeSub, sort, searchQuery, view, loadFeed]);

  /* ---------------------------------------------------------------- */
  /*  Open thread                                                      */
  /* ---------------------------------------------------------------- */

  const openThread = useCallback(
    async (post: RedditPost) => {
      setView("thread");
      setThreadTab("comments");
      setThread(null);
      setConfirmDeleteThread(false);
      setThreadLoading(true);
      const t = await fetchThread(post.url);
      setThread(t);
      setThreadLoading(false);
      // Check if saved
      const match = savedItems.find(
        (i) =>
          i.source_url === post.url ||
          i.source_url === `https://www.reddit.com${post.permalink}`,
      );
      setThreadSaved(match ?? null);
      setMonitorEnabled(match ? (match.monitor?.current_interval ?? 0) > 0 : false);
    },
    [savedItems],
  );

  const goBackToFeed = useCallback(() => {
    setView("feed");
    setThread(null);
    setConfirmDeleteThread(false);
  }, []);

  /* Escape key in thread view */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && view === "thread") goBackToFeed();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [view, goBackToFeed]);

  /* ---------------------------------------------------------------- */
  /*  Save helpers                                                     */
  /* ---------------------------------------------------------------- */

  const handleSavePost = useCallback(
    async (post: RedditPost) => {
      setSavingPostId(post.id);
      await saveToLibrary(post.url, post.title);
      await refreshSavedItems();
      setSavingPostId(null);
    },
    [refreshSavedItems],
  );

  const handleSaveThread = useCallback(async () => {
    if (!thread) return;
    setThreadSaving(true);
    const result = await saveToLibrary(thread.post.url, thread.post.title);
    if (result) {
      await refreshSavedItems();
      const match = savedItems.find((i) => i.source_url === thread.post.url);
      setThreadSaved(match ?? null);
    }
    setThreadSaving(false);
  }, [thread, savedItems, refreshSavedItems]);

  const handleReIngestThread = useCallback(async () => {
    if (!threadSaved) return;
    await ingestUrl(threadSaved.source_url, {
      title: threadSaved.title,
      categories: threadSaved.categories,
    });
    await refreshSavedItems();
  }, [threadSaved, refreshSavedItems]);

  const handleDeleteThread = useCallback(async () => {
    if (!threadSaved) return;
    await deleteItem(threadSaved.id);
    setThreadSaved(null);
    setConfirmDeleteThread(false);
    await refreshSavedItems();
  }, [threadSaved, refreshSavedItems]);

  /* ---------------------------------------------------------------- */
  /*  Add subreddit                                                    */
  /* ---------------------------------------------------------------- */

  const addSub = useCallback(() => {
    const name = newSub.trim().replace(/^r\//, "");
    if (name && !subs.includes(name)) {
      setSubs((prev) => [...prev, name]);
      setActiveSub(name);
      setActiveSection("subreddits");
    }
    setNewSub("");
    setAddSubOpen(false);
  }, [newSub, subs]);

  /* ---------------------------------------------------------------- */
  /*  Saved items helpers                                              */
  /* ---------------------------------------------------------------- */

  const getSavedForPost = useCallback(
    (post: RedditPost): KnowledgeItem | undefined =>
      savedItems.find(
        (i) =>
          i.source_url === post.url ||
          i.source_url === `https://www.reddit.com${post.permalink}`,
      ),
    [savedItems],
  );

  const monitoredItems = savedItems.filter(
    (i) => i.source_type === "reddit" && (i.monitor?.current_interval ?? 0) > 0,
  );

  /* ---------------------------------------------------------------- */
  /*  Sidebar UI                                                       */
  /* ---------------------------------------------------------------- */

  const sidebarUI = (
    <nav
      className={
        isMobile
          ? "w-full flex flex-col overflow-hidden h-full"
          : "w-52 shrink-0 border-r border-white/5 bg-shell-surface/30 flex flex-col overflow-hidden"
      }
      aria-label="Reddit navigation"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-white/5 shrink-0">
        <ScrollText size={15} className="text-orange-400" />
        <h1 className="text-sm font-semibold">Reddit</h1>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {/* Subreddits */}
        <section>
          <div className="flex items-center justify-between px-2 mb-1.5">
            <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary">
              Subreddits
            </p>
            <button
              aria-label="Add subreddit"
              onClick={() => setAddSubOpen((v) => !v)}
              className="text-shell-text-tertiary hover:text-accent transition-colors"
            >
              <Plus size={12} />
            </button>
          </div>

          {/* Add sub input */}
          {addSubOpen && (
            <div className="flex gap-1 mb-1 px-1">
              <Input
                value={newSub}
                onChange={(e) => setNewSub(e.target.value)}
                placeholder="r/subreddit"
                className="h-6 text-xs flex-1"
                aria-label="New subreddit name"
                onKeyDown={(e) => {
                  if (e.key === "Enter") addSub();
                  if (e.key === "Escape") setAddSubOpen(false);
                }}
                autoFocus
              />
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-1.5 text-xs"
                onClick={addSub}
                aria-label="Confirm add subreddit"
              >
                <Check size={11} />
              </Button>
            </div>
          )}

          <div className="space-y-0.5">
            {subs.map((sub) => {
              const active =
                activeSection === "subreddits" && activeSub === sub;
              return (
                <Button
                  key={sub}
                  variant={active ? "secondary" : "ghost"}
                  size="sm"
                  aria-pressed={active}
                  onClick={() => {
                    setActiveSub(sub);
                    setActiveSection("subreddits");
                    setSearchQuery("");
                    setSearchInput("");
                  }}
                  className="w-full justify-start text-xs h-7 px-2 gap-1.5"
                >
                  <span className="text-orange-400 text-[10px] font-bold">r/</span>
                  {sub}
                </Button>
              );
            })}
          </div>
        </section>

        {/* Saved Posts */}
        <section>
          <div className="flex items-center gap-1.5 px-2 mb-1.5">
            <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary">
              Saved Posts
            </p>
            {!authStatus.authenticated && (
              <Lock size={10} className="text-shell-text-tertiary" />
            )}
          </div>
          {authStatus.authenticated ? (
            <Button
              variant={activeSection === "saved" ? "secondary" : "ghost"}
              size="sm"
              aria-pressed={activeSection === "saved"}
              onClick={() => {
                setActiveSection("saved");
                setActiveSub(null);
              }}
              className="w-full justify-start text-xs h-7 px-2"
            >
              Reddit Saved
            </Button>
          ) : (
            <p className="text-[11px] text-shell-text-tertiary px-2 italic">
              Not connected
            </p>
          )}
        </section>

        {/* Monitored */}
        <section>
          <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary px-2 mb-1.5">
            Monitored
          </p>
          <div className="space-y-0.5">
            {monitoredItems.length === 0 ? (
              <p className="text-[11px] text-shell-text-tertiary px-2 italic">
                None yet
              </p>
            ) : (
              monitoredItems.map((item) => (
                <Button
                  key={item.id}
                  variant={activeSection === "monitored" && activeSub === item.id ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => {
                    setActiveSection("monitored");
                  }}
                  className="w-full justify-start text-xs h-7 px-2 truncate"
                  aria-label={`Monitored: ${item.title}`}
                >
                  <Eye size={11} className="shrink-0 mr-1" />
                  <span className="truncate">{item.title}</span>
                </Button>
              ))
            )}
          </div>
        </section>

        {/* History (placeholder) */}
        <section>
          <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary px-2 mb-1.5">
            History
          </p>
          <p className="text-[11px] text-shell-text-tertiary px-2 italic">
            Coming soon
          </p>
        </section>
      </div>

      {/* Auth status at bottom */}
      <div className="border-t border-white/5 px-3 py-2 shrink-0">
        {authStatus.authenticated ? (
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-500 shrink-0" />
            <span className="text-xs text-shell-text-secondary truncate">
              u/{authStatus.username}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-shell-text-tertiary shrink-0" />
            <a
              href="/api/reddit/auth/login"
              className="text-xs text-accent hover:underline"
              aria-label="Connect Reddit account"
            >
              Not connected
            </a>
          </div>
        )}
      </div>
    </nav>
  );

  /* ---------------------------------------------------------------- */
  /*  Feed view                                                        */
  /* ---------------------------------------------------------------- */

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(searchInput);
  };

  const feedViewUI = (
    <main className="flex-1 flex flex-col overflow-hidden">
      {/* Search + sort bar */}
      <div className="px-4 py-3 border-b border-white/5 shrink-0 space-y-2">
        <form onSubmit={handleSearch} className="flex gap-2" role="search">
          <Input
            ref={searchRef}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder={
              activeSub
                ? `Search r/${activeSub}…`
                : "Search Reddit…"
            }
            className="flex-1 h-8 text-sm"
            aria-label="Search Reddit"
          />
          <Button
            type="submit"
            variant="ghost"
            size="sm"
            className="h-8 px-2"
            aria-label="Run search"
          >
            <Search size={14} />
          </Button>
        </form>

        {/* Sort controls */}
        <div className="flex items-center gap-1" role="group" aria-label="Sort posts">
          {(["hot", "new", "top"] as SortMode[]).map((s) => (
            <Button
              key={s}
              variant={sort === s ? "secondary" : "ghost"}
              size="sm"
              className="h-6 text-xs px-2 capitalize"
              aria-pressed={sort === s}
              onClick={() => setSort(s)}
            >
              {s}
            </Button>
          ))}
        </div>
      </div>

      {/* Post list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {feedLoading && (
          <div className="flex items-center justify-center py-12">
            <RefreshCw size={18} className="animate-spin text-shell-text-tertiary" />
          </div>
        )}

        {!feedLoading && !activeSub && activeSection === "subreddits" && !searchQuery && (
          <div className="flex flex-col items-center justify-center py-16 text-shell-text-tertiary">
            <ScrollText size={36} className="mb-3 opacity-30" />
            <p className="text-sm">Select a subreddit to browse</p>
          </div>
        )}

        {!feedLoading && listing.posts.length > 0 && (
          <ul role="list" className="space-y-2">
            {listing.posts.map((post) => (
              <li key={post.id} role="listitem">
                <PostCard
                  post={post}
                  savedItem={getSavedForPost(post)}
                  onOpen={openThread}
                  onSave={handleSavePost}
                  saving={savingPostId === post.id}
                />
              </li>
            ))}
          </ul>
        )}

        {!feedLoading &&
          listing.posts.length === 0 &&
          (activeSub || searchQuery || activeSection === "saved") && (
            <div className="flex flex-col items-center justify-center py-16 text-shell-text-tertiary">
              <p className="text-sm">No posts found</p>
            </div>
          )}
      </div>
    </main>
  );

  /* ---------------------------------------------------------------- */
  /*  Thread view                                                      */
  /* ---------------------------------------------------------------- */

  const threadViewUI = (() => {
    const post = thread?.post ?? null;
    const comments = thread?.comments ?? [];

    return (
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Back button + action bar */}
        <div className="px-3 py-2 border-b border-white/5 shrink-0 flex items-center justify-between gap-2 flex-wrap">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1.5"
            onClick={goBackToFeed}
            aria-label="Back to feed"
          >
            <ChevronLeft size={13} />
            Back to feed
          </Button>

          {post && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <a
                href={`https://www.reddit.com${post.permalink}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-shell-text-tertiary hover:text-accent transition-colors"
                aria-label="Open on Reddit"
              >
                <ExternalLink size={12} />
                Reddit
              </a>

              {threadSaved ? (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="h-6 text-xs gap-1 px-2"
                    disabled
                    aria-label="Already saved to Library"
                  >
                    <Check size={11} />
                    Saved
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs gap-1 px-2"
                    onClick={handleReIngestThread}
                    aria-label="Re-ingest this thread"
                  >
                    <RefreshCw size={11} />
                    Re-ingest
                  </Button>
                  {confirmDeleteThread ? (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs px-2 text-red-400 hover:text-red-300"
                        onClick={handleDeleteThread}
                        aria-label="Confirm delete from Library"
                      >
                        Confirm Delete
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs px-2"
                        onClick={() => setConfirmDeleteThread(false)}
                        aria-label="Cancel delete"
                      >
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-xs gap-1 px-2 text-red-400 hover:text-red-300"
                      onClick={() => setConfirmDeleteThread(true)}
                      aria-label="Delete from Library"
                    >
                      <Trash2 size={11} />
                    </Button>
                  )}
                </>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-xs gap-1 px-2"
                  onClick={handleSaveThread}
                  disabled={threadSaving}
                  aria-label="Save to Library"
                >
                  <BookmarkPlus size={11} />
                  {threadSaving ? "Saving…" : "Save to Library"}
                </Button>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {threadLoading && (
            <div className="flex items-center justify-center py-16">
              <RefreshCw size={20} className="animate-spin text-shell-text-tertiary" />
            </div>
          )}

          {!threadLoading && post && (
            <>
              {/* Post header */}
              <div className="space-y-2">
                <h2 className="text-base font-semibold text-shell-text leading-snug">
                  {post.title}
                </h2>

                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full bg-orange-500/20 text-orange-400 border border-orange-500/30">
                    r/{post.subreddit}
                  </span>
                  <span className="text-xs text-shell-text-tertiary">
                    by u/{post.author}
                  </span>
                  <span className="text-shell-text-tertiary text-xs">·</span>
                  <span className="text-xs text-shell-text-tertiary">
                    {formatScore(post.score)} pts
                  </span>
                  <span className="text-shell-text-tertiary text-xs">·</span>
                  <span className="text-xs text-shell-text-tertiary">
                    {Math.round(post.upvote_ratio * 100)}% upvoted
                  </span>
                  <span className="text-shell-text-tertiary text-xs">·</span>
                  <span className="text-xs text-shell-text-tertiary">
                    {timeAgo(post.created_utc)}
                  </span>
                </div>

                {/* Summary if saved */}
                {threadSaved?.summary && (
                  <div className="bg-accent/5 border border-accent/20 rounded-lg px-3 py-2">
                    <p className="text-[10px] uppercase tracking-wider text-accent mb-1 font-semibold">
                      Summary
                    </p>
                    <p className="text-xs text-shell-text-secondary leading-relaxed">
                      {threadSaved.summary}
                    </p>
                  </div>
                )}

                {/* Post body */}
                {post.is_self && post.selftext && (
                  <div className="bg-white/3 rounded-lg px-3 py-2 border border-white/5">
                    <p className="text-sm text-shell-text-secondary whitespace-pre-wrap leading-relaxed">
                      {post.selftext}
                    </p>
                  </div>
                )}

                {!post.is_self && (
                  <a
                    href={post.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-accent hover:underline flex items-center gap-1"
                    aria-label={`External link: ${post.url}`}
                  >
                    <ExternalLink size={11} />
                    {stripRedditDomain(post.url) || post.url}
                  </a>
                )}
              </div>

              {/* Tabs */}
              <div>
                <div
                  role="tablist"
                  aria-label="Thread sections"
                  className="flex gap-1 border-b border-white/5 pb-0 mb-3"
                >
                  {(["comments", "history", "metadata"] as const).map(
                    (tab) => (
                      <button
                        key={tab}
                        role="tab"
                        aria-selected={threadTab === tab}
                        onClick={() => setThreadTab(tab)}
                        className={[
                          "px-3 py-1.5 text-xs capitalize border-b-2 transition-colors",
                          threadTab === tab
                            ? "border-accent text-accent"
                            : "border-transparent text-shell-text-tertiary hover:text-shell-text",
                        ].join(" ")}
                      >
                        {tab}
                        {tab === "comments" && (
                          <span className="ml-1 text-[10px] opacity-60">
                            ({post.num_comments})
                          </span>
                        )}
                      </button>
                    ),
                  )}
                </div>

                {/* Comments tab */}
                {threadTab === "comments" && (
                  <ul role="list" className="space-y-2">
                    {comments.length === 0 ? (
                      <li className="text-sm text-shell-text-tertiary py-4 text-center italic">
                        No comments yet
                      </li>
                    ) : (
                      comments.map((c) => (
                        <CommentNode key={c.id} comment={c} />
                      ))
                    )}
                  </ul>
                )}

                {/* History tab */}
                {threadTab === "history" && (
                  <div className="text-sm text-shell-text-tertiary py-4">
                    {threadSaved ? (
                      <p className="italic">
                        Monitoring snapshots will appear here when available.
                      </p>
                    ) : (
                      <p className="italic">
                        Save this thread to the Library to enable monitoring.
                      </p>
                    )}
                  </div>
                )}

                {/* Metadata tab */}
                {threadTab === "metadata" && post && (
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                    {[
                      ["Subreddit", `r/${post.subreddit}`],
                      ["Author", `u/${post.author}`],
                      ["Score", formatScore(post.score)],
                      ["Upvote ratio", `${Math.round(post.upvote_ratio * 100)}%`],
                      ["Comments", String(post.num_comments)],
                      ["Flair", post.flair || "—"],
                      ["Type", post.is_self ? "Text post" : "Link post"],
                      ["Posted", new Date(post.created_utc * 1000).toLocaleString()],
                      ["Permalink", post.permalink],
                    ].map(([label, value]) => (
                      <div key={label} className="contents">
                        <dt className="text-shell-text-tertiary font-medium truncate">
                          {label}
                        </dt>
                        <dd className="text-shell-text truncate" title={value}>
                          {value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            </>
          )}

          {!threadLoading && !thread && (
            <div className="flex flex-col items-center justify-center py-16 text-shell-text-tertiary">
              <p className="text-sm">Failed to load thread</p>
            </div>
          )}
        </div>
      </main>
    );
  })();

  /* ---------------------------------------------------------------- */
  /*  Layout                                                           */
  /* ---------------------------------------------------------------- */

  // Mobile: show sidebar in feed view, thread view replaces everything
  if (isMobile) {
    if (view === "thread") {
      return (
        <div className="flex flex-col h-full overflow-hidden bg-shell-base text-shell-text">
          {threadViewUI}
        </div>
      );
    }
    return (
      <div className="flex flex-col h-full overflow-hidden bg-shell-base text-shell-text">
        {sidebarUI}
        {feedViewUI}
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-shell-base text-shell-text">
      {sidebarUI}
      {view === "feed" ? feedViewUI : threadViewUI}
    </div>
  );
}
