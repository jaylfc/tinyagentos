import { useCallback, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  RotateCw,
  Globe,
  ExternalLink,
  Copy,
  Bookmark,
  Bot,
  Star,
} from "lucide-react";

const DEFAULT_URL = "https://duckduckgo.com";

const BOOKMARKS = [
  { name: "DuckDuckGo", url: "https://duckduckgo.com", icon: "🦆" },
  { name: "Wikipedia", url: "https://en.wikipedia.org", icon: "📚" },
  { name: "GitHub", url: "https://github.com", icon: "🐙" },
  { name: "Hacker News", url: "https://news.ycombinator.com", icon: "🟧" },
];

function proxyUrl(url: string): string {
  return `/api/desktop/proxy?url=${encodeURIComponent(url)}`;
}

function normalizeUrl(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return DEFAULT_URL;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export function BrowserApp({ windowId: _windowId }: { windowId: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [url, setUrl] = useState(DEFAULT_URL);
  const [inputValue, setInputValue] = useState(DEFAULT_URL);
  const [history, setHistory] = useState<string[]>([DEFAULT_URL]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [loadError, setLoadError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [agentTooltip, setAgentTooltip] = useState(false);

  const canGoBack = historyIndex > 0;
  const canGoForward = historyIndex < history.length - 1;

  const navigate = useCallback(
    (newUrl: string) => {
      const normalized = normalizeUrl(newUrl);
      setUrl(normalized);
      setInputValue(normalized);
      setLoadError(false);
      setHistory((prev) => [...prev.slice(0, historyIndex + 1), normalized]);
      setHistoryIndex((i) => i + 1);
    },
    [historyIndex],
  );

  const goBack = useCallback(() => {
    if (!canGoBack) return;
    const newIndex = historyIndex - 1;
    setHistoryIndex(newIndex);
    const target = history[newIndex] ?? DEFAULT_URL;
    setUrl(target);
    setInputValue(target);
    setLoadError(false);
  }, [canGoBack, history, historyIndex]);

  const goForward = useCallback(() => {
    if (!canGoForward) return;
    const newIndex = historyIndex + 1;
    setHistoryIndex(newIndex);
    const target = history[newIndex] ?? DEFAULT_URL;
    setUrl(target);
    setInputValue(target);
    setLoadError(false);
  }, [canGoForward, history, historyIndex]);

  const refresh = useCallback(() => {
    setLoadError(false);
    if (iframeRef.current) {
      iframeRef.current.src = proxyUrl(url);
    }
  }, [url]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate(inputValue);
  };

  const openInTab = useCallback(() => {
    window.open(url, "_blank", "noopener,noreferrer");
  }, [url]);

  const copyUrl = useCallback(() => {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [url]);

  const handleIframeError = useCallback(() => {
    setLoadError(true);
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Notice banner */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800 text-xs text-amber-700 dark:text-amber-400">
        <Globe size={12} className="shrink-0" />
        <span>
          Some sites may not render correctly in the embedded viewer. Use
          &lsquo;Open in Tab&rsquo; for full functionality.
        </span>
      </div>

      {/* Navigation bar */}
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-1.5 px-2 py-1.5 bg-shell-surface border-b border-shell-border"
      >
        <button
          type="button"
          onClick={goBack}
          disabled={!canGoBack}
          className="p-1.5 rounded-md hover:bg-shell-surface-hover disabled:opacity-30 transition-colors"
          aria-label="Back"
        >
          <ArrowLeft size={16} className="text-shell-text-secondary" />
        </button>
        <button
          type="button"
          onClick={goForward}
          disabled={!canGoForward}
          className="p-1.5 rounded-md hover:bg-shell-surface-hover disabled:opacity-30 transition-colors"
          aria-label="Forward"
        >
          <ArrowRight size={16} className="text-shell-text-secondary" />
        </button>
        <button
          type="button"
          onClick={refresh}
          className="p-1.5 rounded-md hover:bg-shell-surface-hover transition-colors"
          aria-label="Refresh"
        >
          <RotateCw size={16} className="text-shell-text-secondary" />
        </button>

        <div className="flex-1 flex items-center gap-2 px-2.5 py-1 rounded-md bg-shell-bg-deep border border-shell-border">
          <Globe size={14} className="text-shell-text-tertiary shrink-0" />
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            className="flex-1 bg-transparent text-sm text-shell-text outline-none placeholder:text-shell-text-tertiary"
            placeholder="Enter URL"
            aria-label="URL"
          />
        </div>

        {/* Action buttons */}
        <button
          type="button"
          onClick={openInTab}
          className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
          aria-label="Open in new tab"
          title="Open in new tab"
        >
          <ExternalLink size={14} />
          <span className="hidden sm:inline">Open in Tab</span>
        </button>

        <button
          type="button"
          onClick={copyUrl}
          className="p-1.5 rounded-md hover:bg-shell-surface-hover transition-colors relative"
          aria-label="Copy URL"
          title="Copy URL"
        >
          <Copy size={16} className="text-shell-text-secondary" />
          {copied && (
            <span className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-[10px] bg-shell-surface border border-shell-border rounded px-1 py-0.5 text-shell-text-secondary whitespace-nowrap z-10">
              Copied!
            </span>
          )}
        </button>

        <div className="relative">
          <button
            type="button"
            onMouseEnter={() => setAgentTooltip(true)}
            onMouseLeave={() => setAgentTooltip(false)}
            className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-purple-600/20 hover:bg-purple-600/30 text-purple-600 dark:text-purple-400 text-xs font-medium transition-colors border border-purple-600/30"
            aria-label="Agent Browse"
            title="Agent Browse"
          >
            <Bot size={14} />
            <span className="hidden sm:inline">Agent</span>
          </button>
          {agentTooltip && (
            <span className="absolute top-full right-0 mt-1 text-[10px] bg-shell-surface border border-shell-border rounded px-2 py-1 text-shell-text-secondary whitespace-nowrap z-10 shadow-md">
              Requires browser-use plugin
            </span>
          )}
        </div>
      </form>

      {/* Bookmarks bar */}
      <div className="flex items-center gap-1 px-2 py-1 bg-shell-surface/50 border-b border-shell-border">
        <Bookmark size={12} className="text-shell-text-tertiary shrink-0 mr-1" />
        {BOOKMARKS.map((bm) => (
          <button
            key={bm.url}
            type="button"
            onClick={() => navigate(bm.url)}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-xs text-shell-text-secondary hover:bg-shell-surface-hover hover:text-shell-text transition-colors"
            aria-label={`Go to ${bm.name}`}
          >
            <Star size={10} className="text-shell-text-tertiary" />
            <span>{bm.name}</span>
          </button>
        ))}
      </div>

      {/* Browser content */}
      {loadError ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8 text-center">
          <Globe size={48} className="text-shell-text-tertiary" />
          <div>
            <h3 className="text-lg font-medium text-shell-text mb-1">
              Could not load this page
            </h3>
            <p className="text-sm text-shell-text-secondary max-w-md">
              This site blocks embedded viewing. You can open it directly in a
              new browser tab instead.
            </p>
          </div>
          <button
            type="button"
            onClick={openInTab}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
          >
            <ExternalLink size={16} />
            Open in Tab
          </button>
        </div>
      ) : (
        <iframe
          ref={iframeRef}
          src={proxyUrl(url)}
          className="flex-1 w-full border-none bg-white"
          sandbox="allow-downloads allow-forms allow-modals allow-pointer-lock allow-popups allow-presentation allow-same-origin allow-scripts"
          title="Browser"
          onError={handleIframeError}
        />
      )}
    </div>
  );
}
