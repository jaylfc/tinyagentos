import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Github,
  Star,
  GitFork,
  Bell,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Search,
  Tag,
  MessageSquare,
  Download,
  BookMarked,
  Eye,
  AlertCircle,
  GitPullRequest,
  CircleDot,
  Package,
} from "lucide-react";
import {
  Button,
  Card,
  CardHeader,
  CardContent,
  Input,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui";
import {
  fetchStarred,
  fetchNotifications,
  fetchRepo,
  fetchIssue,
  fetchReleases,
  getAuthStatus,
  saveToLibrary,
} from "@/lib/github";
import type {
  GitHubRepo,
  GitHubIssue,
  GitHubRelease,
  GitHubComment,
  GitHubAuthStatus,
} from "@/lib/github";
import { MobileSplitView } from "@/components/mobile/MobileSplitView";
import { useIsMobile } from "@/hooks/use-is-mobile";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type View = "list" | "detail";
type SidebarSection = "starred" | "notifications" | "watched";
type ContentType = "repos" | "issues" | "prs" | "releases";

interface DetailTarget {
  type: "repo" | "issue" | "release";
  repo?: GitHubRepo;
  issue?: GitHubIssue;
  release?: GitHubRelease;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const formatDate = (iso: string): string => {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
};

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
};

const stateColor = (state: string): string => {
  if (state === "open") return "bg-green-500/15 text-green-400 border-green-500/30";
  if (state === "closed") return "bg-red-500/15 text-red-400 border-red-500/30";
  if (state === "merged") return "bg-purple-500/15 text-purple-400 border-purple-500/30";
  return "bg-white/10 text-shell-text-tertiary border-white/10";
};

/* ------------------------------------------------------------------ */
/*  CommentNode (recursive, collapsible at 3 levels)                  */
/* ------------------------------------------------------------------ */

function CommentNode({ comment, depth = 0 }: { comment: GitHubComment; depth?: number }) {
  const [collapsed, setCollapsed] = useState(depth >= 3);

  return (
    <div
      className={`border-l-2 ${depth === 0 ? "border-white/10" : "border-white/5"} pl-3 py-1`}
      style={{ marginLeft: depth > 0 ? `${depth * 12}px` : 0 }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-medium text-shell-text-secondary">{comment.author}</span>
        <span className="text-[10px] text-shell-text-tertiary">{formatDate(comment.created_at)}</span>
        {depth >= 3 && (
          <button
            className="text-[10px] text-accent hover:underline ml-1"
            onClick={() => setCollapsed((v) => !v)}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expand comment" : "Collapse comment"}
          >
            {collapsed ? "expand" : "collapse"}
          </button>
        )}
      </div>
      {!collapsed && (
        <>
          <p className="text-xs text-shell-text-secondary whitespace-pre-wrap leading-relaxed mb-1">
            {comment.body}
          </p>
          {Object.keys(comment.reactions ?? {}).length > 0 && (
            <div className="flex gap-1.5 flex-wrap mb-1">
              {Object.entries(comment.reactions).map(([emoji, count]) =>
                count > 0 ? (
                  <span
                    key={emoji}
                    className="px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-[10px] text-shell-text-secondary"
                    aria-label={`${emoji}: ${count}`}
                  >
                    {emoji} {count}
                  </span>
                ) : null,
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  GitHubApp                                                          */
/* ------------------------------------------------------------------ */

export function GitHubApp({ windowId: _windowId }: { windowId: string }) {
  /* ---------- view state ---------- */
  // view is kept for legacy section-switch effect below; navigation is now driven by selectedId/MobileSplitView
  const [, setView] = useState<View>("list");
  const [detail, setDetail] = useState<DetailTarget | null>(null);

  /* ---------- sidebar state ---------- */
  const [activeSection, setActiveSection] = useState<SidebarSection>("starred");
  const [contentType, setContentType] = useState<ContentType>("repos");
  const [filterStatus, setFilterStatus] = useState<string | null>(null);

  /* ---------- list state ---------- */
  const [starredRepos, setStarredRepos] = useState<GitHubRepo[]>([]);
  const [notifications, setNotifications] = useState<GitHubIssue[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [watched] = useState<GitHubRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  /* ---------- detail state ---------- */
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailReleases, setDetailReleases] = useState<GitHubRelease[]>([]);
  const [monitorEnabled, setMonitorEnabled] = useState(false);
  const [savingToLib, setSavingToLib] = useState(false);
  const [savedToLib, setSavedToLib] = useState(false);

  /* ---------- auth state ---------- */
  const [authStatus, setAuthStatus] = useState<GitHubAuthStatus>({ authenticated: false });

  /* ---------- mobile ---------- */
  const isMobile = useIsMobile();

  /* ---------------------------------------------------------------- */
  /*  Initial data loading                                             */
  /* ---------------------------------------------------------------- */

  const loadAuth = useCallback(async () => {
    const status = await getAuthStatus();
    setAuthStatus(status);
  }, []);

  const loadStarred = useCallback(async () => {
    setLoading(true);
    const result = await fetchStarred();
    setStarredRepos(result.repos);
    setLoading(false);
  }, []);

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    const result = await fetchNotifications();
    setNotifications(result.notifications);
    setUnreadCount(result.unread_count);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadAuth();
    loadStarred();
    loadNotifications();
  }, [loadAuth, loadStarred, loadNotifications]);

  /* ---------------------------------------------------------------- */
  /*  Section switching                                                */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    setView("list");
    setDetail(null);
    setSearch("");
    if (activeSection === "starred" || activeSection === "watched") {
      loadStarred();
    } else if (activeSection === "notifications") {
      loadNotifications();
    }
  }, [activeSection, loadStarred, loadNotifications]);

  /* ---------------------------------------------------------------- */
  /*  Open detail                                                      */
  /* ---------------------------------------------------------------- */

  const openRepoDetail = useCallback(async (repo: GitHubRepo) => {
    setView("detail");
    setDetail({ type: "repo", repo });
    setSavedToLib(false);
    setMonitorEnabled(false);
    setDetailLoading(true);
    const [releases, full] = await Promise.all([
      fetchReleases(repo.owner, repo.name),
      fetchRepo(repo.owner, repo.name),
    ]);
    setDetailReleases(releases);
    if (full) {
      setDetail({ type: "repo", repo: full });
    }
    setDetailLoading(false);
  }, []);

  const openIssueDetail = useCallback(async (issue: GitHubIssue) => {
    setView("detail");
    setDetail({ type: "issue", issue });
    setSavedToLib(false);
    setDetailLoading(true);
    const [owner, repoName] = issue.repo.split("/");
    if (owner && repoName) {
      const full = await fetchIssue(owner, repoName, issue.number);
      if (full) setDetail({ type: "issue", issue: full });
    }
    setDetailLoading(false);
  }, []);

  const openReleaseDetail = useCallback((release: GitHubRelease, repoFullName: string) => {
    setView("detail");
    setDetail({ type: "release", release: { ...release, repo: repoFullName } as GitHubRelease & { repo: string } });
    setSavedToLib(false);
  }, []);

  const goBack = useCallback(() => {
    setView("list");
    setDetail(null);
    setDetailReleases([]);
  }, []);

  /* ---------- selectedId for MobileSplitView ---------- */
  const selectedId = useMemo((): string | null => {
    if (!detail) return null;
    if (detail.type === "repo" && detail.repo) return `repo:${detail.repo.owner}/${detail.repo.name}`;
    if (detail.type === "issue" && detail.issue) return `issue:${detail.issue.repo}#${detail.issue.number}`;
    if (detail.type === "release" && detail.release) return `release:${detail.release.tag}`;
    return null;
  }, [detail]);

  /* ---------------------------------------------------------------- */
  /*  Save to library                                                  */
  /* ---------------------------------------------------------------- */

  const handleSaveToLibrary = useCallback(async (url: string) => {
    setSavingToLib(true);
    const result = await saveToLibrary(url);
    setSavingToLib(false);
    if (result) setSavedToLib(true);
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Filtered list items                                              */
  /* ---------------------------------------------------------------- */

  const activeItems = useMemo(() => {
    if (activeSection === "starred" || activeSection === "watched") {
      const repos = activeSection === "watched" ? watched : starredRepos;
      return repos.filter((r) => {
        if (!search) return true;
        const q = search.toLowerCase();
        return (
          r.name.toLowerCase().includes(q) ||
          r.owner.toLowerCase().includes(q) ||
          r.description?.toLowerCase().includes(q)
        );
      });
    }
    if (activeSection === "notifications") {
      return notifications.filter((n) => {
        if (!search) return true;
        const q = search.toLowerCase();
        return n.title.toLowerCase().includes(q) || n.repo.toLowerCase().includes(q);
      });
    }
    return [];
  }, [activeSection, starredRepos, watched, notifications, search]);

  /* ---------------------------------------------------------------- */
  /*  Sidebar UI                                                       */
  /* ---------------------------------------------------------------- */

  const sidebarUI = (
    <nav
      className="w-52 shrink-0 border-r border-white/5 bg-shell-surface/30 flex flex-col overflow-hidden"
      aria-label="GitHub Browser navigation"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-white/5 shrink-0">
        <Github size={15} className="text-accent" aria-hidden="true" />
        <h1 className="text-sm font-semibold">GitHub</h1>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {/* --- Sections --- */}
        <section aria-label="Sections">
          <div className="space-y-0.5">
            <Button
              variant={activeSection === "starred" ? "secondary" : "ghost"}
              size="sm"
              aria-pressed={activeSection === "starred"}
              onClick={() => setActiveSection("starred")}
              className="w-full justify-start text-xs h-7 px-2 gap-1.5"
            >
              <Star size={11} aria-hidden="true" />
              Starred Repos
            </Button>
            <Button
              variant={activeSection === "notifications" ? "secondary" : "ghost"}
              size="sm"
              aria-pressed={activeSection === "notifications"}
              onClick={() => setActiveSection("notifications")}
              className="w-full justify-between text-xs h-7 px-2"
            >
              <span className="flex items-center gap-1.5">
                <Bell size={11} aria-hidden="true" />
                Notifications
              </span>
              {unreadCount > 0 && (
                <span
                  className="px-1.5 py-0.5 rounded-full bg-accent text-white text-[10px] tabular-nums"
                  aria-label={`${unreadCount} unread`}
                >
                  {unreadCount}
                </span>
              )}
            </Button>
            <Button
              variant={activeSection === "watched" ? "secondary" : "ghost"}
              size="sm"
              aria-pressed={activeSection === "watched"}
              onClick={() => setActiveSection("watched")}
              className="w-full justify-start text-xs h-7 px-2 gap-1.5"
            >
              <Eye size={11} aria-hidden="true" />
              Watched
            </Button>
          </div>
        </section>

        {/* --- Content Type --- */}
        <section aria-label="Content type">
          <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary px-2 mb-1.5">
            Content
          </p>
          <div className="space-y-0.5">
            {(
              [
                { id: "repos" as ContentType, label: "Repos", icon: Github },
                { id: "issues" as ContentType, label: "Issues", icon: CircleDot },
                { id: "prs" as ContentType, label: "Pull Requests", icon: GitPullRequest },
                { id: "releases" as ContentType, label: "Releases", icon: Package },
              ] as const
            ).map(({ id, label, icon: Icon }) => (
              <Button
                key={id}
                variant={contentType === id ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={contentType === id}
                onClick={() => setContentType(id)}
                className="w-full justify-start text-xs h-7 px-2 gap-1.5"
              >
                <Icon size={11} aria-hidden="true" />
                {label}
              </Button>
            ))}
          </div>
        </section>

        {/* --- Status --- */}
        <section aria-label="Status filter">
          <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary px-2 mb-1.5">
            Status
          </p>
          <div className="space-y-0.5">
            {(["open", "closed", "merged"] as const).map((s) => {
              const active = filterStatus === s;
              return (
                <Button
                  key={s}
                  variant={active ? "secondary" : "ghost"}
                  size="sm"
                  aria-pressed={active}
                  onClick={() => setFilterStatus((prev) => (prev === s ? null : s))}
                  className="w-full justify-start text-xs h-7 px-2 capitalize"
                >
                  {s}
                </Button>
              );
            })}
          </div>
        </section>
      </div>

      {/* Auth status at bottom */}
      <div className="shrink-0 border-t border-white/5 px-3 py-2">
        {authStatus.authenticated ? (
          <div className="space-y-0.5">
            <p className="text-[10px] text-shell-text-tertiary capitalize">
              {authStatus.method ?? "connected"}
            </p>
            <p className="text-xs text-shell-text-secondary truncate">
              @{authStatus.username}
            </p>
          </div>
        ) : (
          <button
            className="text-xs text-accent hover:underline"
            onClick={() => {
              /* links to Secrets app — no-op in UI, user can navigate manually */
            }}
            aria-label="Connect GitHub account"
          >
            Connect GitHub
          </button>
        )}
      </div>
    </nav>
  );

  /* ---------------------------------------------------------------- */
  /*  Auth Banner                                                      */
  /* ---------------------------------------------------------------- */

  const authBanner = !authStatus.authenticated ? (
    <div
      className="flex items-center gap-3 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 text-xs text-amber-300 shrink-0"
      role="banner"
      aria-label="GitHub authentication notice"
    >
      <AlertCircle size={13} aria-hidden="true" />
      <span>Connect GitHub for starred repos and notifications.</span>
      <button
        className="ml-auto underline hover:text-amber-200"
        aria-label="Open Secrets app to connect GitHub"
      >
        Connect
      </button>
    </div>
  ) : null;

  /* ---------------------------------------------------------------- */
  /*  Repo card                                                        */
  /* ---------------------------------------------------------------- */

  const repoCard = (repo: GitHubRepo) => (
    <Card
      key={`${repo.owner}/${repo.name}`}
      className="cursor-pointer hover:border-white/15 transition-colors"
      onClick={() => openRepoDetail(repo)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openRepoDetail(repo);
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`Open ${repo.owner}/${repo.name}`}
    >
      <CardHeader className="pb-1 p-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-medium leading-snug">
            <span className="text-shell-text-tertiary">{repo.owner}/</span>
            {repo.name}
          </h3>
          {repo.language && (
            <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">
              {repo.language}
            </span>
          )}
        </div>
        {repo.description && (
          <p className="text-[11px] text-shell-text-secondary line-clamp-1 leading-relaxed mt-0.5">
            {repo.description}
          </p>
        )}
      </CardHeader>
      <CardContent className="pt-0 px-3 pb-3">
        <div className="flex items-center gap-3 text-[10px] text-shell-text-tertiary">
          <span className="flex items-center gap-1" aria-label={`${repo.stars} stars`}>
            <Star size={10} aria-hidden="true" />
            {repo.stars.toLocaleString()}
          </span>
          <span className="flex items-center gap-1" aria-label={`${repo.forks} forks`}>
            <GitFork size={10} aria-hidden="true" />
            {repo.forks.toLocaleString()}
          </span>
          <span className="ml-auto">{formatDate(repo.updated_at)}</span>
        </div>
      </CardContent>
    </Card>
  );

  /* ---------------------------------------------------------------- */
  /*  Issue card                                                       */
  /* ---------------------------------------------------------------- */

  const issueCard = (issue: GitHubIssue) => (
    <Card
      key={`${issue.repo}#${issue.number}`}
      className="cursor-pointer hover:border-white/15 transition-colors"
      onClick={() => openIssueDetail(issue)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openIssueDetail(issue);
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`Open ${issue.is_pull_request ? "PR" : "issue"}: ${issue.title}`}
    >
      <CardHeader className="pb-1 p-3">
        <div className="flex items-start gap-2">
          {issue.is_pull_request ? (
            <GitPullRequest size={13} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
          ) : (
            <CircleDot size={13} className="mt-0.5 shrink-0 text-green-400" aria-hidden="true" />
          )}
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-medium leading-snug line-clamp-1">{issue.title}</h3>
            <p className="text-[11px] text-shell-text-tertiary mt-0.5">{issue.repo}</p>
          </div>
          <span
            className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded border ${stateColor(issue.state)}`}
            aria-label={`Status: ${issue.state}`}
          >
            {issue.state}
          </span>
        </div>
      </CardHeader>
      <CardContent className="pt-0 px-3 pb-3 space-y-1.5">
        {issue.labels.length > 0 && (
          <div className="flex flex-wrap gap-1" aria-label="Labels">
            {issue.labels.map((label) => (
              <span
                key={label}
                className="px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-[10px] text-shell-text-secondary"
              >
                {label}
              </span>
            ))}
          </div>
        )}
        <div className="flex items-center gap-3 text-[10px] text-shell-text-tertiary">
          <span className="flex items-center gap-1">
            <MessageSquare size={10} aria-hidden="true" />
            {issue.comments.length}
          </span>
          <span>{issue.author}</span>
          <span className="ml-auto">{formatDate(issue.created_at)}</span>
        </div>
      </CardContent>
    </Card>
  );

  /* ---------------------------------------------------------------- */
  /*  Release card                                                     */
  /* ---------------------------------------------------------------- */

  const releaseCard = (release: GitHubRelease, repoFullName = "") => (
    <Card
      key={release.tag}
      className="cursor-pointer hover:border-white/15 transition-colors"
      onClick={() => openReleaseDetail(release, repoFullName)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openReleaseDetail(release, repoFullName);
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`Open release ${release.tag}`}
    >
      <CardHeader className="pb-1 p-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-medium leading-snug flex items-center gap-1.5">
              <Tag size={11} aria-hidden="true" className="text-accent" />
              {release.tag}
            </h3>
            {repoFullName && (
              <p className="text-[11px] text-shell-text-tertiary mt-0.5">{repoFullName}</p>
            )}
          </div>
          {release.prerelease && (
            <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
              pre-release
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0 px-3 pb-3">
        <p className="text-[10px] text-shell-text-tertiary">{formatDate(release.published_at)}</p>
      </CardContent>
    </Card>
  );

  /* ---------------------------------------------------------------- */
  /*  List View                                                        */
  /* ---------------------------------------------------------------- */

  const listViewUI = (
    <main className="flex-1 flex flex-col overflow-hidden" aria-label="GitHub content list">
      {/* Search bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5 shrink-0">
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-shell-text-tertiary pointer-events-none z-10"
            aria-hidden="true"
          />
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="pl-8 h-8"
            aria-label="Search GitHub content"
          />
        </div>
      </div>

      {/* Items */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2" role="list" aria-label="GitHub items">
        {loading ? (
          <div
            className="flex items-center justify-center h-full text-shell-text-tertiary text-sm"
            role="status"
            aria-live="polite"
          >
            Loading…
          </div>
        ) : activeItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-shell-text-tertiary">
            <Github size={36} className="opacity-20" aria-hidden="true" />
            <p className="text-sm">
              {search ? "No results for your search" : "Nothing here yet"}
            </p>
          </div>
        ) : activeSection === "notifications" ? (
          (activeItems as GitHubIssue[]).map((item) => (
            <div key={`${item.repo}#${item.number}`} role="listitem">
              {issueCard(item)}
            </div>
          ))
        ) : (
          (activeItems as GitHubRepo[]).map((item) => (
            <div key={`${item.owner}/${item.name}`} role="listitem">
              {repoCard(item)}
            </div>
          ))
        )}
      </div>
    </main>
  );

  /* ---------------------------------------------------------------- */
  /*  Repo Detail View                                                 */
  /* ---------------------------------------------------------------- */

  const repoDetailUI = (repo: GitHubRepo) => {
    const repoUrl = `https://github.com/${repo.owner}/${repo.name}`;
    const latestRelease = detailReleases[0] ?? null;

    return (
      <main className="flex-1 flex flex-col overflow-hidden" aria-label={`${repo.owner}/${repo.name} detail`}>
        <div className="flex-1 overflow-y-auto">
          {/* Back + header */}
          <div className="px-5 pt-4 pb-3 border-b border-white/5">
            {/* Hide back button on mobile — MobileSplitView nav bar handles back */}
            {!isMobile && (
              <Button
                variant="ghost"
                size="sm"
                onClick={goBack}
                className="text-xs mb-3 -ml-1 text-shell-text-secondary"
                aria-label="Back to list"
                onKeyDown={(e) => e.key === "Escape" && goBack()}
              >
                <ChevronLeft size={14} aria-hidden="true" />
                Back
              </Button>
            )}

            <h2 className="text-lg font-semibold leading-snug mb-1">
              <span className="text-shell-text-tertiary">{repo.owner}/</span>
              {repo.name}
            </h2>
            {repo.description && (
              <p className="text-sm text-shell-text-secondary mb-3">{repo.description}</p>
            )}

            {/* Badges */}
            <div className="flex flex-wrap gap-2 mb-3">
              <span
                className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-shell-text-secondary"
                aria-label={`${repo.stars} stars`}
              >
                <Star size={10} aria-hidden="true" />
                {repo.stars.toLocaleString()} stars
              </span>
              <span
                className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-shell-text-secondary"
                aria-label={`${repo.forks} forks`}
              >
                <GitFork size={10} aria-hidden="true" />
                {repo.forks.toLocaleString()} forks
              </span>
              {repo.language && (
                <span className="text-[11px] px-2 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">
                  {repo.language}
                </span>
              )}
              {repo.license && (
                <span className="text-[11px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-shell-text-secondary">
                  {repo.license}
                </span>
              )}
            </div>

            {/* Topics */}
            {repo.topics.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2" aria-label="Topics">
                {repo.topics.map((t) => (
                  <span
                    key={t}
                    className="px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 text-[10px] border border-blue-500/20"
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* README */}
          {repo.readme_content && (
            <div className="px-5 py-4 border-b border-white/5">
              <h3 className="text-xs font-semibold text-shell-text-tertiary uppercase tracking-wider mb-2">
                README
              </h3>
              <div className="rounded-lg bg-white/[0.02] border border-white/5 p-3 max-h-64 overflow-y-auto">
                <pre className="text-xs text-shell-text-secondary whitespace-pre-wrap leading-relaxed font-sans">
                  {detailLoading ? "Loading…" : repo.readme_content}
                </pre>
              </div>
            </div>
          )}

          {/* Latest release */}
          {latestRelease && (
            <div className="px-5 py-4 border-b border-white/5">
              <h3 className="text-xs font-semibold text-shell-text-tertiary uppercase tracking-wider mb-2">
                Latest Release
              </h3>
              {releaseCard(latestRelease, `${repo.owner}/${repo.name}`)}
            </div>
          )}

          {/* Monitor toggle */}
          <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between">
            <label
              htmlFor={`monitor-${repo.name}`}
              className="text-xs text-shell-text-secondary cursor-pointer"
            >
              Monitor releases
            </label>
            <Switch
              id={`monitor-${repo.name}`}
              checked={monitorEnabled}
              onCheckedChange={setMonitorEnabled}
              aria-label="Monitor releases for this repository"
            />
          </div>

          {/* Action bar */}
          <div className="px-5 py-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="text-xs gap-1.5"
              onClick={() => window.open(repoUrl, "_blank", "noopener,noreferrer")}
              aria-label="Open on GitHub"
            >
              <ExternalLink size={13} aria-hidden="true" />
              Open on GitHub
            </Button>
            <Button
              size="sm"
              variant={savedToLib ? "secondary" : "outline"}
              className="text-xs gap-1.5"
              onClick={() => handleSaveToLibrary(repoUrl)}
              disabled={savingToLib || savedToLib}
              aria-label={savedToLib ? "Saved to library" : "Save to Library"}
            >
              <BookMarked size={13} aria-hidden="true" />
              {savedToLib ? "Saved" : savingToLib ? "Saving…" : "Save to Library"}
            </Button>
          </div>
        </div>
      </main>
    );
  };

  /* ---------------------------------------------------------------- */
  /*  Issue Detail View                                                */
  /* ---------------------------------------------------------------- */

  const issueDetailUI = (issue: GitHubIssue) => {
    const issueUrl = `https://github.com/${issue.repo}/${issue.is_pull_request ? "pull" : "issues"}/${issue.number}`;

    return (
      <main className="flex-1 flex flex-col overflow-hidden" aria-label={`Issue ${issue.number} detail`}>
        <div className="flex-1 overflow-y-auto">
          {/* Back + header */}
          <div className="px-5 pt-4 pb-3 border-b border-white/5">
            {/* Hide back button on mobile — MobileSplitView nav bar handles back */}
            {!isMobile && (
              <Button
                variant="ghost"
                size="sm"
                onClick={goBack}
                className="text-xs mb-3 -ml-1 text-shell-text-secondary"
                aria-label="Back to list"
                onKeyDown={(e) => e.key === "Escape" && goBack()}
              >
                <ChevronLeft size={14} aria-hidden="true" />
                Back
              </Button>
            )}

            <div className="flex items-start gap-2 mb-2">
              {issue.is_pull_request ? (
                <GitPullRequest size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
              ) : (
                <CircleDot size={16} className="mt-0.5 shrink-0 text-green-400" aria-hidden="true" />
              )}
              <h2 className="text-base font-semibold leading-snug flex-1">{issue.title}</h2>
              <span
                className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded border ${stateColor(issue.state)}`}
                aria-label={`Status: ${issue.state}`}
              >
                {issue.state}
              </span>
            </div>

            <p className="text-xs text-shell-text-tertiary mb-2">
              {issue.repo} · {issue.author} · {formatDate(issue.created_at)}
            </p>

            {issue.labels.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2" aria-label="Labels">
                {issue.labels.map((label) => (
                  <span
                    key={label}
                    className="px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-[10px] text-shell-text-secondary"
                  >
                    {label}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Tabs */}
          <div className="px-5 py-3 flex-1">
            <Tabs defaultValue="discussion">
              <TabsList>
                <TabsTrigger value="discussion">Discussion</TabsTrigger>
                <TabsTrigger value="history">History</TabsTrigger>
                <TabsTrigger value="metadata">Metadata</TabsTrigger>
              </TabsList>

              {/* Discussion tab */}
              <TabsContent value="discussion">
                {/* Body */}
                {issue.body && (
                  <div className="rounded-lg bg-white/[0.02] border border-white/5 p-3 mb-3 mt-3">
                    <p className="text-xs text-shell-text-secondary whitespace-pre-wrap leading-relaxed">
                      {detailLoading ? "Loading…" : issue.body}
                    </p>
                  </div>
                )}

                {/* Comments */}
                {issue.comments.length > 0 && (
                  <div className="space-y-2 mt-2" aria-label="Comments">
                    <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary mb-1">
                      {issue.comments.length} comment{issue.comments.length !== 1 ? "s" : ""}
                    </p>
                    {issue.comments.map((comment, idx) => (
                      <CommentNode key={idx} comment={comment} depth={0} />
                    ))}
                  </div>
                )}
              </TabsContent>

              {/* History tab */}
              <TabsContent value="history">
                <div className="mt-3 text-xs text-shell-text-tertiary italic">
                  Issue history not available in this view.
                </div>
              </TabsContent>

              {/* Metadata tab */}
              <TabsContent value="metadata">
                <div className="mt-3 space-y-2">
                  {[
                    { label: "Number", value: `#${issue.number}` },
                    { label: "State", value: issue.state },
                    { label: "Author", value: issue.author },
                    { label: "Repo", value: issue.repo },
                    { label: "Type", value: issue.is_pull_request ? "Pull Request" : "Issue" },
                    { label: "Created", value: issue.created_at },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex justify-between text-xs">
                      <span className="text-shell-text-tertiary">{label}</span>
                      <span className="text-shell-text-secondary">{value}</span>
                    </div>
                  ))}
                </div>
              </TabsContent>
            </Tabs>
          </div>

          {/* Action bar */}
          <div className="px-5 py-3 flex flex-wrap gap-2 border-t border-white/5">
            <Button
              size="sm"
              variant="ghost"
              className="text-xs gap-1.5"
              onClick={() => window.open(issueUrl, "_blank", "noopener,noreferrer")}
              aria-label="Open on GitHub"
            >
              <ExternalLink size={13} aria-hidden="true" />
              Open on GitHub
            </Button>
            <Button
              size="sm"
              variant={savedToLib ? "secondary" : "outline"}
              className="text-xs gap-1.5"
              onClick={() => handleSaveToLibrary(issueUrl)}
              disabled={savingToLib || savedToLib}
              aria-label={savedToLib ? "Saved to library" : "Save to Library"}
            >
              <BookMarked size={13} aria-hidden="true" />
              {savedToLib ? "Saved" : savingToLib ? "Saving…" : "Save to Library"}
            </Button>
          </div>
        </div>
      </main>
    );
  };

  /* ---------------------------------------------------------------- */
  /*  Release Detail View                                              */
  /* ---------------------------------------------------------------- */

  const releaseDetailUI = (release: GitHubRelease & { repo?: string }) => {
    const repoFullName = release.repo ?? "";
    const releaseUrl = repoFullName
      ? `https://github.com/${repoFullName}/releases/tag/${encodeURIComponent(release.tag)}`
      : "#";

    return (
      <main className="flex-1 flex flex-col overflow-hidden" aria-label={`Release ${release.tag} detail`}>
        <div className="flex-1 overflow-y-auto">
          {/* Back + header */}
          <div className="px-5 pt-4 pb-3 border-b border-white/5">
            {/* Hide back button on mobile — MobileSplitView nav bar handles back */}
            {!isMobile && (
              <Button
                variant="ghost"
                size="sm"
                onClick={goBack}
                className="text-xs mb-3 -ml-1 text-shell-text-secondary"
                aria-label="Back to list"
                onKeyDown={(e) => e.key === "Escape" && goBack()}
              >
                <ChevronLeft size={14} aria-hidden="true" />
                Back
              </Button>
            )}

            <div className="flex items-start gap-2 mb-1">
              <Tag size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
              <h2 className="text-lg font-semibold leading-snug">{release.tag}</h2>
              {release.prerelease && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                  pre-release
                </span>
              )}
            </div>
            {repoFullName && (
              <p className="text-xs text-shell-text-tertiary mb-1">{repoFullName}</p>
            )}
            <p className="text-xs text-shell-text-tertiary">
              {release.author} · {formatDate(release.published_at)}
            </p>
          </div>

          {/* Release notes */}
          {release.body && (
            <div className="px-5 py-4 border-b border-white/5">
              <h3 className="text-xs font-semibold text-shell-text-tertiary uppercase tracking-wider mb-2">
                Release Notes
              </h3>
              <pre className="text-xs text-shell-text-secondary whitespace-pre-wrap leading-relaxed font-sans">
                {release.body}
              </pre>
            </div>
          )}

          {/* Assets */}
          {release.assets.length > 0 && (
            <div className="px-5 py-4 border-b border-white/5">
              <h3 className="text-xs font-semibold text-shell-text-tertiary uppercase tracking-wider mb-2">
                Assets ({release.assets.length})
              </h3>
              <div className="space-y-1.5" role="list" aria-label="Release assets">
                {release.assets.map((asset) => (
                  <div
                    key={asset.name}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/5 text-xs"
                    role="listitem"
                  >
                    <Download size={11} aria-hidden="true" className="text-shell-text-tertiary shrink-0" />
                    <span className="flex-1 truncate text-shell-text-secondary font-mono">
                      {asset.name}
                    </span>
                    <span className="text-shell-text-tertiary shrink-0">
                      {formatBytes(asset.size)}
                    </span>
                    <span
                      className="text-shell-text-tertiary shrink-0"
                      aria-label={`${asset.download_count} downloads`}
                    >
                      {asset.download_count.toLocaleString()} dl
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action bar */}
          <div className="px-5 py-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="text-xs gap-1.5"
              onClick={() => window.open(releaseUrl, "_blank", "noopener,noreferrer")}
              aria-label="Open on GitHub"
            >
              <ExternalLink size={13} aria-hidden="true" />
              Open on GitHub
            </Button>
            <Button
              size="sm"
              variant={savedToLib ? "secondary" : "outline"}
              className="text-xs gap-1.5"
              onClick={() => handleSaveToLibrary(releaseUrl)}
              disabled={savingToLib || savedToLib || releaseUrl === "#"}
              aria-label={savedToLib ? "Saved to library" : "Save to Library"}
            >
              <BookMarked size={13} aria-hidden="true" />
              {savedToLib ? "Saved" : savingToLib ? "Saving…" : "Save to Library"}
            </Button>
          </div>
        </div>
      </main>
    );
  };

  /* ---------------------------------------------------------------- */
  /*  Detail dispatch                                                  */
  /* ---------------------------------------------------------------- */

  const detailUI = detail ? (() => {
    if (detail.type === "repo" && detail.repo) return repoDetailUI(detail.repo);
    if (detail.type === "issue" && detail.issue) return issueDetailUI(detail.issue);
    if (detail.type === "release" && detail.release)
      return releaseDetailUI(detail.release as GitHubRelease & { repo?: string });
    return null;
  })() : null;

  /* ---------------------------------------------------------------- */
  /*  Detail title for mobile nav bar                                  */
  /* ---------------------------------------------------------------- */

  const detailTitle = useMemo(() => {
    if (!detail) return "";
    if (detail.type === "repo" && detail.repo) return `${detail.repo.owner}/${detail.repo.name}`;
    if (detail.type === "issue" && detail.issue) return detail.issue.title;
    if (detail.type === "release" && detail.release) return detail.release.tag;
    return "";
  }, [detail]);

  // Hide toolbar on mobile when detail is open — MobileSplitView nav bar is shown instead
  const showToolbar = !isMobile || selectedId === null;

  /* ---------------------------------------------------------------- */
  /*  Mobile iOS-style list pane (sidebar sections + item list)        */
  /* ---------------------------------------------------------------- */

  const mobileListPane = (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {authBanner}
      {/* Sections */}
      <div style={{ padding: "8px 0 4px", borderBottom: "1px solid rgba(255,255,255,0.05)", flexShrink: 0 }}>
        <div style={{ margin: "0 12px", borderRadius: 16, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", overflow: "hidden" }}>
          {(
            [
              { id: "starred" as SidebarSection, label: "Starred Repos", icon: Star, badge: null as number | null },
              { id: "notifications" as SidebarSection, label: "Notifications", icon: Bell, badge: unreadCount as number | null },
              { id: "watched" as SidebarSection, label: "Watched", icon: Eye, badge: null as number | null },
            ]
          ).map(({ id, label, icon: Icon, badge }, idx, arr) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveSection(id)}
              aria-pressed={activeSection === id}
              aria-label={label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                width: "100%",
                padding: "14px 16px",
                background: activeSection === id ? "rgba(255,255,255,0.08)" : "none",
                border: "none",
                borderBottom: idx === arr.length - 1 ? "none" : "1px solid rgba(255,255,255,0.06)",
                cursor: "pointer",
                color: "inherit",
                textAlign: "left",
              }}
            >
              <Icon size={15} style={{ color: "rgba(255,255,255,0.6)", flexShrink: 0 }} aria-hidden="true" />
              <span style={{ flex: 1, fontSize: 15, fontWeight: 500, color: "rgba(255,255,255,0.9)" }}>{label}</span>
              {badge != null && badge > 0 && (
                <span style={{ fontSize: 11, padding: "1px 7px", borderRadius: 20, background: "var(--accent, #7c6be8)", color: "#fff", fontWeight: 600 }} aria-label={`${badge} unread`}>
                  {badge}
                </span>
              )}
              <ChevronRight size={14} style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }} aria-hidden="true" />
            </button>
          ))}
        </div>
      </div>

      {/* Content type filter */}
      <div style={{ padding: "8px 0 4px", borderBottom: "1px solid rgba(255,255,255,0.05)", flexShrink: 0 }}>
        <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.45)", padding: "0 20px 6px", fontWeight: 600 }}>
          Content
        </div>
        <div style={{ margin: "0 12px", borderRadius: 16, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", overflow: "hidden" }}>
          {(
            [
              { id: "repos" as ContentType, label: "Repos", icon: Github },
              { id: "issues" as ContentType, label: "Issues", icon: CircleDot },
              { id: "prs" as ContentType, label: "Pull Requests", icon: GitPullRequest },
              { id: "releases" as ContentType, label: "Releases", icon: Package },
            ] as const
          ).map(({ id, label, icon: Icon }, idx, arr) => (
            <button
              key={id}
              type="button"
              onClick={() => setContentType(id)}
              aria-pressed={contentType === id}
              aria-label={label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                width: "100%",
                padding: "12px 16px",
                background: contentType === id ? "rgba(255,255,255,0.08)" : "none",
                border: "none",
                borderBottom: idx === arr.length - 1 ? "none" : "1px solid rgba(255,255,255,0.06)",
                cursor: "pointer",
                color: "inherit",
                textAlign: "left",
              }}
            >
              <Icon size={14} style={{ color: "rgba(255,255,255,0.6)", flexShrink: 0 }} aria-hidden="true" />
              <span style={{ flex: 1, fontSize: 14, color: "rgba(255,255,255,0.85)" }}>{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Items list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0 16px" }}>
        <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.45)", padding: "4px 20px 8px", fontWeight: 600 }}>
          {activeSection === "notifications" ? "Notifications" : activeSection === "watched" ? "Watched" : "Starred"}
        </div>

        {/* Search */}
        <div style={{ padding: "0 12px 8px" }}>
          <div style={{ position: "relative" }}>
            <Search size={13} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "rgba(255,255,255,0.4)", pointerEvents: "none" }} aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              aria-label="Search GitHub content"
              style={{
                width: "100%",
                padding: "8px 12px 8px 30px",
                borderRadius: 10,
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "inherit",
                fontSize: 13,
                outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "rgba(255,255,255,0.4)" }} role="status" aria-live="polite">
            Loading…
          </div>
        ) : activeItems.length === 0 ? (
          <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "rgba(255,255,255,0.4)" }}>
            {search ? "No results for your search" : "Nothing here yet"}
          </div>
        ) : (
          <div
            style={{ margin: "0 12px", borderRadius: 16, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", overflow: "hidden" }}
            role="list"
            aria-label="GitHub items"
          >
            {activeSection === "notifications"
              ? (activeItems as GitHubIssue[]).map((item, idx, arr) => (
                  <button
                    key={`${item.repo}#${item.number}`}
                    type="button"
                    role="listitem"
                    onClick={() => openIssueDetail(item)}
                    aria-label={`Open ${item.is_pull_request ? "PR" : "issue"}: ${item.title}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      width: "100%",
                      padding: "14px 16px",
                      background: "none",
                      border: "none",
                      borderBottom: idx === arr.length - 1 ? "none" : "1px solid rgba(255,255,255,0.06)",
                      cursor: "pointer",
                      color: "inherit",
                      textAlign: "left",
                    }}
                  >
                    {item.is_pull_request
                      ? <GitPullRequest size={13} style={{ flexShrink: 0, color: "rgba(130,140,255,0.9)" }} aria-hidden="true" />
                      : <CircleDot size={13} style={{ flexShrink: 0, color: "rgba(80,200,120,0.9)" }} aria-hidden="true" />
                    }
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 500, color: "rgba(255,255,255,0.9)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 2 }}>
                        {item.title}
                      </div>
                      <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)" }}>{item.repo}</div>
                    </div>
                    <ChevronRight size={14} style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }} aria-hidden="true" />
                  </button>
                ))
              : (activeItems as GitHubRepo[]).map((item, idx, arr) => (
                  <button
                    key={`${item.owner}/${item.name}`}
                    type="button"
                    role="listitem"
                    onClick={() => openRepoDetail(item)}
                    aria-label={`Open ${item.owner}/${item.name}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      width: "100%",
                      padding: "14px 16px",
                      background: "none",
                      border: "none",
                      borderBottom: idx === arr.length - 1 ? "none" : "1px solid rgba(255,255,255,0.06)",
                      cursor: "pointer",
                      color: "inherit",
                      textAlign: "left",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: "rgba(255,255,255,0.95)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 2 }}>
                        <span style={{ color: "rgba(255,255,255,0.5)" }}>{item.owner}/</span>{item.name}
                      </div>
                      {item.description && (
                        <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {item.description}
                        </div>
                      )}
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4, fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 3 }} aria-label={`${item.stars} stars`}>
                          <Star size={9} aria-hidden="true" /> {item.stars.toLocaleString()}
                        </span>
                        <span style={{ display: "flex", alignItems: "center", gap: 3 }} aria-label={`${item.forks} forks`}>
                          <GitFork size={9} aria-hidden="true" /> {item.forks.toLocaleString()}
                        </span>
                        {item.language && <span>{item.language}</span>}
                      </div>
                    </div>
                    <ChevronRight size={14} style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }} aria-hidden="true" />
                  </button>
                ))
            }
          </div>
        )}
      </div>
    </div>
  );

  /* ---------------------------------------------------------------- */
  /*  Root layout                                                      */
  /* ---------------------------------------------------------------- */

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden bg-shell-surface text-shell-text select-none relative">
      {/* Toolbar — hidden on mobile when detail is shown */}
      {showToolbar && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0">
          <div className="flex items-center gap-2">
            <Github size={15} className="text-accent shrink-0" aria-hidden="true" />
            <h1 className="text-sm font-semibold">GitHub</h1>
          </div>
        </div>
      )}

      {/* MobileSplitView — stacks on mobile, splits on desktop */}
      <MobileSplitView
        selectedId={selectedId}
        onBack={goBack}
        listTitle="GitHub"
        detailTitle={detailTitle}
        listWidth={208}
        list={
          isMobile
            ? mobileListPane
            : (
              <div className="flex h-full overflow-hidden">
                {sidebarUI}
                <div className="flex-1 flex flex-col overflow-hidden">
                  {authBanner}
                  {listViewUI}
                </div>
              </div>
            )
        }
        detail={
          detailUI ?? (
            !isMobile ? (
              <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
                Select an item to view details
              </div>
            ) : null
          )
        }
      />
    </div>
  );
}
