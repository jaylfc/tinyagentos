import { useState, useEffect, useCallback } from "react";
import { Database, Search, Trash2, User, FolderOpen, ChevronLeft } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Agent {
  name: string;
  color: string;
  collections: string[];
}

interface MemoryChunk {
  id: string;
  title: string;
  collection: string;
  preview: string;
  hash: string;
}

type SearchMode = "keyword" | "semantic" | "hybrid";

/* ------------------------------------------------------------------ */
/*  Fallback data                                                      */
/* ------------------------------------------------------------------ */

const MOCK_AGENTS: Agent[] = [
  { name: "research-agent", color: "#3b82f6", collections: ["notes", "web-scrapes", "summaries"] },
  { name: "code-reviewer", color: "#8b5cf6", collections: ["reviews", "patterns", "standards"] },
  { name: "data-pipeline", color: "#f59e0b", collections: ["schemas", "transforms"] },
];

const MOCK_CHUNKS: Record<string, MemoryChunk[]> = {
  "research-agent": [
    { id: "c1", title: "GPU vs NPU inference comparison", collection: "notes", preview: "Benchmarks show NPU inference on RK3588 achieves 15 tokens/sec for 7B models compared to 8 tokens/sec on Mali GPU...", hash: "a3f8c2" },
    { id: "c2", title: "LangChain agent patterns", collection: "web-scrapes", preview: "ReAct pattern combines reasoning and acting. The agent generates a thought, takes an action, observes the result...", hash: "b7d1e4" },
    { id: "c3", title: "Weekly research summary", collection: "summaries", preview: "Key findings: local models now competitive for agent tasks. GGUF format standardising. Mixture-of-experts showing promise...", hash: "c9a2f6" },
    { id: "c4", title: "Embedding model evaluation", collection: "notes", preview: "Tested BGE-small, MiniLM-L6, and Nomic-embed. BGE-small gives best quality/speed tradeoff for ARM deployment...", hash: "d4e8b1" },
  ],
  "code-reviewer": [
    { id: "c5", title: "TypeScript strict mode patterns", collection: "patterns", preview: "Always enable strict mode. Use discriminated unions over type assertions. Prefer unknown over any...", hash: "e2f5a8" },
    { id: "c6", title: "React performance review", collection: "reviews", preview: "Component re-renders excessively due to inline object creation in props. Recommend useMemo for computed values...", hash: "f1c3d7" },
  ],
  "data-pipeline": [
    { id: "c7", title: "CSV ingestion schema", collection: "schemas", preview: "Expected columns: timestamp, agent_name, event_type, payload_json. Timestamp must be ISO 8601...", hash: "g8h2j4" },
  ],
};

/* ------------------------------------------------------------------ */
/*  MemoryApp (main)                                                   */
/* ------------------------------------------------------------------ */

export function MemoryApp({ windowId: _windowId }: { windowId: string }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [chunks, setChunks] = useState<MemoryChunk[]>([]);
  const [search, setSearch] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("keyword");
  const [loading, setLoading] = useState(true);
  const [chunksLoading, setChunksLoading] = useState(false);

  // Fetch agents
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/agents", { headers: { Accept: "application/json" } });
        if (res.ok) {
          const ct = res.headers.get("content-type") ?? "";
          if (ct.includes("application/json")) {
            const data = await res.json();
            if (Array.isArray(data) && data.length > 0) {
              const mapped = data.map((a: Record<string, unknown>) => ({
                name: String(a.name ?? "unknown"),
                color: String(a.color ?? "#3b82f6"),
                collections: Array.isArray(a.collections) ? a.collections.map(String) : [],
              }));
              setAgents(mapped);
              setLoading(false);
              return;
            }
          }
        }
      } catch { /* fall through */ }
      setAgents(MOCK_AGENTS);
      setLoading(false);
    })();
  }, []);

  // Fetch chunks when agent selected
  const fetchChunks = useCallback(async (agentName: string) => {
    setChunksLoading(true);
    setChunks([]);
    try {
      const res = await fetch(`/api/memory/browse?agent=${encodeURIComponent(agentName)}`, {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data)) {
            setChunks(
              data.map((c: Record<string, unknown>) => ({
                id: String(c.id ?? Math.random().toString(36).slice(2)),
                title: String(c.title ?? "Untitled"),
                collection: String(c.collection ?? "default"),
                preview: String(c.preview ?? c.text ?? ""),
                hash: String(c.hash ?? "------"),
              })),
            );
            setChunksLoading(false);
            return;
          }
        }
      }
    } catch { /* fall through */ }
    // Fallback to mock
    setChunks(MOCK_CHUNKS[agentName] ?? []);
    setChunksLoading(false);
  }, []);

  // Fetch collections for agent
  const fetchCollections = useCallback(async (agentName: string) => {
    try {
      const res = await fetch(`/api/memory/collections/${encodeURIComponent(agentName)}`, {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data)) {
            setAgents((prev) =>
              prev.map((a) =>
                a.name === agentName ? { ...a, collections: data.map(String) } : a,
              ),
            );
          }
        }
      }
    } catch { /* ignore */ }
  }, []);

  const handleSelectAgent = (name: string) => {
    setSelectedAgent(name);
    setSelectedCollection(null);
    setSearch("");
    fetchChunks(name);
    fetchCollections(name);
  };

  const handleDeleteChunk = (id: string) => {
    setChunks((prev) => prev.filter((c) => c.id !== id));
  };

  const currentAgent = agents.find((a) => a.name === selectedAgent);
  const q = search.toLowerCase();

  const filteredChunks = chunks.filter((c) => {
    if (selectedCollection && c.collection !== selectedCollection) return false;
    if (q && !c.title.toLowerCase().includes(q) && !c.preview.toLowerCase().includes(q)) return false;
    return true;
  });

  const MODES: { id: SearchMode; label: string }[] = [
    { id: "keyword", label: "Keyword" },
    { id: "semantic", label: "Semantic" },
    { id: "hybrid", label: "Hybrid" },
  ];

  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;

  const handleSelectAgentMobile = (name: string) => {
    handleSelectAgent(name);
  };

  const sidebarUI = (
    <nav
      className={isMobile ? "w-full flex flex-col overflow-hidden h-full" : "w-52 shrink-0 border-r border-white/5 bg-shell-surface/30 flex flex-col overflow-hidden"}
      aria-label="Agent list"
    >
      <div className="flex items-center gap-2 px-3 py-3 border-b border-white/5">
        <Database size={15} className="text-accent" />
        <h1 className="text-sm font-semibold">Memory</h1>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <p className="text-xs text-shell-text-tertiary px-2 py-4 text-center">Loading...</p>
        ) : agents.length === 0 ? (
          <p className="text-xs text-shell-text-tertiary px-2 py-4 text-center">No agents found</p>
        ) : (
          agents.map((agent) => {
            const active = selectedAgent === agent.name;
            return (
              <button
                key={agent.name}
                onClick={() => handleSelectAgentMobile(agent.name)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  active
                    ? "bg-white/10 text-shell-text"
                    : "text-shell-text-secondary hover:bg-white/5 hover:text-shell-text"
                }`}
                aria-current={active ? "page" : undefined}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: agent.color }}
                  aria-hidden="true"
                />
                <span className="truncate">{agent.name}</span>
              </button>
            );
          })
        )}
      </div>

      {/* Collection pills */}
      {currentAgent && currentAgent.collections.length > 0 && (
        <div className="border-t border-white/5 p-2">
          <p className="text-[10px] uppercase tracking-wider text-shell-text-tertiary px-2 mb-1.5">Collections</p>
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setSelectedCollection(null)}
              className={`px-2 py-0.5 rounded-full text-[11px] transition-colors ${
                !selectedCollection
                  ? "bg-accent/20 text-accent"
                  : "bg-white/5 text-shell-text-tertiary hover:bg-white/10"
              }`}
            >
              All
            </button>
            {currentAgent.collections.map((col) => (
              <button
                key={col}
                onClick={() => setSelectedCollection(selectedCollection === col ? null : col)}
                className={`px-2 py-0.5 rounded-full text-[11px] transition-colors ${
                  selectedCollection === col
                    ? "bg-accent/20 text-accent"
                    : "bg-white/5 text-shell-text-tertiary hover:bg-white/10"
                }`}
              >
                {col}
              </button>
            ))}
          </div>
        </div>
      )}
    </nav>
  );

  const mainPanelUI = (
    <main className="flex-1 flex flex-col overflow-hidden">
      {!selectedAgent ? (
        <div className="flex flex-col items-center justify-center h-full gap-3 text-shell-text-tertiary">
          <User size={40} className="opacity-30" />
          <p className="text-sm">Select an agent to browse memory</p>
        </div>
      ) : (
        <>
          {/* Search bar */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/5">
            {isMobile && (
              <button onClick={() => setSelectedAgent(null)} className="flex items-center gap-1 text-xs text-shell-text-secondary shrink-0">
                <ChevronLeft size={14} /> Back
              </button>
            )}
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-shell-text-tertiary" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search memory..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-shell-bg-deep text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                aria-label="Search memory chunks"
              />
            </div>
            <div className="flex items-center gap-0.5 p-0.5 rounded-lg bg-shell-bg-deep border border-white/5" role="radiogroup" aria-label="Search mode">
              {MODES.map((mode) => (
                <button
                  key={mode.id}
                  onClick={() => setSearchMode(mode.id)}
                  className={`px-2.5 py-1 rounded-md text-xs transition-colors ${
                    searchMode === mode.id
                      ? "bg-accent/20 text-accent font-medium"
                      : "text-shell-text-tertiary hover:text-shell-text"
                  }`}
                  role="radio"
                  aria-checked={searchMode === mode.id}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>

          {/* Results */}
          <div className="flex-1 overflow-auto p-4">
            {chunksLoading ? (
              <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
                Loading memory...
              </div>
            ) : filteredChunks.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-shell-text-tertiary">
                <FolderOpen size={36} className="opacity-30" />
                <p className="text-sm">
                  {chunks.length === 0 ? "No memory stored for this agent" : "No results match your filter"}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {filteredChunks.map((chunk) => (
                  <div
                    key={chunk.id}
                    className="p-3.5 rounded-xl bg-shell-surface/60 border border-white/5 flex flex-col gap-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-medium truncate" title={chunk.title}>
                          {chunk.title}
                        </h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="px-1.5 py-0.5 rounded bg-white/5 text-[10px] font-medium text-shell-text-tertiary">
                            {chunk.collection}
                          </span>
                          <span className="text-[10px] text-shell-text-tertiary font-mono tabular-nums">
                            #{chunk.hash}
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteChunk(chunk.id)}
                        className="shrink-0 p-1 rounded-md hover:bg-red-500/15 transition-colors text-shell-text-secondary hover:text-red-400"
                        aria-label={`Delete memory chunk: ${chunk.title}`}
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <p className="text-xs text-shell-text-secondary line-clamp-3 leading-relaxed">
                      {chunk.preview}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </main>
  );

  return (
    <div className="flex h-full bg-shell-bg text-shell-text select-none">
      {isMobile ? (
        selectedAgent ? mainPanelUI : sidebarUI
      ) : (
        <>
          {sidebarUI}
          {mainPanelUI}
        </>
      )}
    </div>
  );
}
