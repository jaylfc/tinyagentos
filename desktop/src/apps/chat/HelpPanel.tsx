import { useEffect, useMemo, useState } from "react";

function renderMarkdown(md: string): React.ReactNode {
  const lines = md.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let ulItems: React.ReactNode[] = [];
  const flushUl = () => {
    if (ulItems.length > 0) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="list-disc pl-5 my-2 space-y-1 text-sm text-shell-text-secondary">
          {ulItems}
        </ul>,
      );
      ulItems = [];
    }
  };
  while (i < lines.length) {
    const line = (lines[i] ?? "").trimEnd();
    if (!line.trim()) { flushUl(); i++; continue; }
    if (line.startsWith("### ")) { flushUl(); blocks.push(<h3 key={i} className="text-sm font-semibold text-white mt-4 mb-2">{inlineMd(line.slice(4))}</h3>); i++; continue; }
    if (line.startsWith("## ")) { flushUl(); blocks.push(<h2 key={i} className="text-base font-semibold text-white mt-6 mb-2">{inlineMd(line.slice(3))}</h2>); i++; continue; }
    if (line.startsWith("# ")) { flushUl(); blocks.push(<h1 key={i} className="text-lg font-bold text-white mt-4 mb-3">{inlineMd(line.slice(2))}</h1>); i++; continue; }
    if (line.startsWith("- ") || line.startsWith("* ")) { ulItems.push(<li key={i}>{inlineMd(line.slice(2))}</li>); i++; continue; }
    const paraLines: string[] = [line];
    i++;
    while (i < lines.length) {
      const next = (lines[i] ?? "").trimEnd();
      if (!next.trim()) break;
      if (next.startsWith("#") || next.startsWith("- ") || next.startsWith("* ")) break;
      paraLines.push(next);
      i++;
    }
    flushUl();
    blocks.push(
      <p key={`p-${blocks.length}`} className="text-sm text-shell-text-secondary leading-relaxed my-2">
        {inlineMd(paraLines.join(" "))}
      </p>,
    );
  }
  flushUl();
  return <>{blocks}</>;
}

function inlineMd(s: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let idx = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(s)) !== null) {
    if (match.index > last) parts.push(s.slice(last, match.index));
    const tok = match[0];
    if (tok.startsWith("`")) parts.push(<code key={idx++} className="bg-white/5 px-1 rounded text-xs">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) parts.push(<strong key={idx++}>{tok.slice(2, -2)}</strong>);
    else {
      const m = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok);
      if (m) parts.push(<a key={idx++} href={m[2]} target="_blank" rel="noreferrer" className="text-sky-300 hover:text-sky-200 underline">{m[1]}</a>);
      else parts.push(tok);
    }
    last = match.index + tok.length;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}

export function HelpPanel({ onClose }: { onClose: () => void }) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/docs/chat-guide", { signal: ac.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => setMarkdown(data.markdown ?? ""))
      .catch((e) => {
        if ((e as Error).name === "AbortError") return;
        setError(e instanceof Error ? e.message : "failed");
      });
    return () => ac.abort();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rendered = useMemo(
    () => (markdown === null ? null : renderMarkdown(markdown)),
    [markdown],
  );

  return (
    <div
      role="dialog"
      aria-label="Chat guide"
      aria-modal="true"
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center"
      onClick={onClose}
      data-testid="help-panel-backdrop"
    >
      <div
        className="bg-shell-surface border border-white/10 rounded-lg shadow-xl w-[720px] max-w-[95vw] max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
          <h2 className="text-sm font-semibold">Chat guide</h2>
          <button onClick={onClose} aria-label="Close" className="text-lg leading-none opacity-60 hover:opacity-100">×</button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {error && (
            <div role="alert" className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded px-2 py-2">
              Failed to load guide: {error}
            </div>
          )}
          {!error && markdown === null && (
            <div className="text-xs text-shell-text-tertiary">Loading…</div>
          )}
          {!error && rendered}
        </div>
      </div>
    </div>
  );
}
