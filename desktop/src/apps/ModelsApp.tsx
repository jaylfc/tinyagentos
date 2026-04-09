import { useState, useEffect, useCallback, useRef } from "react";
import { Brain, Search, Download, Trash2, HardDrive, X, Filter } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface DownloadedModel {
  id: string;
  filename: string;
  size: string;
  format: string;
  quantization?: string;
}

interface AvailableModel {
  id: string;
  name: string;
  description: string;
  compatibility: "green" | "yellow" | "red";
  capabilities: string[];
  size: string;
}

type SourceFilter = "all" | "huggingface" | "ollama" | "catalog";

/* ------------------------------------------------------------------ */
/*  Fallback data                                                      */
/* ------------------------------------------------------------------ */

const MOCK_DOWNLOADED: DownloadedModel[] = [
  { id: "qwen2.5-7b-q4", filename: "qwen2.5-7b-instruct-q4_k_m.gguf", size: "4.4 GB", format: "GGUF", quantization: "Q4_K_M" },
  { id: "phi3-mini-q5", filename: "phi-3-mini-4k-q5_k_m.gguf", size: "2.8 GB", format: "GGUF", quantization: "Q5_K_M" },
];

const MOCK_AVAILABLE: AvailableModel[] = [
  { id: "llama3-8b", name: "Llama 3 8B", description: "Meta's latest open model. Strong general-purpose reasoning and instruction following.", compatibility: "green", capabilities: ["chat", "code", "reasoning"], size: "4.7 GB" },
  { id: "mistral-7b", name: "Mistral 7B", description: "Fast and efficient. Good balance of speed and quality for edge deployment.", compatibility: "green", capabilities: ["chat", "code"], size: "4.1 GB" },
  { id: "codellama-13b", name: "Code Llama 13B", description: "Specialised for code generation, completion, and debugging tasks.", compatibility: "yellow", capabilities: ["code", "reasoning"], size: "7.3 GB" },
  { id: "mixtral-8x7b", name: "Mixtral 8x7B", description: "Mixture-of-experts model. Very capable but requires significant memory.", compatibility: "red", capabilities: ["chat", "code", "reasoning", "multilingual"], size: "26 GB" },
  { id: "gemma2-2b", name: "Gemma 2 2B", description: "Google's compact model. Ideal for lightweight agent tasks on constrained hardware.", compatibility: "green", capabilities: ["chat"], size: "1.6 GB" },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const COMPAT_STYLES: Record<string, { dot: string; label: string }> = {
  green: { dot: "bg-emerald-400", label: "Recommended" },
  yellow: { dot: "bg-amber-400", label: "May be slow" },
  red: { dot: "bg-red-400", label: "Too large" },
};

const CAPABILITY_COLORS: Record<string, string> = {
  chat: "bg-sky-500/20 text-sky-400",
  code: "bg-violet-500/20 text-violet-400",
  reasoning: "bg-amber-500/20 text-amber-400",
  multilingual: "bg-emerald-500/20 text-emerald-400",
};

/* ------------------------------------------------------------------ */
/*  DownloadProgress                                                   */
/* ------------------------------------------------------------------ */

function DownloadProgress({ name, onDone }: { name: string; onDone: () => void }) {
  const [pct, setPct] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    timer.current = setInterval(() => {
      setPct((prev) => {
        if (prev >= 100) {
          clearInterval(timer.current);
          setTimeout(onDone, 400);
          return 100;
        }
        return prev + Math.random() * 8 + 2;
      });
    }, 300);
    return () => clearInterval(timer.current);
  }, [onDone]);

  const progress = Math.min(100, Math.round(pct));

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-shell-text-secondary truncate">{name}</span>
        <span className="tabular-nums text-shell-text-tertiary">{progress}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-white/5" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ModelsApp (main)                                                   */
/* ------------------------------------------------------------------ */

export function ModelsApp({ windowId: _windowId }: { windowId: string }) {
  const [downloaded, setDownloaded] = useState<DownloadedModel[]>([]);
  const [available, setAvailable] = useState<AvailableModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [source, setSource] = useState<SourceFilter>("all");
  const [downloading, setDownloading] = useState<Set<string>>(new Set());

  const fetchModels = useCallback(async () => {
    try {
      const res = await fetch("/api/models", { headers: { Accept: "application/json" } });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (data.downloaded) setDownloaded(data.downloaded);
          if (data.available) setAvailable(data.available);
          setLoading(false);
          return;
        }
      }
    } catch { /* fall through */ }
    setDownloaded(MOCK_DOWNLOADED);
    setAvailable(MOCK_AVAILABLE);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const handleDelete = (id: string) => {
    setDownloaded((prev) => prev.filter((m) => m.id !== id));
  };

  const handleDownload = (model: AvailableModel) => {
    setDownloading((prev) => new Set(prev).add(model.id));
  };

  const handleDownloadDone = (model: AvailableModel) => {
    setDownloading((prev) => {
      const next = new Set(prev);
      next.delete(model.id);
      return next;
    });
    setDownloaded((prev) => [
      ...prev,
      {
        id: model.id,
        filename: `${model.id}-q4_k_m.gguf`,
        size: model.size,
        format: "GGUF",
        quantization: "Q4_K_M",
      },
    ]);
  };

  const q = search.toLowerCase();
  const filteredAvailable = available.filter((m) => {
    if (q && !m.name.toLowerCase().includes(q) && !m.description.toLowerCase().includes(q)) return false;
    return true;
  });
  const filteredDownloaded = downloaded.filter((m) => {
    if (q && !m.filename.toLowerCase().includes(q)) return false;
    return true;
  });

  return (
    <div className="flex flex-col h-full bg-shell-bg text-shell-text select-none">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Brain size={18} className="text-accent" />
          <h1 className="text-sm font-semibold">Models</h1>
          <span className="text-xs text-shell-text-tertiary">
            {downloaded.length} downloaded
          </span>
        </div>
      </div>

      {/* Search + Filter */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/5">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-shell-text-tertiary" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search models..."
            className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-shell-bg-deep text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Search models"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-white/10 text-shell-text-tertiary"
              aria-label="Clear search"
            >
              <X size={12} />
            </button>
          )}
        </div>
        <div className="relative">
          <Filter size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-shell-text-tertiary pointer-events-none" />
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as SourceFilter)}
            className="pl-8 pr-3 py-1.5 rounded-lg bg-shell-bg-deep text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent appearance-none cursor-pointer"
            aria-label="Filter by source"
          >
            <option value="all">All Sources</option>
            <option value="huggingface">HuggingFace</option>
            <option value="ollama">Ollama</option>
            <option value="catalog">Catalog</option>
          </select>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-6">
        {loading ? (
          <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
            Loading models...
          </div>
        ) : (
          <>
            {/* Downloaded Models */}
            <section aria-label="Downloaded models">
              <div className="flex items-center gap-2 mb-3">
                <HardDrive size={15} className="text-shell-text-tertiary" />
                <h2 className="text-sm font-semibold">Downloaded Models</h2>
                <span className="text-xs text-shell-text-tertiary">({filteredDownloaded.length})</span>
              </div>

              {filteredDownloaded.length === 0 ? (
                <div className="p-6 rounded-xl bg-shell-surface/40 border border-white/5 text-center">
                  <HardDrive size={28} className="mx-auto text-shell-text-tertiary opacity-40 mb-2" />
                  <p className="text-sm text-shell-text-tertiary">No downloaded models</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {filteredDownloaded.map((model) => (
                    <div
                      key={model.id}
                      className="p-3.5 rounded-xl bg-shell-surface/60 border border-white/5 flex flex-col gap-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium truncate" title={model.filename}>
                          {model.filename}
                        </p>
                        <button
                          onClick={() => handleDelete(model.id)}
                          className="shrink-0 p-1 rounded-md hover:bg-red-500/15 transition-colors text-shell-text-secondary hover:text-red-400"
                          aria-label={`Delete ${model.filename}`}
                          title="Delete model"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-shell-text-tertiary">
                        <span className="px-1.5 py-0.5 rounded bg-white/5 font-medium">{model.format}</span>
                        {model.quantization && (
                          <span className="px-1.5 py-0.5 rounded bg-white/5">{model.quantization}</span>
                        )}
                        <span className="ml-auto tabular-nums">{model.size}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Downloading */}
            {downloading.size > 0 && (
              <section aria-label="Downloads in progress">
                <h2 className="text-sm font-semibold mb-3">Downloading</h2>
                <div className="space-y-2">
                  {[...downloading].map((id) => {
                    const model = available.find((m) => m.id === id);
                    if (!model) return null;
                    return (
                      <div key={id} className="p-3.5 rounded-xl bg-shell-surface/60 border border-white/5">
                        <DownloadProgress name={model.name} onDone={() => handleDownloadDone(model)} />
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* Available Models */}
            <section aria-label="Available models">
              <div className="flex items-center gap-2 mb-3">
                <Download size={15} className="text-shell-text-tertiary" />
                <h2 className="text-sm font-semibold">Available Models</h2>
                <span className="text-xs text-shell-text-tertiary">({filteredAvailable.length})</span>
              </div>

              {filteredAvailable.length === 0 ? (
                <div className="p-6 rounded-xl bg-shell-surface/40 border border-white/5 text-center">
                  <Brain size={28} className="mx-auto text-shell-text-tertiary opacity-40 mb-2" />
                  <p className="text-sm text-shell-text-tertiary">No models match your search</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {filteredAvailable.map((model) => {
                    const compat = COMPAT_STYLES[model.compatibility] ?? { dot: "bg-emerald-400", label: "Recommended" };
                    const isDownloaded = downloaded.some((d) => d.id === model.id);
                    const isDownloading = downloading.has(model.id);

                    return (
                      <div
                        key={model.id}
                        className="p-4 rounded-xl bg-shell-surface/60 border border-white/5 flex flex-col gap-2.5"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <h3 className="text-sm font-medium">{model.name}</h3>
                              <span
                                className={`w-2 h-2 rounded-full shrink-0 ${compat.dot}`}
                                title={compat.label}
                                aria-label={`Compatibility: ${compat.label}`}
                              />
                            </div>
                            <p className="text-xs text-shell-text-secondary mt-1 line-clamp-2">
                              {model.description}
                            </p>
                          </div>
                          <span className="text-xs text-shell-text-tertiary tabular-nums shrink-0">
                            {model.size}
                          </span>
                        </div>

                        <div className="flex items-center justify-between gap-2">
                          <div className="flex flex-wrap gap-1">
                            {model.capabilities.map((cap) => (
                              <span
                                key={cap}
                                className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${CAPABILITY_COLORS[cap] ?? "bg-white/5 text-shell-text-tertiary"}`}
                              >
                                {cap}
                              </span>
                            ))}
                          </div>

                          {isDownloaded ? (
                            <span className="text-xs text-emerald-400 font-medium shrink-0">Downloaded</span>
                          ) : (
                            <button
                              onClick={() => handleDownload(model)}
                              disabled={isDownloading}
                              className="shrink-0 flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-accent text-white hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                              aria-label={`Download ${model.name}`}
                            >
                              <Download size={12} />
                              {isDownloading ? "Downloading..." : "Download"}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
