import { useEffect, useState } from "react";

export function HelpPanel({ onClose }: { onClose: () => void }) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/docs/chat-guide")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => setMarkdown(data.markdown ?? ""))
      .catch((e) => setError(e instanceof Error ? e.message : "failed"));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-label="Chat guide"
      aria-modal="true"
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="bg-shell-surface border border-white/10 rounded-lg shadow-xl w-[640px] max-w-[90vw] max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
          <h2 className="text-sm font-semibold">Chat guide</h2>
          <button onClick={onClose} aria-label="Close" className="text-lg leading-none opacity-60 hover:opacity-100">×</button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {error && (
            <div role="alert" className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded px-2 py-2">
              Failed to load guide: {error}
            </div>
          )}
          {!error && markdown === null && (
            <div className="text-xs text-shell-text-tertiary">Loading…</div>
          )}
          {!error && markdown !== null && (
            <pre className="whitespace-pre-wrap font-sans text-sm text-shell-text-secondary leading-relaxed">
              {markdown}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
