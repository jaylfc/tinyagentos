import { useState, useEffect, useCallback } from "react";
import { ShoppingBag, Search, Download, Trash2, Check, Package, Loader2, Bot, Brain, Server, Plug, Wrench, Image, Music, Video, Globe, Home, Cpu, Gamepad2 } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface CatalogApp {
  id: string;
  name: string;
  type: string;
  version: string;
  description: string;
  installed: boolean;
  compat: "green" | "yellow" | "red";
  category?: string;
}

/* ------------------------------------------------------------------ */
/*  Categories                                                         */
/* ------------------------------------------------------------------ */

interface Category {
  id: string;
  label: string;
  icon: React.ReactNode;
  types: string[];       // which app types belong here
  description: string;
}

const CATEGORIES: Category[] = [
  { id: "all", label: "All Apps", icon: <ShoppingBag size={16} />, types: [], description: "Browse everything" },
  { id: "frameworks", label: "Agent Frameworks", icon: <Bot size={16} />, types: ["agent-framework"], description: "Execution engines for your AI agents" },
  { id: "models", label: "Models", icon: <Brain size={16} />, types: ["model"], description: "Language models for inference" },
  { id: "plugins", label: "Plugins & MCP", icon: <Plug size={16} />, types: ["plugin"], description: "Tools and capabilities for agents" },
  { id: "services", label: "Services", icon: <Server size={16} />, types: ["service"], description: "Infrastructure and backends" },
  { id: "streaming", label: "Streaming Apps", icon: <Globe size={16} />, types: ["streaming-app"], description: "Desktop apps streamed via KasmVNC" },
  { id: "image", label: "Image Generation", icon: <Image size={16} />, types: ["image-gen", "image-model"], description: "Stable Diffusion and image models" },
  { id: "audio", label: "Audio & Voice", icon: <Music size={16} />, types: ["voice", "audio"], description: "TTS, STT, and music generation" },
  { id: "video", label: "Video", icon: <Video size={16} />, types: ["video-gen"], description: "Video generation tools" },
  { id: "devtools", label: "Dev Tools", icon: <Wrench size={16} />, types: ["dev-tool"], description: "Development and coding tools" },
  { id: "home", label: "Home & Monitor", icon: <Home size={16} />, types: ["home", "monitoring"], description: "Home automation and monitoring" },
  { id: "infra", label: "Infrastructure", icon: <Cpu size={16} />, types: ["infrastructure"], description: "System services and networking" },
];

/* ------------------------------------------------------------------ */
/*  Mock data with proper categories                                   */
/* ------------------------------------------------------------------ */

const MOCK_APPS: CatalogApp[] = [
  // Agent Frameworks
  { id: "smolagents", name: "SmolAgents", type: "agent-framework", version: "1.0.0", description: "HuggingFace code-based agents — well-documented, 26k stars", installed: false, compat: "green" },
  { id: "pocketflow", name: "PocketFlow", type: "agent-framework", version: "1.0.0", description: "Minimal 100-line framework, zero deps, graph-based", installed: false, compat: "green" },
  { id: "openclaw", name: "OpenClaw", type: "agent-framework", version: "1.0.0", description: "Full-featured multi-channel agent framework", installed: true, compat: "green" },
  { id: "langroid", name: "Langroid", type: "agent-framework", version: "1.0.0", description: "Multi-agent message-passing framework", installed: false, compat: "green" },
  { id: "openai-agents-sdk", name: "OpenAI Agents SDK", type: "agent-framework", version: "1.0.0", description: "Provider-agnostic agent SDK from OpenAI", installed: false, compat: "green" },

  // Models
  { id: "qwen3-4b", name: "Qwen3 4B", type: "model", version: "3.0.0", description: "Good balance of speed and capability for most tasks", installed: true, compat: "green" },
  { id: "qwen3-1.7b", name: "Qwen3 1.7B", type: "model", version: "3.0.0", description: "Fast, fits comfortably in 8GB RAM", installed: false, compat: "green" },
  { id: "qwen3-8b", name: "Qwen3 8B", type: "model", version: "3.0.0", description: "Most capable local model for 16GB devices", installed: false, compat: "yellow" },

  // Plugins & MCP
  { id: "mcp-pandoc", name: "MCP Pandoc", type: "plugin", version: "0.1.0", description: "Document format conversion — markdown, docx, pdf, 30+ formats", installed: false, compat: "green" },
  { id: "mcp-server-office", name: "MCP Office Docs", type: "plugin", version: "0.1.0", description: "Read, write, and edit .docx files programmatically", installed: false, compat: "green" },
  { id: "playwright-mcp", name: "Playwright MCP", type: "plugin", version: "1.0.0", description: "Browser automation for agents via Playwright", installed: false, compat: "green" },
  { id: "github-mcp-server", name: "GitHub MCP", type: "plugin", version: "1.0.0", description: "Issues, PRs, repos, search — official GitHub MCP", installed: false, compat: "green" },
  { id: "mcp-memory", name: "MCP Memory", type: "plugin", version: "1.0.0", description: "Knowledge graph memory for persistent context", installed: false, compat: "green" },
  { id: "web-search", name: "Web Search", type: "plugin", version: "0.3.0", description: "Search the web via SearXNG or Perplexica", installed: false, compat: "green" },
  { id: "image-generation-tool", name: "Image Generation", type: "plugin", version: "0.1.0", description: "Generate images via Stable Diffusion", installed: false, compat: "green" },

  // Services
  { id: "searxng", name: "SearXNG", type: "service", version: "latest", description: "Privacy-respecting metasearch engine", installed: false, compat: "green" },
  { id: "gitea", name: "Gitea", type: "service", version: "latest", description: "Lightweight self-hosted Git service", installed: false, compat: "green" },
  { id: "n8n", name: "n8n", type: "service", version: "latest", description: "Workflow automation platform", installed: false, compat: "green" },

  // Streaming Apps
  { id: "code-server", name: "Code Server", type: "streaming-app", version: "latest", description: "VS Code in the browser", installed: false, compat: "green" },
  { id: "blender", name: "Blender", type: "streaming-app", version: "latest", description: "3D creation suite streamed via KasmVNC", installed: false, compat: "yellow" },
  { id: "libreoffice", name: "LibreOffice", type: "streaming-app", version: "latest", description: "Full office suite streamed via KasmVNC", installed: false, compat: "green" },

  // Image Gen
  { id: "comfyui", name: "ComfyUI", type: "image-gen", version: "latest", description: "Node-based Stable Diffusion workflow editor", installed: false, compat: "yellow" },
  { id: "fooocus", name: "Fooocus", type: "image-gen", version: "latest", description: "Simple Stable Diffusion with minimal setup", installed: false, compat: "yellow" },

  // Audio
  { id: "kokoro-tts", name: "Kokoro TTS", type: "voice", version: "latest", description: "High-quality text-to-speech", installed: false, compat: "green" },
  { id: "whisper-stt", name: "Whisper STT", type: "voice", version: "latest", description: "OpenAI Whisper speech-to-text", installed: false, compat: "green" },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const TYPE_COLORS: Record<string, string> = {
  "agent-framework": "bg-blue-500/20 text-blue-400",
  model: "bg-purple-500/20 text-purple-400",
  service: "bg-amber-500/20 text-amber-400",
  plugin: "bg-teal-500/20 text-teal-400",
  "streaming-app": "bg-indigo-500/20 text-indigo-400",
  "image-gen": "bg-pink-500/20 text-pink-400",
  "image-model": "bg-pink-500/20 text-pink-400",
  voice: "bg-orange-500/20 text-orange-400",
  audio: "bg-orange-500/20 text-orange-400",
  "video-gen": "bg-red-500/20 text-red-400",
  "dev-tool": "bg-cyan-500/20 text-cyan-400",
  home: "bg-green-500/20 text-green-400",
  monitoring: "bg-green-500/20 text-green-400",
  infrastructure: "bg-slate-500/20 text-slate-400",
};

const TYPE_LABELS: Record<string, string> = {
  "agent-framework": "Framework",
  model: "Model",
  service: "Service",
  plugin: "Plugin / MCP",
  "streaming-app": "Streaming",
  "image-gen": "Image Gen",
  "image-model": "Image Model",
  voice: "Voice",
  audio: "Audio",
  "video-gen": "Video",
  "dev-tool": "Dev Tool",
  home: "Home",
  monitoring: "Monitor",
  infrastructure: "Infra",
};

const COMPAT_COLORS: Record<string, string> = { green: "bg-emerald-400", yellow: "bg-amber-400", red: "bg-red-400" };
const COMPAT_LABELS: Record<string, string> = { green: "Compatible", yellow: "Partial", red: "Unsupported" };

const TYPE_ICON_GRADIENTS: Record<string, string> = {
  "agent-framework": "linear-gradient(135deg, rgba(59,130,246,0.3), rgba(59,130,246,0.1))",
  model: "linear-gradient(135deg, rgba(139,92,246,0.3), rgba(139,92,246,0.1))",
  service: "linear-gradient(135deg, rgba(245,158,11,0.3), rgba(245,158,11,0.1))",
  plugin: "linear-gradient(135deg, rgba(20,184,166,0.3), rgba(20,184,166,0.1))",
  "streaming-app": "linear-gradient(135deg, rgba(99,102,241,0.3), rgba(99,102,241,0.1))",
  "image-gen": "linear-gradient(135deg, rgba(236,72,153,0.3), rgba(236,72,153,0.1))",
  voice: "linear-gradient(135deg, rgba(249,115,22,0.3), rgba(249,115,22,0.1))",
  "dev-tool": "linear-gradient(135deg, rgba(6,182,212,0.3), rgba(6,182,212,0.1))",
};

/* ------------------------------------------------------------------ */
/*  AppCard                                                            */
/* ------------------------------------------------------------------ */

function AppCard({ app, onInstall, onUninstall }: { app: CatalogApp; onInstall: (id: string) => void; onUninstall: (id: string) => void }) {
  const [busy, setBusy] = useState(false);

  const handleAction = async () => {
    setBusy(true);
    try {
      if (app.installed) {
        await fetch("/api/store/uninstall", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ app_id: app.id }) });
        onUninstall(app.id);
      } else {
        await fetch("/api/store/install", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ app_id: app.id }) });
        onInstall(app.id);
      }
    } catch { /* ignore */ }
    setBusy(false);
  };

  return (
    <div className="bg-white/[0.04] border border-white/[0.06] rounded-2xl p-5 flex flex-col gap-3 hover:-translate-y-0.5 hover:shadow-2xl hover:border-white/[0.12] transition-all duration-200 backdrop-blur-sm">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: TYPE_ICON_GRADIENTS[app.type] ?? "rgba(255,255,255,0.06)" }}
          >
            <Package className="w-5 h-5 text-white/60" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-white/90 truncate text-sm">{app.name}</span>
              {app.installed && <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
            </div>
            <span className="text-[11px] text-white/30">v{app.version}</span>
          </div>
        </div>
        <div className="flex items-center gap-1" title={COMPAT_LABELS[app.compat]}>
          <span className={`w-1.5 h-1.5 rounded-full ${COMPAT_COLORS[app.compat]}`} />
        </div>
      </div>

      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full w-fit ${TYPE_COLORS[app.type] ?? "bg-white/10 text-white/50"}`}>
        {TYPE_LABELS[app.type] ?? app.type}
      </span>

      <p className="text-xs text-white/45 leading-relaxed flex-1">{app.description}</p>

      <button
        onClick={handleAction}
        disabled={busy}
        className={`mt-auto w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium transition-all duration-200 ${
          app.installed ? "bg-red-500/10 text-red-400 hover:bg-red-500/20" : "bg-accent/15 text-accent hover:bg-accent/25"
        } disabled:opacity-50`}
      >
        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : app.installed ? <><Trash2 className="w-3.5 h-3.5" /> Uninstall</> : <><Download className="w-3.5 h-3.5" /> Install</>}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  StoreApp                                                           */
/* ------------------------------------------------------------------ */

export function StoreApp({ windowId: _windowId }: { windowId: string }) {
  const [apps, setApps] = useState<CatalogApp[]>([]);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/store/catalog");
        const ct = res.headers.get("content-type") ?? "";
        if (res.ok && ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data) && !cancelled) { setApps(data); setLoading(false); return; }
        }
      } catch { /* fall through */ }
      if (!cancelled) { setApps(MOCK_APPS); setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  const activeCat = CATEGORIES.find((c) => c.id === activeCategory);

  const filtered = apps.filter((app) => {
    if (activeCategory !== "all" && activeCat) {
      if (!activeCat.types.includes(app.type)) return false;
    }
    if (search) {
      const q = search.toLowerCase();
      return app.name.toLowerCase().includes(q) || app.description.toLowerCase().includes(q);
    }
    return true;
  });

  const handleInstall = useCallback((id: string) => {
    setApps((prev) => prev.map((a) => (a.id === id ? { ...a, installed: true } : a)));
  }, []);

  const handleUninstall = useCallback((id: string) => {
    setApps((prev) => prev.map((a) => (a.id === id ? { ...a, installed: false } : a)));
  }, []);

  // Count per category
  const counts: Record<string, number> = {};
  for (const cat of CATEGORIES) {
    if (cat.id === "all") { counts[cat.id] = apps.length; continue; }
    counts[cat.id] = apps.filter((a) => cat.types.includes(a.type)).length;
  }

  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;

  return (
    <div className={`flex ${isMobile ? "flex-col" : ""} h-full overflow-hidden`}>
      {/* Sidebar / Mobile pill row */}
      {isMobile ? (
        <div className="flex overflow-x-auto gap-2 px-3 py-2 border-b border-shell-border shrink-0">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className={`whitespace-nowrap px-3 py-1 rounded-full text-xs ${
                activeCategory === cat.id
                  ? "bg-accent/15 text-accent"
                  : "bg-shell-surface text-shell-text-secondary"
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      ) : (
        <div className="w-52 shrink-0 border-r border-shell-border bg-shell-surface/30 flex flex-col overflow-y-auto">
          <div className="px-3 py-3 border-b border-shell-border">
            <div className="flex items-center gap-2">
              <ShoppingBag size={16} className="text-accent" />
              <span className="text-sm font-medium text-shell-text">Store</span>
            </div>
          </div>
          <nav className="flex-1 py-2">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left text-xs transition-colors ${
                  activeCategory === cat.id
                    ? "bg-accent/15 text-accent"
                    : "text-shell-text-secondary hover:bg-white/5 hover:text-shell-text"
                }`}
              >
                <span className="shrink-0">{cat.icon}</span>
                <span className="flex-1 truncate">{cat.label}</span>
                {counts[cat.id] ? (
                  <span className="text-[10px] text-shell-text-tertiary">{counts[cat.id]}</span>
                ) : null}
              </button>
            ))}
          </nav>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="shrink-0 px-5 py-4 border-b border-shell-border">
          <div className="flex items-center justify-between mb-1">
            <div>
              <h2 className="text-base font-medium text-shell-text">{activeCat?.label ?? "All Apps"}</h2>
              <p className="text-xs text-shell-text-tertiary">{activeCat?.description}</p>
            </div>
            <span className="text-xs text-shell-text-tertiary">{filtered.length} apps</span>
          </div>
          <div className="relative mt-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-shell-text-tertiary pointer-events-none" />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-shell-surface border border-shell-border rounded-lg pl-9 pr-4 py-1.5 text-sm text-shell-text placeholder:text-shell-text-tertiary focus:outline-none focus:border-accent/30 transition-colors"
            />
          </div>
        </header>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex items-center justify-center h-40">
              <Loader2 className="w-6 h-6 text-shell-text-tertiary animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-shell-text-tertiary text-sm gap-2">
              <Package className="w-8 h-8" />
              <span>No apps in this category</span>
            </div>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-4">
              {filtered.map((app) => (
                <AppCard key={app.id} app={app} onInstall={handleInstall} onUninstall={handleUninstall} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default StoreApp;
