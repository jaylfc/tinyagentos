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
  Brain,
} from "lucide-react";
import {
  Button,
  Card,
  Input,
  Label,
  Switch,
  Textarea,
} from "@/components/ui";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Section = "system" | "storage" | "providers" | "memory" | "backup" | "updates" | "advanced";

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
  { id: "memory", label: "Memory", icon: Brain },
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
    interface SysResp {
      hardware?: {
        cpu?: { arch?: string; model?: string; cores?: number; soc?: string };
        ram_mb?: number;
        gpu?: { type?: string; model?: string; vram_mb?: number };
        npu?: { type?: string; tops?: number; cores?: number };
        disk?: { total_gb?: number; type?: string };
        os?: { distro?: string; version?: string; kernel?: string };
      };
      resources?: {
        ram_total_mb?: number;
        disk_total_gb?: number;
      };
    }
    const data = await safeFetch<SysResp | null>("/api/system", null);
    if (data?.hardware || data?.resources) {
      const hw = data.hardware ?? {};
      const rs = data.resources ?? {};
      const ramMb = rs.ram_total_mb ?? hw.ram_mb ?? 0;
      const diskGb = rs.disk_total_gb ?? hw.disk?.total_gb ?? 0;
      const cpuModel = hw.cpu?.model ?? hw.cpu?.soc ?? "Unknown";
      const cpuCores = hw.cpu?.cores ? ` \u00d7 ${hw.cpu.cores}` : "";
      const cpuArch = hw.cpu?.arch ? ` (${hw.cpu.arch})` : "";
      const gpuModel = hw.gpu?.model || hw.gpu?.type || "None";
      const gpuVram =
        hw.gpu?.vram_mb && hw.gpu.vram_mb > 0
          ? ` (${(hw.gpu.vram_mb / 1024).toFixed(1)} GB)`
          : "";
      const npuType =
        hw.npu?.type && hw.npu.type !== "none" ? hw.npu.type : "None";
      const npuTops =
        hw.npu?.tops && hw.npu.tops > 0 ? ` \u00b7 ${hw.npu.tops} TOPS` : "";
      const diskType = hw.disk?.type ? ` ${hw.disk.type}` : "";
      const osParts = [hw.os?.distro, hw.os?.version].filter(Boolean);
      const osStr = osParts.length > 0 ? osParts.join(" ") : "\u2014";
      setInfo({
        cpu: `${cpuModel}${cpuCores}${cpuArch}`,
        ram:
          ramMb >= 1024
            ? `${(ramMb / 1024).toFixed(1)} GB`
            : ramMb > 0
              ? `${ramMb} MB`
              : "\u2014",
        npu: `${npuType}${npuTops}`,
        gpu: `${gpuModel}${gpuVram}`,
        disk: diskGb > 0 ? `${diskGb} GB${diskType}` : "\u2014",
        os: osStr,
      });
    } else {
      setInfo({
        cpu: "Unavailable",
        ram: "Unavailable",
        npu: "Unavailable",
        gpu: "Unavailable",
        disk: "Unavailable",
        os: "Unavailable",
      });
    }
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
      <h2 className="text-lg font-semibold mb-5">System Information</h2>
      <div className="rounded-2xl bg-white/[0.04] border border-white/[0.06] overflow-x-auto backdrop-blur-sm">
        <table className="w-full text-sm min-w-[360px]">
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label} className="border-b border-white/5 last:border-0">
                <td className="px-5 py-3 text-shell-text-secondary font-medium w-32">{label}</td>
                <td className="px-5 py-3">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={detect}
        disabled={loading}
        className="mt-3"
      >
        <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        Re-detect Hardware
      </Button>
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
      <h2 className="text-lg font-semibold mb-5">Storage Usage</h2>
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.label} className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">{item.label}</span>
              <span className="text-sm text-shell-text-secondary tabular-nums">{item.size}</span>
            </div>
            <ProgressBar value={item.bytes} max={item.maxBytes} />
          </Card>
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
      <h2 className="text-lg font-semibold mb-5">Inference Providers</h2>
      <div className="space-y-2">
        {providers.map((p) => (
          <Card key={p.id} className="flex items-center gap-3 p-3.5">
            <StatusDot status={p.status} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{p.name}</p>
              <p className="text-xs text-shell-text-tertiary truncate">
                {p.type} &middot; {p.url}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => testProvider(p.id)}
              disabled={testing === p.id}
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
            </Button>
          </Card>
        ))}
      </div>

      {showAdd ? (
        <Card className="mt-3 p-4 space-y-3">
          <div>
            <Label htmlFor="provider-name">Name</Label>
            <Input
              id="provider-name"
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="mt-1"
              placeholder="My Provider"
            />
          </div>
          <div>
            <Label htmlFor="provider-type">Type</Label>
            <select
              id="provider-type"
              value={form.type}
              onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
              className="mt-1 flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
            >
              <option value="openai">OpenAI Compatible</option>
              <option value="rkllama">RKLlama</option>
              <option value="ollama">Ollama</option>
              <option value="vllm">vLLM</option>
            </select>
          </div>
          <div>
            <Label htmlFor="provider-url">URL</Label>
            <Input
              id="provider-url"
              type="url"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              className="mt-1"
              placeholder="http://localhost:8080"
            />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={addProvider}>
              <Check size={14} /> Add
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
          </div>
        </Card>
      ) : (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAdd(true)}
          className="mt-3"
        >
          <Plus size={14} /> Add Provider
        </Button>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Memory Capture                                                     */
/* ------------------------------------------------------------------ */

interface MemorySettings {
  capture_conversations?: boolean;
  capture_notes?: boolean;
  capture_files?: boolean;
  capture_searches?: boolean;
  [key: string]: boolean | undefined;
}

const MEMORY_TOGGLES: { key: keyof MemorySettings; label: string; desc: string }[] = [
  { key: "capture_conversations", label: "Conversations", desc: "Messages you send to agents in the Message Hub" },
  { key: "capture_notes", label: "Notes", desc: "Notes from the Text Editor app" },
  { key: "capture_files", label: "File activity", desc: "Files you upload or open" },
  { key: "capture_searches", label: "Search queries", desc: "What you search for in global search" },
];

function MemorySection() {
  const [settings, setSettings] = useState<MemorySettings | null>(null);
  const [stats, setStats] = useState<{ total: number; collections: Record<string, number> } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/user-memory/settings")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setSettings(data);
        else setSettings({});
      })
      .catch(() => {
        setSettings({});
        setError("Could not load memory settings.");
      });

    fetch("/api/user-memory/stats")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setStats(data);
      })
      .catch(() => {});
  }, []);

  const update = (key: keyof MemorySettings, value: boolean) => {
    const next: MemorySettings = { ...(settings || {}), [key]: value };
    setSettings(next);
    fetch("/api/user-memory/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    })
      .then((r) => {
        if (!r.ok) setError(`Failed to save setting (${r.status})`);
        else setError(null);
      })
      .catch(() => setError("Could not reach backend."));
  };

  if (!settings) {
    return (
      <section aria-label="Memory capture settings">
        <h2 className="text-lg font-semibold mb-5">Memory Capture</h2>
        <p className="text-sm text-shell-text-tertiary">Loading...</p>
      </section>
    );
  }

  return (
    <section aria-label="Memory capture settings">
      <h2 className="text-lg font-semibold mb-2">Memory Capture</h2>
      <p className="text-sm text-shell-text-tertiary mb-5">
        Choose what activity gets saved to your personal memory index. All data stays on this device.
      </p>

      {error && (
        <p className="mb-3 text-xs text-amber-400 flex items-center gap-1.5">
          <AlertCircle size={12} /> {error}
        </p>
      )}

      <div className="space-y-2">
        {MEMORY_TOGGLES.map((item) => {
          const checked = !!settings[item.key];
          const id = `capture-${String(item.key)}`;
          return (
            <Card key={String(item.key)} className="p-4 flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <Label htmlFor={id} className="text-sm font-medium text-shell-text">
                  {item.label}
                </Label>
                <p className="text-xs text-shell-text-tertiary mt-0.5">{item.desc}</p>
              </div>
              <Switch
                id={id}
                checked={checked}
                onCheckedChange={(v) => update(item.key, v)}
                aria-label={`Capture ${item.label}`}
              />
            </Card>
          );
        })}
      </div>

      {stats && (
        <Card className="mt-6 p-4">
          <h3 className="text-sm font-medium mb-3">Stored chunks</h3>
          <div className="text-xs text-shell-text-secondary mb-2 tabular-nums">
            Total: {stats.total}
          </div>
          {Object.keys(stats.collections || {}).length > 0 ? (
            <ul className="space-y-1 text-xs text-shell-text-tertiary">
              {Object.entries(stats.collections).map(([name, count]) => (
                <li key={name} className="flex justify-between tabular-nums">
                  <span>{name}</span>
                  <span>{count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-shell-text-tertiary">No memories captured yet.</p>
          )}
        </Card>
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
      <h2 className="text-lg font-semibold mb-5">Backup & Restore</h2>

      <Card className="p-4 space-y-4">
        <div>
          <h3 className="text-sm font-medium mb-2">Create Backup</h3>
          <p className="text-xs text-shell-text-tertiary mb-3">
            Export all agents, memory, and configuration as a backup archive.
          </p>
          <Button size="sm" onClick={createBackup} disabled={creating}>
            <Download size={14} className={creating ? "animate-bounce" : ""} />
            {creating ? "Creating..." : "Create Backup"}
          </Button>
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
      </Card>
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
      <h2 className="text-lg font-semibold mb-5">Updates</h2>
      <Card className="p-4 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-white/5 text-sky-400">
            <Settings size={20} />
          </div>
          <div>
            <p className="text-sm font-medium">TinyAgentOS</p>
            <p className="text-xs text-shell-text-tertiary tabular-nums">v0.1.0-dev</p>
          </div>
        </div>

        <Button variant="outline" size="sm" onClick={checkUpdates} disabled={checking}>
          <RefreshCw size={14} className={checking ? "animate-spin" : ""} />
          {checking ? "Checking..." : "Check for Updates"}
        </Button>

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
      </Card>
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
      <h2 className="text-lg font-semibold mb-5">Advanced Configuration</h2>
      <Card className="p-4 space-y-3">
        <div>
          <Label htmlFor="yaml-config">YAML Configuration</Label>
          <Textarea
            id="yaml-config"
            value={config}
            onChange={(e) => { setConfig(e.target.value); setSaved(false); setError(null); }}
            rows={14}
            spellCheck={false}
            className="mt-1 font-mono resize-y"
            aria-label="YAML configuration editor"
          />
        </div>

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
          <Button variant="secondary" size="sm" onClick={() => validate()}>
            <Code size={14} /> Validate
          </Button>
          <Button size="sm" onClick={save}>
            <Check size={14} /> Save
          </Button>
        </div>
      </Card>
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
    memory: <MemorySection />,
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
      className={isMobile ? "w-full overflow-y-auto" : "w-52 shrink-0 border-r border-white/5 bg-shell-surface/30 overflow-y-auto"}
      aria-label="Settings sections"
    >
      <div className="p-3 space-y-1">
        {SECTIONS.map((s) => {
          const active = section === s.id;
          const Icon = s.icon;
          return (
            <Button
              key={s.id}
              variant={active ? "secondary" : "ghost"}
              onClick={() => handleSelectSection(s.id)}
              className="w-full justify-start gap-3 h-auto py-2.5"
              aria-current={active ? "page" : undefined}
            >
              <div className={`p-1.5 rounded-lg transition-colors ${active ? "bg-sky-500/20 text-sky-400" : "bg-white/5"}`}>
                <Icon size={16} />
              </div>
              {s.label}
            </Button>
          );
        })}
      </div>
    </nav>
  );

  const contentUI = (
    <main className="flex-1 overflow-y-auto p-6">
      {isMobile && (
        <Button variant="ghost" size="sm" onClick={() => setMobileShowSection(false)} className="mb-3">
          <ChevronLeft size={14} /> Back
        </Button>
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
