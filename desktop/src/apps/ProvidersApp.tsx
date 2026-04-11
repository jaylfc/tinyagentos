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
}

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
      className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={isEdit ? "Edit provider" : "Add provider"}
    >
      <Card
        className="w-full max-w-md max-h-full overflow-y-auto bg-shell-surface shadow-2xl"
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
}: {
  provider: Provider;
  onEdit: () => void;
  onDelete: () => void;
  onTestDone: (result: TestResult) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult>(null);

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

  const models = provider.models ?? [];

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-white/5 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-sm font-semibold text-shell-text truncate">{provider.name}</h2>
            <TypePill type={provider.type} />
            <StatusPill status={provider.status} />
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-shell-text-tertiary">
              priority {provider.priority}
            </span>
          </div>
          {provider.response_ms > 0 && (
            <p className="text-[11px] text-shell-text-tertiary mt-0.5">{provider.response_ms} ms</p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            size="sm"
            variant="outline"
            onClick={handleTest}
            disabled={testing}
            aria-label={`Test connection for ${provider.name}`}
          >
            <RefreshCw size={13} className={testing ? "animate-spin" : ""} />
            {testing ? "Testing..." : "Test"}
          </Button>
          <Button size="sm" variant="outline" onClick={onEdit} aria-label={`Edit provider ${provider.name}`}>
            <Edit size={13} />
            Edit
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onDelete}
            className="hover:bg-red-500/15 hover:text-red-300"
            aria-label={`Delete provider ${provider.name}`}
          >
            <Trash2 size={13} />
            Delete
          </Button>
        </div>
      </div>

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
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ProvidersApp                                                       */
/* ------------------------------------------------------------------ */

export function ProvidersApp({ windowId: _windowId }: { windowId: string }) {
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

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden bg-shell-bg text-shell-text select-none relative">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-2">
          <Cloud size={18} className="text-accent" />
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
            Add Provider
          </Button>
        </div>
      </div>

      {/* Master-detail */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* List */}
        <aside
          className="w-64 shrink-0 border-r border-white/5 overflow-y-auto p-3 space-y-2"
          aria-label="Provider list"
        >
          {loading ? (
            <div className="text-[11px] text-shell-text-tertiary px-2 py-6 text-center">
              Loading providers...
            </div>
          ) : providers.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <Cloud size={32} className="opacity-20 text-shell-text-tertiary" />
              <p className="text-[11px] text-shell-text-tertiary">No providers configured yet.</p>
              <Button size="sm" onClick={openAdd} className="mt-1">
                <Plus size={13} />
                Add your first
              </Button>
            </div>
          ) : (
            providers.map((p) => (
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
                  <span className="text-[10px] text-shell-text-tertiary">#{p.priority}</span>
                  {p.models.length > 0 && (
                    <span className="text-[10px] text-shell-text-tertiary">
                      {p.models.length} model{p.models.length !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </aside>

        {/* Detail */}
        <section className="flex-1 min-w-0 min-h-0 overflow-hidden" aria-label="Provider detail">
          {selectedProvider ? (
            <ProviderDetail
              provider={selectedProvider}
              onEdit={() => openEdit(selectedProvider)}
              onDelete={() => handleDelete(selectedProvider.name)}
              onTestDone={() => fetchProviders()}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
              {loading ? "Loading..." : providers.length === 0 ? "Add a provider to get started" : "Select a provider"}
            </div>
          )}
        </section>
      </div>

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
