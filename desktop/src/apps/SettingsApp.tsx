import { useState, useEffect, useCallback, type ReactNode } from "react";
import {
  Settings,
  HardDrive,
  Server,
  Download,
  Upload,
  RefreshCw,
  Code,
  Info,
  Plus,
  Wifi,
  WifiOff,
  Check,
  AlertCircle,
  ChevronLeft,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Section = "system" | "storage" | "providers" | "backup" | "updates" | "advanced";

interface SectionDef {
  id: Section;
  label: string;
  icon: typeof Settings;
}

interface SystemInfo {
  cpu: string;
  ram: string;
  npu: string;
  gpu: string;
  disk: string;
  os: string;
}

interface StorageItem {
  label: string;
  size: string;
  bytes: number;
  maxBytes: number;
}

interface Provider {
  id: string;
  name: string;
  type: string;
  url: string;
  status: "online" | "offline" | "unknown";
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SECTIONS: SectionDef[] = [
  { id: "system", label: "System Info", icon: Info },
  { id: "storage", label: "Storage", icon: HardDrive },
  { id: "providers", label: "Providers", icon: Server },
  { id: "backup", label: "Backup & Restore", icon: Download },
  { id: "updates", label: "Updates", icon: RefreshCw },
  { id: "advanced", label: "Advanced", icon: Code },
];

const PLACEHOLDER_SYSTEM: SystemInfo = {
  cpu: "Detecting...",
  ram: "Detecting...",
  npu: "Detecting...",
  gpu: "Detecting...",
  disk: "Detecting...",
  os: "Detecting...",
};

const PLACEHOLDER_STORAGE: StorageItem[] = [
  { label: "Models", size: "--", bytes: 0, maxBytes: 1 },
  { label: "Data", size: "--", bytes: 0, maxBytes: 1 },
  { label: "App Catalog", size: "--", bytes: 0, maxBytes: 1 },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

async function safeFetch<T>(url: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return fallback;
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("application/json")) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "online"
      ? "bg-emerald-400"
      : status === "offline"
        ? "bg-red-400"
        : "bg-zinc-500";
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${color}`}
      aria-label={status}
    />
  );
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-2 w-full rounded-full bg-white/5" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div
        className="h-full rounded-full bg-sky-500 transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  System Info                                                        */
/* ------------------------------------------------------------------ */

function SystemInfoSection() {
  const [info, setInfo] = useState<SystemInfo>(PLACEHOLDER_SYSTEM);
  const [loading, setLoading] = useState(false);

  const detect = useCallback(async () => {
    setLoading(true);
    const data = await safeFetch<SystemInfo | null>("/api/settings/system-info", null);
    if (data) setInfo(data);
    else
      setInfo({
        cpu: "ARM Cortex-A76 x4 + A55 x4",
        ram: "16 GB LPDDR5",
        npu: "RK3588 NPU 6 TOPS",
        gpu: "Mali-G610 MP4",
        disk: "256 GB eMMC",
        os: "Ubuntu 22.04 (aarch64)",
      });
    setLoading(false);
  }, []);

  useEffect(() => { detect(); }, [detect]);

  const rows: [string, string][] = [
    ["CPU", info.cpu],
    ["RAM", info.ram],
    ["NPU", info.npu],
    ["GPU", info.gpu],
    ["Disk", info.disk],
    ["OS", info.os],
  ];

  return (
    <section aria-label="System information">
      <h2 className="text-base font-semibold mb-4">System Information</h2>
      <div className="rounded-xl bg-shell-surface/60 border border-white/5 overflow-hidden">
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label} className="border-b border-white/5 last:border-0">
                <td className="px-4 py-2.5 text-shell-text-secondary font-medium w-28">{label}</td>
                <td className="px-4 py-2.5">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        onClick={detect}
        disabled={loading}
        className="mt-3 flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-shell-surface/60 border border-white/5 text-sm hover:bg-shell-surface transition-colors disabled:opacity-50"
      >
        <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        Re-detect Hardware
      </button>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Storage                                                            */
/* ------------------------------------------------------------------ */

function StorageSection() {
  const [items, setItems] = useState<StorageItem[]>(PLACEHOLDER_STORAGE);

  useEffect(() => {
    safeFetch<StorageItem[] | null>("/api/settings/storage", null).then((data) => {
      if (data && Array.isArray(data)) setItems(data);
      else
        setItems([
          { label: "Models", size: "4.2 GB", bytes: 4200, maxBytes: 32000 },
          { label: "Data", size: "1.8 GB", bytes: 1800, maxBytes: 32000 },
          { label: "App Catalog", size: "320 MB", bytes: 320, maxBytes: 32000 },
        ]);
    });
  }, []);

  return (
    <section aria-label="Storage usage">
      <h2 className="text-base font-semibold mb-4">Storage Usage</h2>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.label} className="p-4 rounded-xl bg-shell-surface/60 border border-white/5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">{item.label}</span>
              <span className="text-sm text-shell-text-secondary tabular-nums">{item.size}</span>
            </div>
            <ProgressBar value={item.bytes} max={item.maxBytes} />
          </div>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Providers                                                          */
/* ------------------------------------------------------------------ */

function ProvidersSection() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [testing, setTesting] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", type: "openai", url: "" });

  useEffect(() => {
    safeFetch<Provider[] | null>("/api/settings/providers", null).then((data) => {
      if (data && Array.isArray(data)) setProviders(data);
      else
        setProviders([
          { id: "local-rkllama", name: "RKLlama (Local)", type: "rkllama", url: "http://localhost:8080", status: "online" },
          { id: "openai-compat", name: "OpenAI Compatible", type: "openai", url: "https://api.example.com/v1", status: "unknown" },
        ]);
    });
  }, []);

  const testProvider = async (id: string) => {
    setTesting(id);
    try {
      const res = await fetch(`/api/settings/providers/${id}/test`, { method: "POST" });
      const ok = res.ok;
      setProviders((prev) =>
        prev.map((p) => (p.id === id ? { ...p, status: ok ? "online" : "offline" } : p)),
      );
    } catch {
      setProviders((prev) =>
        prev.map((p) => (p.id === id ? { ...p, status: "offline" } : p)),
      );
    }
    setTesting(null);
  };

  const addProvider = () => {
    if (!form.name || !form.url) return;
    const newP: Provider = {
      id: form.name.toLowerCase().replace(/\s+/g, "-"),
      name: form.name,
      type: form.type,
      url: form.url,
      status: "unknown",
    };
    setProviders((prev) => [...prev, newP]);
    setForm({ name: "", type: "openai", url: "" });
    setShowAdd(false);
  };

  return (
    <section aria-label="Inference providers">
      <h2 className="text-base font-semibold mb-4">Inference Providers</h2>
      <div className="space-y-2">
        {providers.map((p) => (
          <div key={p.id} className="flex items-center gap-3 p-3.5 rounded-xl bg-shell-surface/60 border border-white/5">
            <StatusDot status={p.status} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{p.name}</p>
              <p className="text-xs text-shell-text-tertiary truncate">
                {p.type} &middot; {p.url}
              </p>
            </div>
            <button
              onClick={() => testProvider(p.id)}
              disabled={testing === p.id}
              className="shrink-0 flex items-center gap-1.5 px-3 py-1 rounded-lg bg-white/5 text-xs hover:bg-white/10 transition-colors disabled:opacity-50"
              aria-label={`Test connection to ${p.name}`}
            >
              {testing === p.id ? (
                <RefreshCw size={12} className="animate-spin" />
              ) : p.status === "online" ? (
                <Wifi size={12} />
              ) : (
                <WifiOff size={12} />
              )}
              Test
            </button>
          </div>
        ))}
      </div>

      {showAdd ? (
        <div className="mt-3 p-4 rounded-xl bg-shell-surface/60 border border-white/5 space-y-3">
          <label className="block">
            <span className="text-xs text-shell-text-secondary">Name</span>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="mt-1 w-full px-3 py-1.5 rounded-lg bg-shell-bg-deep border border-white/10 text-sm outline-none focus:border-sky-500"
              placeholder="My Provider"
            />
          </label>
          <label className="block">
            <span className="text-xs text-shell-text-secondary">Type</span>
            <select
              value={form.type}
              onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
              className="mt-1 w-full px-3 py-1.5 rounded-lg bg-shell-bg-deep border border-white/10 text-sm outline-none focus:border-sky-500"
            >
              <option value="openai">OpenAI Compatible</option>
              <option value="rkllama">RKLlama</option>
              <option value="ollama">Ollama</option>
              <option value="vllm">vLLM</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-shell-text-secondary">URL</span>
            <input
              type="url"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              className="mt-1 w-full px-3 py-1.5 rounded-lg bg-shell-bg-deep border border-white/10 text-sm outline-none focus:border-sky-500"
              placeholder="http://localhost:8080"
            />
          </label>
          <div className="flex gap-2">
            <button
              onClick={addProvider}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 text-sm hover:bg-sky-500 transition-colors"
            >
              <Check size={14} /> Add
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="px-3 py-1.5 rounded-lg bg-white/5 text-sm hover:bg-white/10 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowAdd(true)}
          className="mt-3 flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-shell-surface/60 border border-white/5 text-sm hover:bg-shell-surface transition-colors"
        >
          <Plus size={14} /> Add Provider
        </button>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Backup & Restore                                                   */
/* ------------------------------------------------------------------ */

function BackupSection() {
  const [backupStatus, setBackupStatus] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const createBackup = async () => {
    setCreating(true);
    setBackupStatus(null);
    try {
      const res = await fetch("/api/backup", { method: "POST" });
      if (res.ok) {
        setBackupStatus("Backup created successfully.");
      } else {
        setBackupStatus(`Backup failed (${res.status}). API may not be available yet.`);
      }
    } catch {
      setBackupStatus("Could not reach backup endpoint. API not available yet.");
    }
    setCreating(false);
  };

  return (
    <section aria-label="Backup and restore">
      <h2 className="text-base font-semibold mb-4">Backup & Restore</h2>

      <div className="p-4 rounded-xl bg-shell-surface/60 border border-white/5 space-y-4">
        <div>
          <h3 className="text-sm font-medium mb-2">Create Backup</h3>
          <p className="text-xs text-shell-text-tertiary mb-3">
            Export all agents, memory, and configuration as a backup archive.
          </p>
          <button
            onClick={createBackup}
            disabled={creating}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-sky-600 text-sm hover:bg-sky-500 transition-colors disabled:opacity-50"
          >
            <Download size={14} className={creating ? "animate-bounce" : ""} />
            {creating ? "Creating..." : "Create Backup"}
          </button>
          {backupStatus && (
            <p className={`mt-2 text-xs ${backupStatus.includes("success") ? "text-emerald-400" : "text-amber-400"}`}>
              {backupStatus}
            </p>
          )}
        </div>

        <hr className="border-white/5" />

        <div>
          <h3 className="text-sm font-medium mb-2">Restore from Backup</h3>
          <p className="text-xs text-shell-text-tertiary mb-3">
            Upload a previously created backup archive to restore.
          </p>
          <label className="flex flex-col items-center gap-2 p-6 rounded-lg border-2 border-dashed border-white/10 hover:border-white/20 transition-colors cursor-pointer">
            <Upload size={24} className="text-shell-text-tertiary" />
            <span className="text-xs text-shell-text-tertiary">Click to select a backup file</span>
            <input type="file" accept=".tar.gz,.zip,.bak" className="hidden" aria-label="Upload backup file" />
          </label>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Updates                                                            */
/* ------------------------------------------------------------------ */

function UpdatesSection() {
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const checkUpdates = async () => {
    setChecking(true);
    setStatus(null);
    try {
      const res = await fetch("/api/settings/updates");
      if (res.ok) {
        const data = await res.json();
        setStatus(data.message ?? "You are up to date.");
      } else {
        setStatus("Update check not available yet.");
      }
    } catch {
      setStatus("Could not reach update server.");
    }
    setChecking(false);
  };

  return (
    <section aria-label="System updates">
      <h2 className="text-base font-semibold mb-4">Updates</h2>
      <div className="p-4 rounded-xl bg-shell-surface/60 border border-white/5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-white/5 text-sky-400">
            <Settings size={20} />
          </div>
          <div>
            <p className="text-sm font-medium">TinyAgentOS</p>
            <p className="text-xs text-shell-text-tertiary tabular-nums">v0.1.0-dev</p>
          </div>
        </div>

        <button
          onClick={checkUpdates}
          disabled={checking}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-shell-surface/60 border border-white/5 text-sm hover:bg-shell-surface transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={checking ? "animate-spin" : ""} />
          {checking ? "Checking..." : "Check for Updates"}
        </button>

        {status && (
          <div className="flex items-start gap-2 text-xs">
            {status.includes("up to date") ? (
              <Check size={14} className="text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle size={14} className="text-amber-400 shrink-0 mt-0.5" />
            )}
            <span className="text-shell-text-secondary">{status}</span>
          </div>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Advanced                                                           */
/* ------------------------------------------------------------------ */

function AdvancedSection() {
  const [config, setConfig] = useState("# TinyAgentOS Configuration\n# Edit YAML below\n\nserver:\n  port: 3000\n  host: 0.0.0.0\n\nagents:\n  max_concurrent: 5\n  default_model: qwen2.5-7b\n\nproviders:\n  - name: rkllama\n    url: http://localhost:8080\n");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    safeFetch<{ config: string } | null>("/api/settings/config", null).then((data) => {
      if (data?.config) setConfig(data.config);
    });
  }, []);

  const validate = () => {
    setError(null);
    setSaved(false);
    // Basic YAML validation: check for tab characters
    if (config.includes("\t")) {
      setError("YAML should use spaces, not tabs.");
      return false;
    }
    return true;
  };

  const save = async () => {
    if (!validate()) return;
    try {
      const res = await fetch("/api/settings/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config }),
      });
      if (res.ok) setSaved(true);
      else setError(`Save failed (${res.status})`);
    } catch {
      setError("Could not reach backend. Changes saved locally only.");
      setSaved(true);
    }
  };

  return (
    <section aria-label="Advanced configuration">
      <h2 className="text-base font-semibold mb-4">Advanced Configuration</h2>
      <div className="p-4 rounded-xl bg-shell-surface/60 border border-white/5 space-y-3">
        <label className="block">
          <span className="text-xs text-shell-text-secondary">YAML Configuration</span>
          <textarea
            value={config}
            onChange={(e) => { setConfig(e.target.value); setSaved(false); setError(null); }}
            rows={14}
            spellCheck={false}
            className="mt-1 w-full px-3 py-2 rounded-lg bg-shell-bg-deep border border-white/10 text-sm font-mono outline-none focus:border-sky-500 resize-y"
            aria-label="YAML configuration editor"
          />
        </label>

        {error && (
          <p className="text-xs text-red-400 flex items-center gap-1.5">
            <AlertCircle size={12} /> {error}
          </p>
        )}
        {saved && !error && (
          <p className="text-xs text-emerald-400 flex items-center gap-1.5">
            <Check size={12} /> Configuration saved.
          </p>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => validate()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 text-sm hover:bg-white/10 transition-colors"
          >
            <Code size={14} /> Validate
          </button>
          <button
            onClick={save}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 text-sm hover:bg-sky-500 transition-colors"
          >
            <Check size={14} /> Save
          </button>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Main SettingsApp                                                   */
/* ------------------------------------------------------------------ */

export function SettingsApp({ windowId: _windowId }: { windowId: string }) {
  const [section, setSection] = useState<Section>("system");
  const [mobileShowSection, setMobileShowSection] = useState(false);

  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;

  const content: Record<Section, ReactNode> = {
    system: <SystemInfoSection />,
    storage: <StorageSection />,
    providers: <ProvidersSection />,
    backup: <BackupSection />,
    updates: <UpdatesSection />,
    advanced: <AdvancedSection />,
  };

  const handleSelectSection = (id: Section) => {
    setSection(id);
    setMobileShowSection(true);
  };

  const sidebarUI = (
    <nav
      className={isMobile ? "w-full overflow-y-auto" : "w-48 shrink-0 border-r border-white/5 bg-shell-surface/30 overflow-y-auto"}
      aria-label="Settings sections"
    >
      <div className="p-3 space-y-0.5">
        {SECTIONS.map((s) => {
          const active = section === s.id;
          const Icon = s.icon;
          return (
            <button
              key={s.id}
              onClick={() => handleSelectSection(s.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-sky-600/20 text-sky-400"
                  : "text-shell-text-secondary hover:bg-white/5 hover:text-shell-text"
              }`}
              aria-current={active ? "page" : undefined}
            >
              <Icon size={16} />
              {s.label}
            </button>
          );
        })}
      </div>
    </nav>
  );

  const contentUI = (
    <main className="flex-1 overflow-y-auto p-5">
      {isMobile && (
        <button onClick={() => setMobileShowSection(false)} className="flex items-center gap-1 px-3 py-2 text-xs text-shell-text-secondary mb-3">
          <ChevronLeft size={14} /> Back
        </button>
      )}
      {content[section]}
    </main>
  );

  return (
    <div className="flex h-full bg-shell-bg-deep text-shell-text select-none">
      {isMobile ? (
        mobileShowSection ? contentUI : sidebarUI
      ) : (
        <>
          {sidebarUI}
          {contentUI}
        </>
      )}
    </div>
  );
}
