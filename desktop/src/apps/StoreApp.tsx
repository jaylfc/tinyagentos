import { useState, useEffect, useCallback } from "react";
import { ShoppingBag, Search, Download, Trash2, Check, Package, Loader2 } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface StoreApp {
  id: string;
  name: string;
  type: "agent-framework" | "model" | "service" | "plugin";
  version: string;
  description: string;
  installed: boolean;
  compat: "green" | "yellow" | "red";
}

type TypeFilter = "all" | "agent-framework" | "model" | "service" | "plugin";

/* ------------------------------------------------------------------ */
/*  Mock data                                                          */
/* ------------------------------------------------------------------ */

const MOCK_APPS: StoreApp[] = [
  { id: "smolagents", name: "SmolAgents", type: "agent-framework", version: "1.0.0", description: "HuggingFace code-based agents", installed: false, compat: "green" },
  { id: "pocketflow", name: "PocketFlow", type: "agent-framework", version: "1.0.0", description: "Minimal graph-based agent framework", installed: false, compat: "green" },
  { id: "openclaw", name: "OpenClaw", type: "agent-framework", version: "1.0.0", description: "Full-featured multi-channel agent", installed: true, compat: "green" },
  { id: "crewai", name: "CrewAI", type: "agent-framework", version: "0.41.0", description: "Role-based autonomous AI agents", installed: false, compat: "green" },
  { id: "qwen2.5-7b", name: "Qwen 2.5 7B", type: "model", version: "2.5.0", description: "Versatile language model with strong reasoning", installed: true, compat: "green" },
  { id: "llama3-8b", name: "Llama 3 8B", type: "model", version: "3.0.0", description: "Meta open-weight LLM for general tasks", installed: false, compat: "yellow" },
  { id: "qdrant", name: "Qdrant", type: "service", version: "1.9.0", description: "High-performance vector search engine", installed: true, compat: "green" },
  { id: "redis-memory", name: "Redis Memory", type: "service", version: "7.2.0", description: "Fast key-value store for agent memory", installed: false, compat: "green" },
  { id: "web-search", name: "Web Search", type: "plugin", version: "0.3.0", description: "Search the web from agent pipelines", installed: false, compat: "green" },
  { id: "code-exec", name: "Code Executor", type: "plugin", version: "0.5.0", description: "Sandboxed code execution for agents", installed: false, compat: "red" },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const TYPE_LABELS: Record<string, string> = {
  "agent-framework": "Framework",
  model: "Model",
  service: "Service",
  plugin: "Plugin",
};

const TYPE_COLORS: Record<string, string> = {
  "agent-framework": "bg-blue-500/20 text-blue-400",
  model: "bg-purple-500/20 text-purple-400",
  service: "bg-amber-500/20 text-amber-400",
  plugin: "bg-teal-500/20 text-teal-400",
};

const COMPAT_COLORS: Record<string, string> = {
  green: "bg-emerald-400",
  yellow: "bg-amber-400",
  red: "bg-red-400",
};

const COMPAT_LABELS: Record<string, string> = {
  green: "Compatible",
  yellow: "Partial",
  red: "Unsupported",
};

const FILTER_OPTIONS: { value: TypeFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "agent-framework", label: "Frameworks" },
  { value: "model", label: "Models" },
  { value: "service", label: "Services" },
  { value: "plugin", label: "Plugins" },
];

/* ------------------------------------------------------------------ */
/*  AppCard                                                            */
/* ------------------------------------------------------------------ */

function AppCard({
  app,
  onInstall,
  onUninstall,
}: {
  app: StoreApp;
  onInstall: (id: string) => void;
  onUninstall: (id: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const handleAction = async () => {
    setBusy(true);
    // Simulate a brief delay for install/uninstall
    await new Promise((r) => setTimeout(r, 800));
    if (app.installed) {
      onUninstall(app.id);
    } else {
      onInstall(app.id);
    }
    setBusy(false);
  };

  return (
    <div className="bg-shell-surface/60 border border-white/[0.06] rounded-xl p-5 flex flex-col gap-3 hover:border-white/10 transition-colors">
      {/* Top row: icon + meta */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-white/[0.06] flex items-center justify-center shrink-0">
            <Package className="w-5 h-5 text-white/50" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-white/90 truncate">{app.name}</span>
              {app.installed && (
                <Check className="w-4 h-4 text-emerald-400 shrink-0" aria-label="Installed" />
              )}
            </div>
            <span className="text-xs text-white/40">v{app.version}</span>
          </div>
        </div>

        {/* Compat indicator */}
        <div className="flex items-center gap-1.5" title={COMPAT_LABELS[app.compat]}>
          <span className={`w-2 h-2 rounded-full ${COMPAT_COLORS[app.compat]}`} />
          <span className="text-[11px] text-white/40">{COMPAT_LABELS[app.compat]}</span>
        </div>
      </div>

      {/* Type badge */}
      <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full w-fit ${TYPE_COLORS[app.type]}`}>
        {TYPE_LABELS[app.type]}
      </span>

      {/* Description */}
      <p className="text-sm text-white/50 leading-relaxed flex-1">{app.description}</p>

      {/* Action button */}
      <button
        onClick={handleAction}
        disabled={busy}
        className={`mt-auto flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
          app.installed
            ? "bg-red-500/10 text-red-400 hover:bg-red-500/20"
            : "bg-blue-500/15 text-blue-400 hover:bg-blue-500/25"
        } disabled:opacity-50`}
        aria-label={app.installed ? `Uninstall ${app.name}` : `Install ${app.name}`}
      >
        {busy ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : app.installed ? (
          <>
            <Trash2 className="w-4 h-4" />
            Uninstall
          </>
        ) : (
          <>
            <Download className="w-4 h-4" />
            Install
          </>
        )}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  StoreApp                                                           */
/* ------------------------------------------------------------------ */

export function StoreApp({ _windowId }: { _windowId: string }) {
  const [apps, setApps] = useState<StoreApp[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [loading, setLoading] = useState(true);

  /* Fetch catalog on mount */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/store/catalog");
        const ct = res.headers.get("content-type") || "";
        if (res.ok && ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data) && !cancelled) {
            setApps(data);
            setLoading(false);
            return;
          }
        }
      } catch {
        // fall through to mock
      }
      if (!cancelled) {
        setApps(MOCK_APPS);
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  /* Client-side filtering */
  const filtered = apps.filter((app) => {
    if (typeFilter !== "all" && app.type !== typeFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        app.name.toLowerCase().includes(q) ||
        app.description.toLowerCase().includes(q) ||
        app.type.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const handleInstall = useCallback((id: string) => {
    setApps((prev) => prev.map((a) => (a.id === id ? { ...a, installed: true } : a)));
  }, []);

  const handleUninstall = useCallback((id: string) => {
    setApps((prev) => prev.map((a) => (a.id === id ? { ...a, installed: false } : a)));
  }, []);

  return (
    <div className="flex flex-col h-full bg-shell-base text-white/80 overflow-hidden select-none">
      {/* Header */}
      <header className="shrink-0 px-6 pt-5 pb-4 border-b border-white/[0.06]">
        <div className="flex items-center gap-3 mb-4">
          <ShoppingBag className="w-6 h-6 text-blue-400" />
          <h1 className="text-lg font-semibold text-white/90">App Store</h1>
          <span className="ml-auto text-xs text-white/30">{apps.length} apps</span>
        </div>

        {/* Search */}
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
          <input
            type="text"
            placeholder="Search apps..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg pl-9 pr-4 py-2 text-sm text-white/80 placeholder:text-white/25 focus:outline-none focus:border-white/15 transition-colors"
            aria-label="Search apps"
          />
        </div>

        {/* Filter pills */}
        <div className="flex gap-2 flex-wrap" role="tablist" aria-label="Filter by type">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              role="tab"
              aria-selected={typeFilter === opt.value}
              onClick={() => setTypeFilter(opt.value)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                typeFilter === opt.value
                  ? "bg-blue-500/20 text-blue-400"
                  : "bg-white/[0.04] text-white/40 hover:bg-white/[0.08] hover:text-white/60"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </header>

      {/* App grid */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="w-6 h-6 text-white/30 animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-white/30 text-sm gap-2">
            <Package className="w-8 h-8" />
            <span>No apps match your search</span>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
            {filtered.map((app) => (
              <AppCard
                key={app.id}
                app={app}
                onInstall={handleInstall}
                onUninstall={handleUninstall}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default StoreApp;
