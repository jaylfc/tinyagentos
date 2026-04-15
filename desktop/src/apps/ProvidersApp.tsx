import { useState, useEffect, useCallback } from "react";
import { Cloud, Plus, Trash2, Copy, Check, RefreshCw, Edit, X, ExternalLink } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  Input,
  Label,
} from "@/components/ui";
import { useProcessStore } from "@/stores/process-store";
import { getApp } from "@/registry/app-registry";
import { MobileSplitView } from "@/components/mobile/MobileSplitView";
import { useIsMobile } from "@/hooks/use-is-mobile";

/* ------------------------------------------------------------------ */
/*  Constants — matches VALID_BACKEND_TYPES in tinyagentos/config.py  */
/* ------------------------------------------------------------------ */

const CLOUD_TYPES = ["openai", "anthropic"] as const;
const LOCAL_TYPES = ["rkllama", "ollama", "llama-cpp", "vllm", "exo", "mlx"] as const;
type ProviderType = typeof CLOUD_TYPES[number] | typeof LOCAL_TYPES[number];

const DEFAULT_URLS: Partial<Record<ProviderType, string>> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  ollama: "http://localhost:11434",
  rkllama: "http://localhost:8080",
  "llama-cpp": "http://localhost:8080",
  vllm: "http://localhost:8000",
};

const STATUS_PILL: Record<string, string> = {
  ok: "bg-emerald-500/20 text-emerald-400",
  online: "bg-emerald-500/20 text-emerald-400",
  slow: "bg-amber-500/20 text-amber-400",
  error: "bg-red-500/20 text-red-400",
  unknown: "bg-zinc-500/20 text-zinc-400",
};

const STATUS_LABEL: Record<string, string> = {
  ok: "Online",
  online: "Online",
  slow: "Slow",
  error: "Error",
  unknown: "Unknown",
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ProviderModel {
  id?: string;
  name?: string;
  [key: string]: unknown;
}

type ProviderCategory = "local" | "network" | "cloud";

interface Provider {
  name: string;
  type: string;
  url: string;
  priority: number;
  api_key_secret?: string;
  model?: string;
  status: string;
  response_ms: number;
  models: ProviderModel[];
  source?: string;
  category?: ProviderCategory;
  worker_name?: string;
  worker_url?: string;
  worker_platform?: string;
  // Lifecycle
  lifecycle_state?: "stopped" | "starting" | "running" | "draining" | "stopping";
  auto_manage?: boolean;
  keep_alive_minutes?: number;
  enabled?: boolean;
}

const CATEGORY_LABELS: Record<ProviderCategory, string> = {
  local: "Local / On Device",
  network: "Network / Cluster",
  cloud: "Cloud",
};

const CATEGORY_ORDER: ProviderCategory[] = ["local", "network", "cloud"];

interface FormState {
  name: string;
  type: ProviderType;
  url: string;
  apiKey: string;
  model: string;
  priority: string;
}

type TestResult = { reachable: boolean; response_ms?: number; models?: ProviderModel[]; error?: string } | null;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function isCloud(type: string): boolean {
  return (CLOUD_TYPES as readonly string[]).includes(type);
}

function TypePill({ type }: { type: string }) {
  const cloud = isCloud(type);
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
        cloud ? "bg-violet-500/20 text-violet-300" : "bg-teal-500/20 text-teal-300"
      }`}
    >
      {type}
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  const cls = STATUS_PILL[status] ?? STATUS_PILL.unknown;
  const label = STATUS_LABEL[status] ?? "Unknown";
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cls}`}>
      {label}
    </span>
  );
}

const LIFECYCLE_PILL: Record<string, string> = {
  running:  "bg-emerald-500/20 text-emerald-400",
  stopped:  "bg-zinc-500/20 text-zinc-400",
  starting: "bg-blue-500/20 text-blue-400",
  draining: "bg-amber-500/20 text-amber-400",
  stopping: "bg-amber-500/20 text-amber-400",
};

const LIFECYCLE_LABEL: Record<string, string> = {
  running:  "Running",
  stopped:  "Stopped",
  starting: "Starting…",
  draining: "Draining…",
  stopping: "Stopping…",
};

function LifecycleStatePill({ state }: { state: string }) {
  const cls = LIFECYCLE_PILL[state] ?? LIFECYCLE_PILL.stopped;
  const label = LIFECYCLE_LABEL[state] ?? state;
  const isTransitional = state === "starting" || state === "draining" || state === "stopping";
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium inline-flex items-center gap-1 ${cls}`}>
      {isTransitional && (
        <svg className="animate-spin" width="8" height="8" viewBox="0 0 8 8" fill="none" aria-hidden="true">
          <circle cx="4" cy="4" r="3" stroke="currentColor" strokeWidth="1.5" strokeDasharray="10" strokeDashoffset="5" />
        </svg>
      )}
      {label}
    </span>
  );
}

function WorkerBadge({ name, platform }: { name: string; platform?: string }) {
  const platformLabel = platform ? ` · ${platform}` : "";
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-blue-500/20 text-blue-300 inline-flex items-center gap-1"
      title={`Backend on worker ${name}${platformLabel}`}
    >
      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
        <circle cx="4" cy="4" r="3" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      {name}
    </span>
  );
}

function groupByCategory(providers: Provider[]): Record<ProviderCategory, Provider[]> {
  const groups: Record<ProviderCategory, Provider[]> = { local: [], network: [], cloud: [] };
  for (const p of providers) {
    const cat: ProviderCategory = p.category ?? (p.source?.startsWith("worker:") ? "network" : (CLOUD_TYPES as readonly string[]).includes(p.type) ? "cloud" : "local");
    groups[cat].push(p);
  }
  return groups;
}

function defaultFormState(editingProvider?: Provider | null): FormState {
  if (editingProvider) {
    return {
      name: editingProvider.name,
      type: editingProvider.type as ProviderType,
      url: editingProvider.url,
      apiKey: "",
      model: editingProvider.model ?? "",
      priority: String(editingProvider.priority ?? 99),
    };
  }
  return {
    name: "",
    type: "openai",
    url: DEFAULT_URLS.openai ?? "",
    apiKey: "",
    model: "",
    priority: "99",
  };
}

/* ------------------------------------------------------------------ */
/*  AddEditForm modal                                                  */
/* ------------------------------------------------------------------ */

function ProviderForm({
  editing,
  onSave,
  onClose,
}: {
  editing: Provider | null;
  onSave: () => void;
  onClose: () => void;
}) {
  const isMobile = useIsMobile();
  const [form, setForm] = useState<FormState>(() => defaultFormState(editing));
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [forceEnabled, setForceEnabled] = useState(false);

  const isEdit = !!editing;

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setTestResult(null);
    setForceEnabled(false);
  }

  function handleTypeChange(t: ProviderType) {
    setForm((prev) => ({
      ...prev,
      type: t,
      url: DEFAULT_URLS[t] ?? prev.url,
    }));
    setTestResult(null);
    setForceEnabled(false);
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    setSaveError(null);
    try {
      const res = await fetch("/api/providers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ type: form.type, url: form.url }),
      });
      const data = await res.json();
      setTestResult(data);
    } catch (e) {
      setTestResult({ reachable: false, error: e instanceof Error ? e.message : "Network error" });
    }
    setTesting(false);
  }

  async function handleSave() {
    if (!form.name.trim()) { setSaveError("Name is required"); return; }
    setSaving(true);
    setSaveError(null);

    // If a new API key is provided, save it as a secret first
    let apiKeySecret: string | undefined = editing?.api_key_secret;
    if (form.apiKey.trim()) {
      const secretName = `provider-${form.name.trim()}-key`;
      try {
        await fetch("/api/secrets", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            name: secretName,
            value: form.apiKey.trim(),
            category: "api-key",
            description: `API key for ${form.name.trim()} provider`,
            agents: [],
          }),
        });
        apiKeySecret = secretName;
      } catch {
        /* continue even if secret save fails */
      }
    }

    try {
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        type: form.type,
        url: form.url.trim(),
        priority: parseInt(form.priority) || 99,
        model: form.model.trim() || "default",
      };
      if (apiKeySecret) payload.api_key_secret = apiKeySecret;

      // For edits, delete first then re-create
      if (isEdit) {
        await fetch(`/api/providers/${encodeURIComponent(editing!.name)}`, {
          method: "DELETE",
          headers: { Accept: "application/json" },
        });
      }

      const res = await fetch("/api/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let msg = `Save failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.error) msg = String(err.error);
        } catch { /* ignore */ }
        setSaveError(msg);
        setSaving(false);
        return;
      }
      onSave();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Network error");
      setSaving(false);
    }
  }

  const canSave = (testResult?.reachable === true || forceEnabled) && form.name.trim().length > 0;

  return (
    <div
      className={
        isMobile
          ? "absolute inset-0 z-50 flex items-end bg-black/50 backdrop-blur-sm"
          : "absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      }
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={isEdit ? "Edit provider" : "Add provider"}
    >
      <Card
        className={
          isMobile
            ? "w-full max-h-[92%] overflow-y-auto bg-shell-surface shadow-2xl"
            : "w-full max-w-md max-h-full overflow-y-auto bg-shell-surface shadow-2xl"
        }
        style={isMobile ? { borderRadius: "20px 20px 0 0" } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <CardContent className="p-5 space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cloud size={16} className="text-accent" />
              <h2 className="text-sm font-semibold">{isEdit ? "Edit Provider" : "Add Provider"}</h2>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close form" className="h-7 w-7">
              <X size={16} />
            </Button>
          </div>

          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="prov-name">Name</Label>
            <Input
              id="prov-name"
              type="text"
              value={form.name}
              onChange={(e) => setField("name", e.target.value)}
              placeholder="my-openai"
              disabled={isEdit}
              autoFocus={!isEdit}
            />
          </div>

          {/* Type */}
          <div className="space-y-1.5">
            <Label htmlFor="prov-type">Type</Label>
            <select
              id="prov-type"
              value={form.type}
              onChange={(e) => handleTypeChange(e.target.value as ProviderType)}
              disabled={isEdit}
              className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20"
            >
              <optgroup label="Cloud">
                {CLOUD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </optgroup>
              <optgroup label="Local">
                {LOCAL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </optgroup>
            </select>
          </div>

          {/* URL */}
          <div className="space-y-1.5">
            <Label htmlFor="prov-url">URL</Label>
            <Input
              id="prov-url"
              type="url"
              value={form.url}
              onChange={(e) => setField("url", e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </div>

          {/* API Key (cloud only) */}
          {isCloud(form.type) && (
            <div className="space-y-1.5">
              <Label htmlFor="prov-apikey">
                API Key{isEdit && " (leave blank to keep existing)"}
              </Label>
              <Input
                id="prov-apikey"
                type="password"
                value={form.apiKey}
                onChange={(e) => setField("apiKey", e.target.value)}
                placeholder={isEdit ? "••••••••" : "sk-..."}
                className="font-mono"
              />
              <p className="text-[10px] text-shell-text-tertiary">
                Saved automatically as <code>provider-{form.name || "{name}"}-key</code>
              </p>
            </div>
          )}

          {/* Default model */}
          <div className="space-y-1.5">
            <Label htmlFor="prov-model">Default Model (optional)</Label>
            <Input
              id="prov-model"
              type="text"
              value={form.model}
              onChange={(e) => setField("model", e.target.value)}
              placeholder="default"
            />
          </div>

          {/* Priority */}
          <div className="space-y-1.5">
            <Label htmlFor="prov-priority">Priority (lower wins)</Label>
            <Input
              id="prov-priority"
              type="number"
              value={form.priority}
              onChange={(e) => setField("priority", e.target.value)}
              placeholder="99"
              min={0}
            />
          </div>

          {/* Test result */}
          {testResult && (
            <div
              role="status"
              className={`text-xs rounded-lg px-3 py-2 border ${
                testResult.reachable
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
                  : "bg-red-500/10 border-red-500/20 text-red-300"
              }`}
            >
              {testResult.reachable
                ? `Connected — ${testResult.response_ms ?? 0} ms · ${testResult.models?.length ?? 0} models found`
                : `Connection failed: ${testResult.error ?? "unknown error"}`}
            </div>
          )}

          {saveError && (
            <div role="alert" className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded px-2 py-1.5">
              {saveError}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTest}
              disabled={testing || !form.url.trim()}
              aria-label="Test provider connection"
            >
              <RefreshCw size={13} className={testing ? "animate-spin" : ""} />
              {testing ? "Testing..." : "Test connection"}
            </Button>
            <Button
              onClick={handleSave}
              disabled={!canSave || saving}
              aria-label={isEdit ? "Update provider" : "Save provider"}
            >
              {saving ? "Saving..." : isEdit ? "Update" : "Save"}
            </Button>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            {testResult && !testResult.reachable && !forceEnabled && (
              <button
                type="button"
                onClick={() => setForceEnabled(true)}
                className="text-[11px] text-shell-text-tertiary underline hover:text-shell-text transition-colors ml-auto"
                aria-label="Save anyway despite connection failure"
              >
                Save anyway
              </button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Detail pane                                                        */
/* ------------------------------------------------------------------ */

function ProviderDetail({
  provider,
  onEdit,
  onDelete,
  onTestDone,
  onRefresh,
}: {
  provider: Provider;
  onEdit: () => void;
  onDelete: () => void;
  onTestDone: (result: TestResult) => void;
  onRefresh: () => void;
}) {
  const isMobile = useIsMobile();
  const [copied, setCopied] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [lifecycleLoading, setLifecycleLoading] = useState(false);

  const lifecycleState = provider.lifecycle_state ?? "running";
  const isLocal = !provider.source?.startsWith("worker:");
  const isTransitional = lifecycleState === "starting" || lifecycleState === "draining" || lifecycleState === "stopping";

  const openWindow = useProcessStore((s) => s.openWindow);

  function openSecretsApp() {
    const app = getApp("secrets");
    if (app) openWindow("secrets", app.defaultSize);
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch { /* no-op */ }
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/providers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ type: provider.type, url: provider.url }),
      });
      const data = await res.json();
      setTestResult(data);
      onTestDone(data);
    } catch (e) {
      const r = { reachable: false, error: e instanceof Error ? e.message : "Network error" };
      setTestResult(r);
      onTestDone(r);
    }
    setTesting(false);
  }

  async function handleStart() {
    setLifecycleLoading(true);
    try {
      await fetch(`/api/providers/${encodeURIComponent(provider.name)}/start`, { method: "POST" });
      onRefresh();
    } finally {
      setLifecycleLoading(false);
    }
  }

  async function handleStop(force: boolean) {
    setLifecycleLoading(true);
    try {
      await fetch(`/api/providers/${encodeURIComponent(provider.name)}/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force }),
      });
      onRefresh();
    } finally {
      setLifecycleLoading(false);
    }
  }

  async function handlePatch(patch: { enabled?: boolean; auto_manage?: boolean; keep_alive_minutes?: number }) {
    await fetch(`/api/providers/${encodeURIComponent(provider.name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    onRefresh();
  }

  const models = provider.models ?? [];

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* Header — hide on mobile (MobileSplitView nav bar shows the name) */}
      {!isMobile && (
        <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-white/5 shrink-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-sm font-semibold text-shell-text truncate">{provider.name}</h2>
              <TypePill type={provider.type} />
              <StatusPill status={provider.status} />
              {isLocal && provider.lifecycle_state && (
                <LifecycleStatePill state={lifecycleState} />
              )}
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-shell-text-tertiary">
                priority {provider.priority}
              </span>
            </div>
            {provider.response_ms > 0 && (
              <p className="text-[11px] text-shell-text-tertiary mt-0.5">{provider.response_ms} ms</p>
            )}
          </div>
          {/* Action buttons — lifecycle state aware */}
          <div className="flex items-center gap-1 shrink-0">
            {isLocal && lifecycleState === "stopped" && (
              <Button size="sm" variant="outline" onClick={handleStart} disabled={lifecycleLoading}
                aria-label={`Start provider ${provider.name}`}>
                {lifecycleLoading ? "Starting…" : "Start"}
              </Button>
            )}
            {isLocal && lifecycleState === "running" && (
              <>
                <Button size="sm" variant="outline" onClick={handleTest} disabled={testing}
                  aria-label={`Test connection for ${provider.name}`}>
                  <RefreshCw size={13} className={testing ? "animate-spin" : ""} />
                  {testing ? "Testing..." : "Test"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleStop(false)} disabled={lifecycleLoading}
                  aria-label={`Stop provider ${provider.name}`}>
                  Stop
                </Button>
                <button
                  onClick={() => handleStop(true)}
                  disabled={lifecycleLoading}
                  className="text-[11px] text-red-400 hover:text-red-300 px-1"
                  aria-label={`Force kill provider ${provider.name}`}
                >
                  Kill
                </button>
              </>
            )}
            {isLocal && isTransitional && (
              <span className="text-[11px] text-shell-text-tertiary px-2">
                {LIFECYCLE_LABEL[lifecycleState]}
              </span>
            )}
            {(!isLocal || lifecycleState === "running" || !provider.lifecycle_state) && (
              <>
                {!isLocal && (
                  <Button size="sm" variant="outline" onClick={handleTest} disabled={testing}
                    aria-label={`Test connection for ${provider.name}`}>
                    <RefreshCw size={13} className={testing ? "animate-spin" : ""} />
                    {testing ? "Testing..." : "Test"}
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={onEdit} aria-label={`Edit provider ${provider.name}`}>
                  <Edit size={13} />
                  Edit
                </Button>
                <Button size="sm" variant="outline" onClick={onDelete}
                  className="hover:bg-red-500/15 hover:text-red-300"
                  aria-label={`Delete provider ${provider.name}`}>
                  <Trash2 size={13} />
                  Delete
                </Button>
              </>
            )}
          </div>
        </div>
      )}
      {/* Mobile: status + pills + action buttons shown as a prominent summary row */}
      {isMobile && (
        <div className="shrink-0 px-4 py-3 border-b border-white/5">
          <div className="flex items-center gap-2 flex-wrap mb-3">
            <TypePill type={provider.type} />
            <StatusPill status={provider.status} />
            <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/5 text-shell-text-tertiary">
              priority {provider.priority}
            </span>
            {provider.response_ms > 0 && (
              <span className="text-[11px] text-shell-text-tertiary">{provider.response_ms} ms</span>
            )}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={handleTest} disabled={testing} className="flex-1">
              <RefreshCw size={13} className={testing ? "animate-spin" : ""} />
              {testing ? "Testing..." : "Test"}
            </Button>
            <Button size="sm" variant="outline" onClick={onEdit} className="flex-1">
              <Edit size={13} />
              Edit
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onDelete}
              className="flex-1 hover:bg-red-500/15 hover:text-red-300"
            >
              <Trash2 size={13} />
              Delete
            </Button>
          </div>
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Test result */}
        {testResult && (
          <div
            role="status"
            className={`text-xs rounded-lg px-3 py-2 border ${
              testResult.reachable
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
                : "bg-red-500/10 border-red-500/20 text-red-300"
            }`}
          >
            {testResult.reachable
              ? `Connected — ${testResult.response_ms ?? 0} ms · ${testResult.models?.length ?? 0} models found`
              : lifecycleState === "stopped" && (provider.auto_manage ?? false)
              ? "Starting service…"
              : lifecycleState === "stopped"
              ? "Service is stopped. Start it manually or enable Auto manage."
              : testResult.error?.includes("Cannot connect") || testResult.error?.includes("Connection refused") || testResult.error?.includes("connect")
              ? `Cannot reach ${provider.url}. Check the service is running.`
              : `Connection failed: ${testResult.error ?? "unknown error"}`}
          </div>
        )}

        {/* URL */}
        <Card className="p-3">
          <CardContent className="p-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase tracking-wide text-shell-text-tertiary">Base URL</span>
            </div>
            <div className="flex items-center gap-2">
              <code className="text-xs text-shell-text flex-1 truncate font-mono">{provider.url}</code>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={() => copy(provider.url)}
                aria-label="Copy URL"
              >
                {copied ? <Check size={12} /> : <Copy size={12} />}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* API key */}
        <Card className="p-3">
          <CardContent className="p-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase tracking-wide text-shell-text-tertiary">API Key</span>
            </div>
            {provider.api_key_secret ? (
              <div className="flex items-center gap-2">
                <code className="text-xs text-shell-text-secondary font-mono flex-1">{provider.api_key_secret}</code>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={openSecretsApp}
                  className="h-6 text-[10px] gap-1"
                  aria-label="Open Secrets app to manage this key"
                >
                  <ExternalLink size={10} />
                  Manage
                </Button>
              </div>
            ) : (
              <p className="text-xs text-shell-text-tertiary italic">
                {isCloud(provider.type) ? "No key configured" : "Not required — local backend"}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Models */}
        <Card className="p-3">
          <CardContent className="p-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] uppercase tracking-wide text-shell-text-tertiary">
                Models ({models.length})
              </span>
            </div>
            {models.length === 0 ? (
              <p className="text-xs text-shell-text-tertiary italic">No models loaded</p>
            ) : (
              <div className="flex flex-wrap gap-1">
                {models.map((m, i) => {
                  const label = m.id ?? m.name ?? String(i);
                  return (
                    <span
                      key={`m-${i}-${label}`}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-200 font-medium"
                    >
                      {label}
                    </span>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Lifecycle settings — only for local, auto-managed providers */}
        {isLocal && provider.auto_manage !== undefined && (
          <Card className="p-0 overflow-hidden">
            <div className="px-3 py-2 border-b border-white/5">
              <span className="text-[10px] font-medium text-shell-text-tertiary uppercase tracking-wider">
                Lifecycle
              </span>
            </div>
            <CardContent className="p-3 space-y-3">
              {/* Enabled toggle */}
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-shell-text-secondary">Enabled</span>
                <button
                  role="switch"
                  aria-checked={provider.enabled ?? true}
                  aria-label="Toggle provider enabled"
                  onClick={() => handlePatch({ enabled: !(provider.enabled ?? true) })}
                  className={`w-8 h-4 rounded-full transition-colors relative ${
                    (provider.enabled ?? true) ? "bg-emerald-500" : "bg-zinc-600"
                  }`}
                >
                  <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                    (provider.enabled ?? true) ? "translate-x-4" : "translate-x-0.5"
                  }`} />
                </button>
              </div>
              {/* Auto manage toggle */}
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-shell-text-secondary">Auto manage</span>
                <button
                  role="switch"
                  aria-checked={provider.auto_manage ?? false}
                  aria-label="Toggle auto manage"
                  onClick={() => handlePatch({ auto_manage: !(provider.auto_manage ?? false) })}
                  className={`w-8 h-4 rounded-full transition-colors relative ${
                    (provider.auto_manage ?? false) ? "bg-emerald-500" : "bg-zinc-600"
                  }`}
                >
                  <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                    (provider.auto_manage ?? false) ? "translate-x-4" : "translate-x-0.5"
                  }`} />
                </button>
              </div>
              {/* Keep alive — only shown when auto manage is on */}
              {(provider.auto_manage ?? false) && (
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <span className="text-[12px] text-shell-text-secondary">Keep alive</span>
                    <p className="text-[10px] text-shell-text-tertiary">
                      {(provider.keep_alive_minutes ?? 10) === 0
                        ? "Always on"
                        : `Stop after ${provider.keep_alive_minutes ?? 10} min idle`}
                    </p>
                  </div>
                  <input
                    type="number"
                    min={0}
                    max={60}
                    value={provider.keep_alive_minutes ?? 10}
                    onChange={(e) => handlePatch({ keep_alive_minutes: Number(e.target.value) })}
                    className="w-14 text-[12px] bg-white/5 border border-white/10 rounded px-2 py-1 text-right text-shell-text"
                    aria-label="Keep alive minutes (0 = always on)"
                  />
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ProvidersApp                                                       */
/* ------------------------------------------------------------------ */

export function ProvidersApp({ windowId: _windowId }: { windowId: string }) {
  const isMobile = useIsMobile();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  }, []);

  const fetchProviders = useCallback(async () => {
    try {
      const res = await fetch("/api/providers", { headers: { Accept: "application/json" } });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data)) {
            setProviders(data as Provider[]);
            setSelected((cur) => {
              if (cur && data.some((p: Provider) => p.name === cur)) return cur;
              // On mobile, let the user pick from the list — don't auto-select.
              if (isMobile) return null;
              return data.length > 0 ? (data[0] as Provider).name : null;
            });
          }
        }
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchProviders();
    const interval = setInterval(fetchProviders, 30_000);
    return () => clearInterval(interval);
  }, [fetchProviders]);

  async function handleDelete(name: string) {
    if (!window.confirm(`Remove provider "${name}"?`)) return;
    try {
      const res = await fetch(`/api/providers/${encodeURIComponent(name)}`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        let msg = `Delete failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.error) msg = String(err.error);
        } catch { /* ignore */ }
        showToast(msg);
        return;
      }
      showToast(`Provider "${name}" removed`);
      setSelected(null);
      fetchProviders();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Network error");
    }
  }

  function openAdd() {
    setEditingProvider(null);
    setShowForm(true);
  }

  function openEdit(p: Provider) {
    setEditingProvider(p);
    setShowForm(true);
  }

  function handleFormSave() {
    setShowForm(false);
    setEditingProvider(null);
    fetchProviders();
  }

  function handleFormClose() {
    setShowForm(false);
    setEditingProvider(null);
  }

  const selectedProvider = providers.find((p) => p.name === selected) ?? null;

  // Hide the app-level toolbar on mobile when viewing detail — the
  // MobileSplitView provides its own nav bar with back button there.
  const showToolbar = !isMobile || selected === null;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden bg-shell-bg text-shell-text select-none relative">
      {/* Toolbar */}
      {showToolbar && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Cloud size={18} className="text-accent shrink-0" />
            <h1 className="text-sm font-semibold">Providers</h1>
            <span className="text-xs text-shell-text-tertiary">
              {providers.length} configured
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={fetchProviders} aria-label="Refresh provider list">
              <RefreshCw size={14} />
            </Button>
            <Button size="sm" onClick={openAdd} aria-label="Add provider">
              <Plus size={14} />
              {isMobile ? "Add" : "Add Provider"}
            </Button>
          </div>
        </div>
      )}

      {/* Master-detail — MobileSplitView stacks on mobile, splits on desktop */}
      <MobileSplitView
        selectedId={selected}
        onBack={() => setSelected(null)}
        listTitle="Providers"
        detailTitle={selectedProvider?.name}
        list={
          <div className={isMobile ? "py-2" : "p-3 space-y-2"} aria-label="Provider list">
            {loading ? (
              <div className="text-[11px] text-shell-text-tertiary px-4 py-6 text-center">
                Loading providers...
              </div>
            ) : providers.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-10 text-center px-4">
                <Cloud size={36} className="opacity-20 text-shell-text-tertiary" />
                <p className="text-[13px] text-shell-text-tertiary">No providers configured yet.</p>
                <Button size="sm" onClick={openAdd} className="mt-2">
                  <Plus size={13} />
                  Add your first
                </Button>
              </div>
            ) : (
              (() => {
                const groups = groupByCategory(providers);
                const nonEmpty = CATEGORY_ORDER.filter((c) => groups[c].length > 0);

                if (isMobile) {
                  return (
                    <div style={{ padding: "8px 0 16px" }}>
                      {nonEmpty.map((cat) => (
                        <div key={cat} style={{ marginBottom: 20 }}>
                          <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.45)", padding: "0 20px 6px", fontWeight: 600 }}>
                            {CATEGORY_LABELS[cat]}
                          </div>
                          <div
                            style={{
                              margin: "0 12px",
                              borderRadius: 16,
                              background: "rgba(255,255,255,0.05)",
                              border: "1px solid rgba(255,255,255,0.08)",
                              overflow: "hidden",
                            }}
                          >
                            {groups[cat].map((p, idx, arr) => (
                              <button
                                key={p.name}
                                type="button"
                                onClick={() => setSelected(p.name)}
                                aria-label={`Select provider ${p.name}`}
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 10,
                                  width: "100%",
                                  padding: "14px 16px",
                                  background: "none",
                                  border: "none",
                                  borderBottom: idx === arr.length - 1 ? "none" : "1px solid rgba(255,255,255,0.06)",
                                  cursor: "pointer",
                                  color: "inherit",
                                  textAlign: "left",
                                }}
                              >
                                <div style={{ flex: 1, minWidth: 0 }}>
                                  <div style={{ fontSize: 15, fontWeight: 600, color: "rgba(255,255,255,0.95)", display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
                                    <StatusPill status={p.status} />
                                  </div>
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <TypePill type={p.type} />
                                    {p.worker_name && <WorkerBadge name={p.worker_name} platform={p.worker_platform} />}
                                    <span className="text-[11px] text-shell-text-tertiary">priority {p.priority}</span>
                                    {p.models.length > 0 && (
                                      <span className="text-[11px] text-shell-text-tertiary">
                                        · {p.models.length} model{p.models.length !== 1 ? "s" : ""}
                                      </span>
                                    )}
                                  </div>
                                </div>
                                <svg width="8" height="14" viewBox="0 0 8 14" fill="none" style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }}>
                                  <path d="M1 1L7 7L1 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                }

                // Desktop — grouped list with section headers
                return nonEmpty.map((cat) => (
                  <div key={cat} className="mb-4">
                    <div className="text-[10px] uppercase tracking-wider text-shell-text-tertiary font-semibold px-1 mb-1.5">
                      {CATEGORY_LABELS[cat]}
                    </div>
                    <div className="space-y-1.5">
                      {groups[cat].map((p) => (
                        <button
                          key={p.name}
                          type="button"
                          onClick={() => setSelected(p.name)}
                          aria-pressed={selected === p.name}
                          aria-label={`Select provider ${p.name}`}
                          className={`w-full text-left p-2.5 rounded-lg border transition-colors ${
                            selected === p.name
                              ? "border-accent/50 bg-accent/10"
                              : "border-white/5 bg-white/[0.02] hover:bg-white/[0.04]"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1.5 mb-1">
                            <span className="text-[12px] font-semibold text-shell-text truncate">{p.name}</span>
                            <StatusPill status={p.status} />
                          </div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <TypePill type={p.type} />
                            {p.worker_name && <WorkerBadge name={p.worker_name} platform={p.worker_platform} />}
                            <span className="text-[10px] text-shell-text-tertiary">#{p.priority}</span>
                            {p.models.length > 0 && (
                              <span className="text-[10px] text-shell-text-tertiary">
                                {p.models.length} model{p.models.length !== 1 ? "s" : ""}
                              </span>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ));
              })()
            )}
          </div>
        }
        detail={
          selectedProvider ? (
            <ProviderDetail
              provider={selectedProvider}
              onEdit={() => openEdit(selectedProvider)}
              onDelete={() => handleDelete(selectedProvider.name)}
              onTestDone={() => fetchProviders()}
              onRefresh={fetchProviders}
            />
          ) : !isMobile ? (
            <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
              {loading ? "Loading..." : providers.length === 0 ? "Add a provider to get started" : "Select a provider"}
            </div>
          ) : null
        }
      />

      {/* Form modal */}
      {showForm && (
        <ProviderForm
          editing={editingProvider}
          onSave={handleFormSave}
          onClose={handleFormClose}
        />
      )}

      {/* Toast */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 px-3 py-2 rounded-lg bg-shell-surface border border-white/10 text-xs text-shell-text shadow-2xl"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
