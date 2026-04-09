import { useCallback, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Globe, RotateCw } from "lucide-react";

const DEFAULT_URL = "https://duckduckgo.com";

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

  const canGoBack = historyIndex > 0;
  const canGoForward = historyIndex < history.length - 1;

  const navigate = useCallback(
    (newUrl: string) => {
      const normalized = normalizeUrl(newUrl);
      setUrl(normalized);
      setInputValue(normalized);
      setHistory((prev) => [...prev.slice(0, historyIndex + 1), normalized]);
      setHistoryIndex((i) => i + 1);
    },
    [historyIndex],
  );

  const goBack = useCallback(() => {
    if (!canGoBack) return;
    const newIndex = historyIndex - 1;
    setHistoryIndex(newIndex);
    setUrl(history[newIndex] ?? DEFAULT_URL);
    setInputValue(history[newIndex] ?? DEFAULT_URL);
  }, [canGoBack, history, historyIndex]);

  const goForward = useCallback(() => {
    if (!canGoForward) return;
    const newIndex = historyIndex + 1;
    setHistoryIndex(newIndex);
    setUrl(history[newIndex] ?? DEFAULT_URL);
    setInputValue(history[newIndex] ?? DEFAULT_URL);
  }, [canGoForward, history, historyIndex]);

  const refresh = useCallback(() => {
    if (iframeRef.current) {
      iframeRef.current.src = proxyUrl(url);
    }
  }, [url]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate(inputValue);
  };

  return (
    <div className="flex flex-col h-full">
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
      </form>

      {/* Browser content — proxied to strip X-Frame-Options */}
      <iframe
        ref={iframeRef}
        src={proxyUrl(url)}
        className="flex-1 w-full border-none bg-white"
        sandbox="allow-downloads allow-forms allow-modals allow-pointer-lock allow-popups allow-presentation allow-same-origin allow-scripts"
        title="Browser"
      />
    </div>
  );
}
