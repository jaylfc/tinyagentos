import { useCallback, useEffect, useRef, useState } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import { languages } from "@codemirror/language-data";
import { oneDark } from "@codemirror/theme-one-dark";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { syntaxHighlighting, defaultHighlightStyle } from "@codemirror/language";
import { FilePlus, Trash2, ChevronLeft, Menu, FileText } from "lucide-react";

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
  } catch { /* ignore */ }
  return [];
}

function saveNotesToStorage(notes: Note[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
}

function noteTitle(content: string): string {
  const first = content.split("\n").find((l) => l.trim().length > 0);
  if (!first) return "Untitled";
  return first.replace(/^#+\s*/, "").slice(0, 40) || "Untitled";
}

function notePreview(content: string): string {
  const lines = content.split("\n").filter((l) => l.trim().length > 0);
  return (lines[1] || "").slice(0, 60);
}

function saveToUserMemory(note: Note) {
  if (!note.content || !note.content.trim()) return;
  const title = noteTitle(note.content);
  fetch("/api/user-memory/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: note.content,
      title,
      collection: "notes",
      metadata: { noteId: note.id, updatedAt: note.updatedAt },
    }),
  }).catch(() => {});
}

/* ── Obsidian-style theme ────────────────────────────────── */

const obsidianTheme = EditorView.theme({
  "&": {
    backgroundColor: "#151625",
    color: "rgba(255,255,255,0.85)",
    height: "100%",
    fontSize: "15px",
  },
  ".cm-content": {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    lineHeight: "1.75",
    padding: "24px 32px",
    caretColor: "#8b92a3",
  },
  ".cm-cursor": {
    borderLeftColor: "#8b92a3",
    borderLeftWidth: "2px",
  },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "rgba(139, 146, 163, 0.25) !important",
  },
  ".cm-gutters": {
    backgroundColor: "#151625",
    color: "rgba(255,255,255,0.15)",
    border: "none",
    paddingLeft: "8px",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "transparent",
    color: "rgba(255,255,255,0.3)",
  },
  ".cm-activeLine": {
    backgroundColor: "rgba(255,255,255,0.02)",
  },
  ".cm-line": {
    padding: "0",
  },
  // Markdown-specific styling
  "&.cm-focused .cm-matchingBracket": {
    backgroundColor: "rgba(139, 146, 163, 0.3)",
  },
  ".cm-scroller": {
    overflow: "auto",
  },
});

/* ── CodeMirror Editor Component ─────────────────────────── */

function MarkdownEditor({
  content,
  onChange,
}: {
  content: string;
  onChange: (value: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!containerRef.current) return;

    // Clean up previous instance
    if (viewRef.current) {
      viewRef.current.destroy();
      viewRef.current = null;
    }

    const state = EditorState.create({
      doc: content,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        drawSelection(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        markdown({ codeLanguages: languages }),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        obsidianTheme,
        oneDark,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChangeRef.current(update.state.doc.toString());
          }
        }),
        EditorView.lineWrapping,
      ],
    });

    const view = new EditorView({
      state,
      parent: containerRef.current,
    });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [content]); // re-create when content identity changes (note switch)

  return <div ref={containerRef} className="h-full w-full" />;
}

/* ── Main App ────────────────────────────────────────────── */

export function TextEditorApp({ windowId: _windowId }: { windowId: string }) {
  const [notes, setNotes] = useState<Note[]>(loadNotes);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;
  const activeNote = notes.find((n) => n.id === activeId);

  // Persist notes
  useEffect(() => {
    saveNotesToStorage(notes);
  }, [notes]);

  // Debounced user-memory capture when active note changes
  useEffect(() => {
    if (!activeNote) return;
    const timer = setTimeout(() => saveToUserMemory(activeNote), 2000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeNote?.content, activeNote?.id]);

  const createNote = useCallback(() => {
    const note: Note = {
      id: crypto.randomUUID(),
      content: "# New Note\n\nStart writing...",
      updatedAt: Date.now(),
    };
    setNotes((prev) => [note, ...prev]);
    setActiveId(note.id);
  }, []);

  const deleteNote = useCallback((id: string) => {
    setNotes((prev) => prev.filter((n) => n.id !== id));
    if (activeId === id) setActiveId(null);
  }, [activeId]);

  const handleChange = useCallback(
    (value: string) => {
      if (!activeId) return;
      setNotes((prev) =>
        prev.map((n) =>
          n.id === activeId ? { ...n, content: value, updatedAt: Date.now() } : n,
        ),
      );
    },
    [activeId],
  );

  const sortedNotes = [...notes].sort((a, b) => b.updatedAt - a.updatedAt);

  /* ── Sidebar ──────────────────────────────────────────── */
  const sidebar = (
    <div
      className="flex flex-col border-r border-shell-border bg-shell-surface/30 overflow-hidden"
      style={{ width: isMobile ? "100%" : 220 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-shell-border">
        <div className="flex items-center gap-2">
          <FileText size={14} className="text-shell-text-secondary" />
          <span className="text-xs font-medium text-shell-text">Notes</span>
          <span className="text-[10px] text-shell-text-tertiary">{notes.length}</span>
        </div>
        <button
          onClick={createNote}
          className="p-1 rounded hover:bg-shell-surface-hover transition-colors"
          aria-label="New note"
        >
          <FilePlus size={14} className="text-shell-text-secondary" />
        </button>
      </div>

      {/* Note list */}
      <div className="flex-1 overflow-y-auto">
        {sortedNotes.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <p className="text-xs text-shell-text-tertiary mb-3">No notes yet</p>
            <button
              onClick={createNote}
              className="px-3 py-1.5 rounded-lg bg-accent/15 text-accent text-xs hover:bg-accent/25 transition-colors"
            >
              Create your first note
            </button>
          </div>
        ) : (
          sortedNotes.map((note) => (
            <button
              key={note.id}
              onClick={() => setActiveId(note.id)}
              className={`w-full text-left px-3 py-2.5 border-b border-shell-border/50 transition-colors group ${
                activeId === note.id
                  ? "bg-accent/10"
                  : "hover:bg-shell-surface-hover"
              }`}
            >
              <div className="flex items-start justify-between gap-1">
                <div className="min-w-0 flex-1">
                  <div className={`text-xs font-medium truncate ${activeId === note.id ? "text-accent" : "text-shell-text"}`}>
                    {noteTitle(note.content)}
                  </div>
                  <div className="text-[10px] text-shell-text-tertiary truncate mt-0.5">
                    {notePreview(note.content)}
                  </div>
                  <div className="text-[9px] text-shell-text-tertiary mt-1">
                    {new Date(note.updatedAt).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteNote(note.id);
                  }}
                  className="p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-red-500/20 transition-all shrink-0"
                  aria-label={`Delete ${noteTitle(note.content)}`}
                >
                  <Trash2 size={11} className="text-red-400" />
                </button>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );

  /* ── Mobile: stacked layout ───────────────────────────── */
  if (isMobile) {
    if (activeNote) {
      return (
        <div className="flex flex-col h-full">
          <button
            onClick={() => setActiveId(null)}
            className="flex items-center gap-1 px-3 py-2 text-xs text-accent border-b border-shell-border bg-shell-surface/30"
          >
            <ChevronLeft size={14} /> Notes
          </button>
          <div className="flex-1 overflow-hidden">
            <MarkdownEditor
              key={activeNote.id}
              content={activeNote.content}
              onChange={handleChange}
            />
          </div>
        </div>
      );
    }
    return <div className="h-full">{sidebar}</div>;
  }

  /* ── Desktop: side-by-side ────────────────────────────── */
  return (
    <div className="flex h-full overflow-hidden">
      {sidebarOpen && sidebar}

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-2 py-1 border-b border-shell-border bg-shell-surface/30">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="p-1 rounded hover:bg-shell-surface-hover transition-colors"
            aria-label="Toggle sidebar"
          >
            <Menu size={14} className="text-shell-text-secondary" />
          </button>
          {activeNote && (
            <span className="text-xs text-shell-text-secondary truncate">
              {noteTitle(activeNote.content)}
            </span>
          )}
          <div className="flex-1" />
          {activeNote && (
            <span className="text-[10px] text-shell-text-tertiary">
              {activeNote.content.split(/\s+/).filter(Boolean).length} words
            </span>
          )}
        </div>

        {/* Editor */}
        <div className="flex-1 overflow-hidden" style={{ backgroundColor: "#151625" }}>
          {activeNote ? (
            <MarkdownEditor
              key={activeNote.id}
              content={activeNote.content}
              onChange={handleChange}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <FileText size={48} className="text-shell-text-tertiary" />
              <p className="text-sm text-shell-text-tertiary">Select a note or create a new one</p>
              <button
                onClick={createNote}
                className="px-4 py-2 rounded-lg bg-accent/15 text-accent text-sm hover:bg-accent/25 transition-colors"
              >
                New Note
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
