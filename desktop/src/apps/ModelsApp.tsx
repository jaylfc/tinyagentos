import { useState, useEffect, useCallback, useRef } from "react";
import { Brain, Search, Download, Trash2, HardDrive, X } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  Input,
} from "@/components/ui";
import {
  type AggregatedModel,
  controllerDownloadedToAggregated,
  workersToAggregated,
  cloudProvidersToAggregated,
  fetchClusterWorkers,
  fetchCloudProviders,
  HOST_BADGE_CLASS,
} from "@/lib/models";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface DownloadedModel {
  id: string;
  filename: string;
  size: string;
  format: string;
  quantization?: string;
  host: string;
  hostKind: "controller" | "worker" | "cloud";
  backend?: string;
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
  { id: "qwen2.5-7b-q4", filename: "qwen2.5-7b-instruct-q4_k_m.gguf", size: "4.4 GB", format: "GGUF", quantization: "Q4_K_M", host: "controller", hostKind: "controller" },
  { id: "phi3-mini-q5", filename: "phi-3-mini-4k-q5_k_m.gguf", size: "2.8 GB", format: "GGUF", quantization: "Q5_K_M", host: "controller", hostKind: "controller" },
];

function aggregatedToDownloaded(a: AggregatedModel): DownloadedModel {
  return {
    id: a.key,
    filename: a.name,
    size: a.size ?? "",
    format: a.format ?? (a.backend ?? "").toUpperCase() ?? "",
    quantization: a.quantization,
    host: a.host,
    hostKind: a.hostKind,
    backend: a.backend,
  };
}

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

  const [isFallback, setIsFallback] = useState(false);

  const fetchModels = useCallback(async () => {
    // Kick off cluster workers + providers in parallel with /api/models so the
    // union (controller + workers + cloud) is ready in a single state flip.
    const workersPromise = fetchClusterWorkers();
    const providersPromise = fetchCloudProviders();

    try {
      const res = await fetch("/api/models", {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          // Real backend shape:
          //   { models: [...], downloaded_files: [...], hardware_profile_id }
          const rawModels: Array<Record<string, unknown>> = Array.isArray(
            data.models,
          )
            ? data.models
            : [];
          const rawDownloaded: Array<Record<string, unknown>> = Array.isArray(
            data.downloaded_files,
          )
            ? data.downloaded_files
            : [];

          const fmtSize = (mb: number) =>
            mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;

          const controllerList: DownloadedModel[] = rawDownloaded.map((d) =>
            aggregatedToDownloaded(
              controllerDownloadedToAggregated({
                filename: (d.filename as string) ?? "unknown",
                size_mb: (d.size_mb as number) ?? 0,
                format: (d.format as string) ?? "bin",
              }),
            ),
          );

          // Await parallel sources and union them in.
          const [workers, providers] = await Promise.all([
            workersPromise,
            providersPromise,
          ]);
          const workerList = workersToAggregated(workers).map(
            aggregatedToDownloaded,
          );
          const cloudList = cloudProvidersToAggregated(providers).map(
            aggregatedToDownloaded,
          );
          const downloadedList: DownloadedModel[] = [
            ...controllerList,
            ...workerList,
            ...cloudList,
          ];

          const availableList: AvailableModel[] = rawModels.map((m) => {
            const variants = Array.isArray(m.variants)
              ? (m.variants as Array<Record<string, unknown>>)
              : [];
            // Pick smallest variant for display size estimate.
            let sizeLabel = "\u2014";
            if (variants.length > 0) {
              const sizes = variants
                .map((v) => (v.size_mb as number) ?? 0)
                .filter((n) => n > 0);
              if (sizes.length > 0) {
                sizeLabel = fmtSize(Math.min(...sizes));
              }
            }
            const compat =
              ((m.compatibility as string) ?? "green") as
                | "green"
                | "yellow"
                | "red";
            return {
              id: (m.id as string) ?? "unknown",
              name: (m.name as string) ?? (m.id as string) ?? "Unknown",
              description: (m.description as string) ?? "",
              compatibility: compat,
              capabilities: Array.isArray(m.capabilities)
                ? (m.capabilities as string[])
                : [],
              size: sizeLabel,
            };
          });

          setDownloaded(downloadedList);
          setAvailable(availableList);
          setIsFallback(false);
          setLoading(false);
          return;
        }
      }
    } catch {
      /* fall through */
    }
    // /api/models failed — still try to surface cluster workers + cloud so the
    // user can at least see remote-hosted models.
    try {
      const [workers, providers] = await Promise.all([
        workersPromise,
        providersPromise,
      ]);
      const workerList = workersToAggregated(workers).map(
        aggregatedToDownloaded,
      );
      const cloudList = cloudProvidersToAggregated(providers).map(
        aggregatedToDownloaded,
      );
      if (workerList.length > 0 || cloudList.length > 0) {
        setDownloaded([...workerList, ...cloudList]);
        setAvailable(MOCK_AVAILABLE);
        setIsFallback(true);
        setLoading(false);
        return;
      }
    } catch {
      /* ignore */
    }
    setDownloaded(MOCK_DOWNLOADED);
    setAvailable(MOCK_AVAILABLE);
    setIsFallback(true);
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
        host: "controller",
        hostKind: "controller",
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
          {isFallback && (
            <span
              className="ml-2 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/25"
              title="Backend unreachable \u2014 showing sample data"
            >
              Sample data
            </span>
          )}
        </div>
      </div>

      {/* Search + Filter */}
      <div className="flex flex-col gap-2 px-4 py-2.5 border-b border-white/5">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-shell-text-tertiary pointer-events-none z-10" />
          <Input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search models..."
            className="pl-8 pr-8 h-8"
            aria-label="Search models"
          />
          {search && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSearch("")}
              className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6"
              aria-label="Clear search"
            >
              <X size={12} />
            </Button>
          )}
        </div>
        <div
          className="flex items-center gap-1.5 flex-wrap"
          role="group"
          aria-label="Filter by source"
        >
          {(["all", "huggingface", "ollama", "catalog"] as SourceFilter[]).map(
            (src) => {
              const labels: Record<SourceFilter, string> = {
                all: "All Sources",
                huggingface: "HuggingFace",
                ollama: "Ollama",
                catalog: "Catalog",
              };
              const active = source === src;
              return (
                <Button
                  key={src}
                  variant={active ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSource(src)}
                  aria-pressed={active}
                >
                  {labels[src]}
                </Button>
              );
            },
          )}
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
                  {filteredDownloaded.map((model) => {
                    const isLocal = model.hostKind === "controller";
                    return (
                      <Card key={model.id}>
                        <CardContent className="p-3.5 flex flex-col gap-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <p className="text-sm font-medium truncate" title={model.filename}>
                                  {model.filename}
                                </p>
                                {!isLocal && (
                                  <span
                                    className={HOST_BADGE_CLASS}
                                    title={`Hosted on ${model.host}`}
                                  >
                                    {model.host}
                                  </span>
                                )}
                              </div>
                            </div>
                            {isLocal && (
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => handleDelete(model.id)}
                                className="h-7 w-7 hover:text-red-400 hover:bg-red-500/15"
                                aria-label={`Delete ${model.filename}`}
                                title="Delete model"
                              >
                                <Trash2 size={14} />
                              </Button>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-xs text-shell-text-tertiary">
                            {model.format && (
                              <span className="px-1.5 py-0.5 rounded bg-white/5 font-medium">{model.format}</span>
                            )}
                            {model.quantization && (
                              <span className="px-1.5 py-0.5 rounded bg-white/5">{model.quantization}</span>
                            )}
                            {model.backend && !model.format && (
                              <span className="px-1.5 py-0.5 rounded bg-white/5">{model.backend}</span>
                            )}
                            {model.size && (
                              <span className="ml-auto tabular-nums">{model.size}</span>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
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
                      <Card key={id}>
                        <CardContent className="p-3.5">
                          <DownloadProgress name={model.name} onDone={() => handleDownloadDone(model)} />
                        </CardContent>
                      </Card>
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
                      <Card key={model.id}>
                        <CardHeader className="flex flex-row items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <h3 className="text-sm font-medium">{model.name}</h3>
                              <span
                                className={`w-2 h-2 rounded-full shrink-0 ${compat.dot}`}
                                title={compat.label}
                                aria-label={`Compatibility: ${compat.label}`}
                              />
                            </div>
                          </div>
                          <span className="text-xs text-shell-text-tertiary tabular-nums shrink-0">
                            {model.size}
                          </span>
                        </CardHeader>
                        <CardContent>
                          <p className="text-xs text-shell-text-secondary line-clamp-2">
                            {model.description}
                          </p>
                        </CardContent>
                        <CardFooter className="justify-between gap-2">
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
                            <Button
                              variant="default"
                              size="sm"
                              onClick={() => handleDownload(model)}
                              disabled={isDownloading}
                              aria-label={`Download ${model.name}`}
                            >
                              <Download size={12} />
                              {isDownloading ? "Downloading..." : "Download"}
                            </Button>
                          )}
                        </CardFooter>
                      </Card>
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
