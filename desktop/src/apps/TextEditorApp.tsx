import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Editor, rootCtx, defaultValueCtx } from "@milkdown/kit/core";
import { commonmark } from "@milkdown/kit/preset/commonmark";
import { gfm } from "@milkdown/kit/preset/gfm";
import { listener, listenerCtx } from "@milkdown/kit/plugin/listener";
import { nord } from "@milkdown/theme-nord";
import { Milkdown, MilkdownProvider, useEditor } from "@milkdown/react";

/* ── Note storage ────────────────────────────────────────── */

interface Note {
  id: string;
  content: string;
  updatedAt: number;
}

const STORAGE_KEY = "tinyagentos-notes";

function loadNotes(): Note[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* ignore corrupt data */
  }
  return [];
}

function saveNotes(notes: Note[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
}

function noteTitle(content: string): string {
  const first = content.split("\n").find((l) => l.trim().length > 0);
  if (!first) return "Untitled";
  return first.replace(/^#+\s*/, "").slice(0, 40) || "Untitled";
}

function notePreview(content: string): string {
  const lines = content.split("\n").filter((l) => l.trim().length > 0);
  return (lines[1] || "").replace(/^#+\s*/, "").slice(0, 60);
}

/* ── Milkdown editor component ───────────────────────────── */

function MilkdownEditor({
  content,
  onChange,
}: {
  content: string;
  onChange: (md: string) => void;
}) {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEditor(
    (root) =>
      Editor.make()
        .config(nord)
        .config((ctx) => {
          ctx.set(rootCtx, root);
          ctx.set(defaultValueCtx, content);
          ctx.get(listenerCtx).markdownUpdated((_ctx, markdown, prev) => {
            if (markdown !== prev) {
              onChangeRef.current(markdown);
            }
          });
        })
        .use(commonmark)
        .use(gfm)
        .use(listener),
    [],
  );

  return <Milkdown />;
}

/* ── Main app ────────────────────────────────────────────── */

export function TextEditorApp({
  windowId: _windowId,
}: {
  windowId: string;
}) {
  const [notes, setNotes] = useState<Note[]>(loadNotes);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [editorKey, setEditorKey] = useState(0);

  // Persist notes whenever they change
  useEffect(() => {
    saveNotes(notes);
  }, [notes]);

  // Auto-select first note or create one
  useEffect(() => {
    if (notes.length === 0) {
      const first: Note = {
        id: crypto.randomUUID(),
        content: "# Welcome\n\nStart writing...",
        updatedAt: Date.now(),
      };
      setNotes([first]);
      setActiveId(first.id);
      setEditorKey((k) => k + 1);
    } else if (!activeId || !notes.find((n) => n.id === activeId)) {
      setActiveId(notes[0]?.id ?? null);
      setEditorKey((k) => k + 1);
    }
  }, [notes.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeNote = useMemo(
    () => notes.find((n) => n.id === activeId) ?? null,
    [notes, activeId],
  );

  const createNote = useCallback(() => {
    const n: Note = {
      id: crypto.randomUUID(),
      content: "# New Note\n\n",
      updatedAt: Date.now(),
    };
    setNotes((prev) => [n, ...prev]);
    setActiveId(n.id);
    setEditorKey((k) => k + 1);
  }, []);

  const deleteNote = useCallback(
    (id: string) => {
      setNotes((prev) => prev.filter((n) => n.id !== id));
      if (activeId === id) {
        setActiveId(null);
        setEditorKey((k) => k + 1);
      }
    },
    [activeId],
  );

  const selectNote = useCallback(
    (id: string) => {
      if (id !== activeId) {
        setActiveId(id);
        setEditorKey((k) => k + 1);
      }
    },
    [activeId],
  );

  const handleChange = useCallback(
    (md: string) => {
      if (!activeId) return;
      setNotes((prev) =>
        prev.map((n) =>
          n.id === activeId ? { ...n, content: md, updatedAt: Date.now() } : n,
        ),
      );
    },
    [activeId],
  );

  const wordCount = useMemo(() => {
    if (!activeNote) return 0;
    const text = activeNote.content.replace(/[#*_~`>\-[\]()]/g, "").trim();
    return text ? text.split(/\s+/).length : 0;
  }, [activeNote]);

  const sorted = useMemo(
    () => [...notes].sort((a, b) => b.updatedAt - a.updatedAt),
    [notes],
  );

  return (
    <div className="flex h-full bg-shell-bg text-shell-text overflow-hidden">
      {/* ── Sidebar ──────────────────────────────────── */}
      <aside
        className={[
          "flex flex-col border-r border-shell-border bg-shell-bg-deep",
          "transition-all duration-200 ease-in-out",
          sidebarOpen ? "w-[220px] min-w-[220px]" : "w-0 min-w-0 overflow-hidden",
          "max-sm:absolute max-sm:inset-y-0 max-sm:left-0 max-sm:z-10",
          sidebarOpen ? "max-sm:w-[260px]" : "",
        ].join(" ")}
        aria-label="Notes sidebar"
      >
        {/* New note button */}
        <button
          onClick={createNote}
          className="flex items-center gap-2 m-2 px-3 py-2 rounded-lg
                     bg-accent/20 hover:bg-accent/30 text-accent
                     text-sm font-medium transition-colors"
          aria-label="Create new note"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          New Note
        </button>

        {/* Note list */}
        <nav className="flex-1 overflow-y-auto px-1" aria-label="Note list">
          {sorted.map((note) => (
            <div
              key={note.id}
              className={[
                "group flex items-start gap-1 mx-1 mb-0.5 px-2 py-2 rounded-lg cursor-pointer transition-colors",
                note.id === activeId
                  ? "bg-shell-surface-active"
                  : "hover:bg-shell-surface-hover",
              ].join(" ")}
              onClick={() => selectNote(note.id)}
              role="button"
              tabIndex={0}
              aria-current={note.id === activeId ? "true" : undefined}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") selectNote(note.id);
              }}
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate text-shell-text">
                  {noteTitle(note.content)}
                </div>
                <div className="text-xs truncate text-shell-text-tertiary mt-0.5">
                  {notePreview(note.content)}
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteNote(note.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded
                           hover:bg-traffic-close/20 text-shell-text-tertiary
                           hover:text-traffic-close transition-all"
                aria-label={`Delete note: ${noteTitle(note.content)}`}
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                  <path d="M1 1l8 8M9 1l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}
        </nav>
      </aside>

      {/* ── Editor area ──────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-shell-border bg-shell-bg-deep/60">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="p-1.5 rounded hover:bg-shell-surface-hover text-shell-text-secondary
                       hover:text-shell-text transition-colors"
            aria-label={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
          <span className="text-sm font-medium text-shell-text truncate">
            {activeNote ? noteTitle(activeNote.content) : "No note selected"}
          </span>
        </div>

        {/* Milkdown editor */}
        <div className="flex-1 overflow-y-auto milkdown-wrapper">
          {activeNote && (
            <MilkdownProvider key={editorKey}>
              <MilkdownEditor content={activeNote.content} onChange={handleChange} />
            </MilkdownProvider>
          )}
        </div>

        {/* Status bar */}
        <div className="flex items-center justify-between px-4 py-1.5 text-xs
                        text-shell-text-secondary bg-shell-bg-deep/60
                        border-t border-shell-border">
          <span>
            {wordCount} {wordCount === 1 ? "word" : "words"}
          </span>
          <span>{notes.length} {notes.length === 1 ? "note" : "notes"}</span>
        </div>
      </div>

      {/* ── Milkdown dark-theme overrides ─────────────── */}
      <style>{`
        .milkdown-wrapper .milkdown {
          background: transparent !important;
          color: rgba(255, 255, 255, 0.85) !important;
          height: 100%;
        }
        .milkdown-wrapper .milkdown .editor {
          padding: 24px 32px;
          min-height: 100%;
          outline: none;
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          font-size: 15px;
          line-height: 1.75;
          color: rgba(255, 255, 255, 0.85);
        }
        .milkdown-wrapper .milkdown .editor h1 {
          font-size: 1.75em;
          font-weight: 700;
          margin: 1em 0 0.4em;
          color: rgba(255, 255, 255, 0.95);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          padding-bottom: 0.3em;
        }
        .milkdown-wrapper .milkdown .editor h2 {
          font-size: 1.4em;
          font-weight: 600;
          margin: 0.8em 0 0.3em;
          color: rgba(255, 255, 255, 0.92);
        }
        .milkdown-wrapper .milkdown .editor h3 {
          font-size: 1.15em;
          font-weight: 600;
          margin: 0.6em 0 0.2em;
          color: rgba(255, 255, 255, 0.9);
        }
        .milkdown-wrapper .milkdown .editor p {
          margin: 0.5em 0;
        }
        .milkdown-wrapper .milkdown .editor a {
          color: #667eea;
          text-decoration: underline;
          text-underline-offset: 2px;
        }
        .milkdown-wrapper .milkdown .editor code {
          background: rgba(255, 255, 255, 0.06);
          padding: 0.15em 0.4em;
          border-radius: 4px;
          font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
          font-size: 0.9em;
        }
        .milkdown-wrapper .milkdown .editor pre {
          background: rgba(0, 0, 0, 0.3) !important;
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 16px;
          overflow-x: auto;
          margin: 0.75em 0;
        }
        .milkdown-wrapper .milkdown .editor pre code {
          background: none;
          padding: 0;
        }
        .milkdown-wrapper .milkdown .editor blockquote {
          border-left: 3px solid #667eea;
          padding-left: 16px;
          margin: 0.75em 0;
          color: rgba(255, 255, 255, 0.6);
        }
        .milkdown-wrapper .milkdown .editor ul {
          list-style: disc;
          padding-left: 1.5em;
        }
        .milkdown-wrapper .milkdown .editor ol {
          list-style: decimal;
          padding-left: 1.5em;
        }
        .milkdown-wrapper .milkdown .editor li {
          margin: 0.2em 0;
        }
        .milkdown-wrapper .milkdown .editor hr {
          border: none;
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          margin: 1.5em 0;
        }
        .milkdown-wrapper .milkdown .editor table {
          border-collapse: collapse;
          width: 100%;
          margin: 0.75em 0;
        }
        .milkdown-wrapper .milkdown .editor th,
        .milkdown-wrapper .milkdown .editor td {
          border: 1px solid rgba(255, 255, 255, 0.1);
          padding: 8px 12px;
          text-align: left;
        }
        .milkdown-wrapper .milkdown .editor th {
          background: rgba(255, 255, 255, 0.04);
          font-weight: 600;
        }
        .milkdown-wrapper .milkdown .editor input[type="checkbox"] {
          margin-right: 6px;
          accent-color: #667eea;
        }
        .milkdown-wrapper .milkdown .editor .tableWrapper {
          overflow-x: auto;
        }
        /* Hide nord theme background */
        .milkdown-wrapper .ProseMirror {
          background: transparent !important;
        }
      `}</style>
    </div>
  );
}
