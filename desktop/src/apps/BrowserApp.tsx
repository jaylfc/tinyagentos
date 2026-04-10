import { useCallback, useEffect, useRef, useState } from "react";
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
  AlertTriangle,
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

function isIOS(): boolean {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

type BrowserMode = "embedded" | "external";

export function BrowserApp({ windowId: _windowId }: { windowId: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [url, setUrl] = useState(DEFAULT_URL);
  const [inputValue, setInputValue] = useState(DEFAULT_URL);
  const [history, setHistory] = useState<string[]>([DEFAULT_URL]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [agentTooltip, setAgentTooltip] = useState(false);
  const [mode, setMode] = useState<BrowserMode>(
    isIOS() ? "external" : "embedded",
  );

  const canGoBack = historyIndex > 0;
  const canGoForward = historyIndex < history.length - 1;

  const navigate = useCallback(
    (newUrl: string) => {
      const normalized = normalizeUrl(newUrl);
      setUrl(normalized);
      setInputValue(normalized);
      setLoadError(false);
      setLoading(true);
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
    setLoading(true);
  }, [canGoBack, history, historyIndex]);

  const goForward = useCallback(() => {
    if (!canGoForward) return;
    const newIndex = historyIndex + 1;
    setHistoryIndex(newIndex);
    const target = history[newIndex] ?? DEFAULT_URL;
    setUrl(target);
    setInputValue(target);
    setLoadError(false);
    setLoading(true);
  }, [canGoForward, history, historyIndex]);

  const refresh = useCallback(() => {
    setLoadError(false);
    setLoading(true);
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

  const handleIframeLoad = useCallback(() => {
    setLoading(false);
    // Check if iframe loaded successfully by trying to detect error responses
    try {
      const iframe = iframeRef.current;
      if (iframe) {
        // We can't access cross-origin content, but if the proxy returned
        // an error JSON, it will be same-origin and we can check
        try {
          const doc = iframe.contentDocument;
          if (doc) {
            const body = doc.body?.textContent?.trim() ?? "";
            // Proxy returns JSON errors like {"error": "..."}
            if (body.startsWith("{") && body.includes('"error"')) {
              setLoadError(true);
              return;
            }
          }
        } catch {
          // Cross-origin access blocked — means content loaded (good)
        }
      }
    } catch {
      // Ignore any inspection errors
    }
  }, []);

  const handleIframeError = useCallback(() => {
    setLoading(false);
    setLoadError(true);
  }, []);

  // Auto-detect: if on iOS, start in external mode
  useEffect(() => {
    if (isIOS()) {
      setMode("external");
    }
  }, []);

  // When in external mode and URL changes, don't auto-open — user clicks the button
  const toggleMode = useCallback(() => {
    setMode((m) => (m === "embedded" ? "external" : "embedded"));
    setLoadError(false);
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Navigation — URL row */}
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-1.5 px-2 py-1.5 bg-shell-surface border-b border-shell-border"
      >
        {/* Row 1: nav buttons + URL input */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={goBack}
            disabled={!canGoBack}
            className="p-1.5 rounded-md hover:bg-shell-surface-hover disabled:opacity-30 transition-colors shrink-0"
            aria-label="Back"
          >
            <ArrowLeft size={16} className="text-shell-text-secondary" />
          </button>
          <button
            type="button"
            onClick={goForward}
            disabled={!canGoForward}
            className="p-1.5 rounded-md hover:bg-shell-surface-hover disabled:opacity-30 transition-colors shrink-0"
            aria-label="Forward"
          >
            <ArrowRight size={16} className="text-shell-text-secondary" />
          </button>
          <button
            type="button"
            onClick={refresh}
            className="p-1.5 rounded-md hover:bg-shell-surface-hover transition-colors shrink-0"
            aria-label="Refresh"
          >
            <RotateCw
              size={16}
              className={`text-shell-text-secondary ${loading ? "animate-spin" : ""}`}
            />
          </button>

          <div className="flex-1 flex items-center gap-2 px-2.5 py-1 rounded-md bg-shell-bg-deep border border-shell-border min-w-0">
            <Globe size={14} className="text-shell-text-tertiary shrink-0" />
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              className="flex-1 bg-transparent text-sm text-shell-text outline-none placeholder:text-shell-text-tertiary min-w-0"
              placeholder="Enter URL"
              aria-label="URL"
            />
          </div>
        </div>

        {/* Row 2: action buttons */}
        <div className="flex items-center gap-1.5 justify-end">
          <button
            type="button"
            onClick={openInTab}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
            aria-label="Open in new tab"
            title="Open in new tab"
          >
            <ExternalLink size={12} />
            <span>Open in Tab</span>
          </button>

          <button
            type="button"
            onClick={toggleMode}
            className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors ${
              mode === "embedded"
                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25"
                : "bg-shell-surface-hover text-shell-text-secondary border border-shell-border"
            }`}
            aria-label={mode === "embedded" ? "Switch to external mode" : "Switch to embedded mode"}
            title={mode === "embedded" ? "Embedded mode" : "External mode"}
          >
            <Globe size={12} />
            <span>{mode === "embedded" ? "Embed" : "Ext"}</span>
          </button>

          <button
            type="button"
            onClick={copyUrl}
            className="p-1.5 rounded-md hover:bg-shell-surface-hover transition-colors relative"
            aria-label="Copy URL"
            title="Copy URL"
          >
            <Copy size={14} className="text-shell-text-secondary" />
            {copied && (
              <span className="absolute -bottom-6 right-0 text-[10px] bg-shell-surface border border-shell-border rounded px-1 py-0.5 text-shell-text-secondary whitespace-nowrap z-10">
                Copied!
              </span>
            )}
          </button>

          <button
            type="button"
            onMouseEnter={() => setAgentTooltip(true)}
            onMouseLeave={() => setAgentTooltip(false)}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-purple-500/15 hover:bg-purple-500/25 text-purple-400 text-xs transition-colors border border-purple-500/25 relative"
            aria-label="Agent Browse"
            title="Agent Browse"
          >
            <Bot size={12} />
            <span>Agent</span>
            {agentTooltip && (
              <span className="absolute top-full right-0 mt-1 text-[10px] bg-shell-surface border border-shell-border rounded px-2 py-1 text-shell-text-secondary whitespace-nowrap z-10 shadow-md">
                Requires browser-use plugin
              </span>
            )}
          </button>
        </div>
      </form>

      {/* Bookmarks bar */}
      <div className="flex items-center gap-1 px-2 py-1 bg-shell-surface/50 border-b border-shell-border">
        <Bookmark
          size={12}
          className="text-shell-text-tertiary shrink-0 mr-1"
        />
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
      {mode === "external" ? (
        /* External mode — show prompt to open in tab */
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8 text-center">
          <Globe size={48} className="text-shell-text-tertiary" />
          <div>
            <h3 className="text-lg font-medium text-shell-text mb-1">
              External Browser Mode
            </h3>
            <p className="text-sm text-shell-text-secondary max-w-md">
              Pages open in a new browser tab for full compatibility. This is the
              default on iOS and recommended for sites that don't render well
              embedded.
            </p>
          </div>
          <button
            type="button"
            onClick={openInTab}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
          >
            <ExternalLink size={18} />
            Open {new URL(url).hostname} in Tab
          </button>
          <button
            type="button"
            onClick={toggleMode}
            className="text-xs text-shell-text-tertiary hover:text-shell-text-secondary transition-colors underline"
          >
            Switch to embedded mode
          </button>
        </div>
      ) : loadError ? (
        /* Embedded mode — load error fallback */
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8 text-center">
          <AlertTriangle size={48} className="text-amber-500" />
          <div>
            <h3 className="text-lg font-medium text-shell-text mb-1">
              Could not load this page
            </h3>
            <p className="text-sm text-shell-text-secondary max-w-md">
              This site could not be loaded through the proxy. Open it directly
              in a new tab instead.
            </p>
          </div>
          <button
            type="button"
            onClick={openInTab}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
          >
            <ExternalLink size={18} />
            Open in Tab
          </button>
          <button
            type="button"
            onClick={() => {
              setLoadError(false);
              setLoading(true);
            }}
            className="text-xs text-shell-text-tertiary hover:text-shell-text-secondary transition-colors underline"
          >
            Try again in embedded mode
          </button>
        </div>
      ) : (
        /* Embedded mode — proxy iframe */
        <iframe
          ref={iframeRef}
          src={proxyUrl(url)}
          className="flex-1 w-full border-none bg-white"
          sandbox="allow-downloads allow-forms allow-modals allow-pointer-lock allow-popups allow-presentation allow-same-origin allow-scripts"
          title="Browser"
          onLoad={handleIframeLoad}
          onError={handleIframeError}
        />
      )}
    </div>
  );
}
