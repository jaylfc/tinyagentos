# Guided Add Provider Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat Add Provider form with a 3-step guided wizard (Category → Provider Pick → Config), add OpenRouter and Kilo as cloud provider types, fix the CloudAPI health adapter, and remove the model field from the provider flow entirely.

**Architecture:** Backend gains a `CloudAPIAdapter` (treats 401/403 as reachable — cloud APIs require auth) and two new types (`openrouter`, `kilocode`) in `VALID_BACKEND_TYPES`. Frontend replaces `ProviderForm` with a wizard: step 1 picks Local/Cluster/Cloud, step 2a picks a specific cloud provider from cards, step 2b shows cluster info, step 3 is the config form (cloud: read-only URL + API key; local: type/URL/priority). Edit mode skips straight to the config step. Model field is removed everywhere.

**Tech Stack:** Python/FastAPI backend, React/TypeScript frontend, Tailwind CSS, existing Card/Button/Input/Label components.

---

## File Structure

| File | Change |
|------|--------|
| `tinyagentos/config.py` | Add `"openrouter"`, `"kilocode"` to `VALID_BACKEND_TYPES` |
| `tinyagentos/backend_adapters.py` | Add `CloudAPIAdapter`; register `openai`, `anthropic`, `openrouter`, `kilocode` to it |
| `tinyagentos/routes/providers.py` | Remove `model` field from `ProviderCreate` |
| `tests/test_backend_adapters.py` | Add `TestCloudAPIAdapter` class + adapter registration tests |
| `desktop/src/apps/ProvidersApp.tsx` | Full wizard rewrite of `ProviderForm`; remove model field; add new constants |

---

## Task 1: Backend — CloudAPIAdapter + new types

**Files:**
- Modify: `tinyagentos/backend_adapters.py`
- Modify: `tinyagentos/config.py`
- Modify: `tinyagentos/routes/providers.py:30-36`
- Test: `tests/test_backend_adapters.py`

### Background

The current `OpenAICompatAdapter` calls `GET /health` first, then `GET /v1/models`. Cloud APIs (OpenAI, Anthropic, OpenRouter, Kilo) don't have a `/health` endpoint — they return 404 or 405, causing the adapter to always return `"status": "error"` for cloud providers. The fix is a dedicated `CloudAPIAdapter` that probes `GET /models` (no auth) and treats HTTP 200, 401, and 403 as "reachable" (401/403 means the server is up, just needs a key).

The `ProviderCreate` model has a `model: str = "default"` field that should not exist — model selection is done in the Models app, not here.

- [ ] **Step 1: Write failing tests for `CloudAPIAdapter`**

Add to `tests/test_backend_adapters.py` after the existing `TestOllamaAdapter` class:

```python
from tinyagentos.backend_adapters import CloudAPIAdapter

class TestCloudAPIAdapter:
    @pytest.mark.asyncio
    async def test_200_is_ok(self):
        adapter = CloudAPIAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
        mock_client.get.return_value = resp
        result = await adapter.health(mock_client, "https://api.openai.com/v1")
        assert result["status"] == "ok"
        assert result["models"] == [{"name": "gpt-4o", "size_mb": 0}, {"name": "gpt-4o-mini", "size_mb": 0}]
        assert "response_ms" in result

    @pytest.mark.asyncio
    async def test_401_is_ok(self):
        """401 = server is reachable, just needs auth — count as online."""
        adapter = CloudAPIAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 401
        mock_client.get.return_value = resp
        result = await adapter.health(mock_client, "https://api.openai.com/v1")
        assert result["status"] == "ok"
        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_403_is_ok(self):
        adapter = CloudAPIAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 403
        mock_client.get.return_value = resp
        result = await adapter.health(mock_client, "https://api.openai.com/v1")
        assert result["status"] == "ok"
        assert result["models"] == []

    @pytest.mark.asyncio
    async def test_500_is_error(self):
        adapter = CloudAPIAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        resp = MagicMock()
        resp.status_code = 500
        mock_client.get.return_value = resp
        result = await adapter.health(mock_client, "https://api.openai.com/v1")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_connection_error_is_error(self):
        adapter = CloudAPIAdapter()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        result = await adapter.health(mock_client, "https://api.openai.com/v1")
        assert result["status"] == "error"
        assert result["models"] == []

    def test_get_adapter_openai_uses_cloud(self):
        assert isinstance(get_adapter("openai"), CloudAPIAdapter)

    def test_get_adapter_anthropic_uses_cloud(self):
        assert isinstance(get_adapter("anthropic"), CloudAPIAdapter)

    def test_get_adapter_openrouter(self):
        assert isinstance(get_adapter("openrouter"), CloudAPIAdapter)

    def test_get_adapter_kilocode(self):
        assert isinstance(get_adapter("kilocode"), CloudAPIAdapter)
```

- [ ] **Step 2: Run to confirm they fail**

```bash
python3 -m pytest tests/test_backend_adapters.py::TestCloudAPIAdapter -v
```
Expected: FAIL — `ImportError: cannot import name 'CloudAPIAdapter'`

- [ ] **Step 3: Add `CloudAPIAdapter` to `backend_adapters.py`**

After the `StableDiffusionCppAdapter` class (after line 100), add:

```python
class CloudAPIAdapter(BackendAdapter):
    """Adapter for hosted cloud AI APIs (OpenAI, Anthropic, OpenRouter, Kilo).

    Cloud APIs have no /health endpoint. We probe GET /models without auth:
    - 2xx  = online (public model list)
    - 401/403 = online (API is responding, just needs a key)
    - anything else = error
    """

    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        base = url.rstrip("/")
        try:
            resp = await client.get(f"{base}/models", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if resp.status_code in (200, 401, 403):
                models = []
                if resp.status_code == 200:
                    try:
                        models = [
                            {"name": m.get("id", ""), "size_mb": 0}
                            for m in resp.json().get("data", [])
                        ]
                    except Exception:
                        pass
                return {"status": "ok", "response_ms": elapsed_ms, "models": models}
            return {"status": "error", "response_ms": elapsed_ms, "models": []}
        except Exception:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}
```

Then update the `_ADAPTERS` dict and the type aliases section at the bottom of the file. Replace the existing `_ADAPTERS` dict and type aliases with:

```python
# Type aliases for backwards compatibility with tests
RkLlamaAdapter = OllamaCompatAdapter
OllamaAdapter = OllamaCompatAdapter
LlamaCppAdapter = OpenAICompatAdapter
VllmAdapter = OpenAICompatAdapter
ExoAdapter = OpenAICompatAdapter

_ADAPTERS: dict[str, BackendAdapter] = {
    "rkllama": OllamaCompatAdapter(),
    "ollama": OllamaCompatAdapter(),
    "llama-cpp": OpenAICompatAdapter(),
    "vllm": OpenAICompatAdapter(),
    "exo": OpenAICompatAdapter(),
    "mlx": OpenAICompatAdapter(),
    "openai": CloudAPIAdapter(),
    "anthropic": CloudAPIAdapter(),
    "openrouter": CloudAPIAdapter(),
    "kilocode": CloudAPIAdapter(),
    "sd-cpp": StableDiffusionCppAdapter(),
    "rknn-sd": RknnSdAdapter(),
}
```

- [ ] **Step 4: Add `openrouter` and `kilocode` to `VALID_BACKEND_TYPES` in `config.py`**

Change line 11 of `tinyagentos/config.py`:

```python
VALID_BACKEND_TYPES = {"rkllama", "ollama", "llama-cpp", "vllm", "exo", "mlx", "openai", "anthropic", "sd-cpp", "rknn-sd", "openrouter", "kilocode"}
```

- [ ] **Step 5: Remove `model` field from `ProviderCreate` in `routes/providers.py`**

Change the `ProviderCreate` class (lines 30–36):

```python
class ProviderCreate(BaseModel):
    name: str
    type: str
    url: str
    priority: int = 99
    api_key_secret: str | None = None
```

- [ ] **Step 6: Run all adapter tests to confirm they pass**

```bash
python3 -m pytest tests/test_backend_adapters.py -v
```
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add tinyagentos/backend_adapters.py tinyagentos/config.py tinyagentos/routes/providers.py tests/test_backend_adapters.py
git commit -m "feat(backend): CloudAPIAdapter for hosted APIs, add openrouter + kilocode types, remove model from ProviderCreate"
```

---

## Task 2: Frontend — guided wizard + remove model field

**Files:**
- Modify: `desktop/src/apps/ProvidersApp.tsx`

### Background

The current `ProviderForm` is a flat single-step modal. This task replaces it with a wizard for Add mode (edit mode goes straight to the config step). The wizard has these steps:

- `"category"` — three cards: Local / Cluster / Cloud
- `"cloud-pick"` — four cloud provider cards (OpenAI, Anthropic, OpenRouter, Kilo)
- `"cluster-info"` — informational only; no form fields
- `"config"` — the actual config form (cloud: read-only URL + name + API key; local: type dropdown + URL + priority)

The `model` field is removed entirely from `FormState`, `defaultFormState`, `handleSave`, and the JSX. The `ProviderType` union gains `"openrouter"` and `"kilocode"`.

### Constants to add / change (lines 14–30 of ProvidersApp.tsx)

```typescript
const CLOUD_TYPES = ["openai", "anthropic", "openrouter", "kilocode"] as const;
const LOCAL_TYPES = ["rkllama", "ollama", "llama-cpp", "vllm", "exo", "mlx"] as const;
type ProviderType = typeof CLOUD_TYPES[number] | typeof LOCAL_TYPES[number];

const DEFAULT_URLS: Partial<Record<ProviderType, string>> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  openrouter: "https://openrouter.ai/api/v1",
  kilocode: "https://api.kilo.ai/api/gateway",
  ollama: "http://localhost:11434",
  rkllama: "http://localhost:8080",
  "llama-cpp": "http://localhost:8080",
  vllm: "http://localhost:8000",
};

interface CloudProviderMeta {
  label: string;
  description: string;
  url: string;
  keyPlaceholder: string;
}

const CLOUD_PROVIDER_META: Record<string, CloudProviderMeta> = {
  openai: {
    label: "OpenAI",
    description: "GPT-4o, o1, and more",
    url: "https://api.openai.com/v1",
    keyPlaceholder: "sk-...",
  },
  anthropic: {
    label: "Anthropic",
    description: "Claude Sonnet, Opus, Haiku",
    url: "https://api.anthropic.com/v1",
    keyPlaceholder: "sk-ant-...",
  },
  openrouter: {
    label: "OpenRouter",
    description: "300+ models via one API",
    url: "https://openrouter.ai/api/v1",
    keyPlaceholder: "sk-or-...",
  },
  kilocode: {
    label: "Kilo",
    description: "500+ models, smart routing",
    url: "https://api.kilo.ai/api/gateway",
    keyPlaceholder: "kilo-...",
  },
};
```

### `FormState` — remove `model`

```typescript
interface FormState {
  name: string;
  type: ProviderType;
  url: string;
  apiKey: string;
  priority: string;
}
```

### `defaultFormState` — remove `model`

```typescript
function defaultFormState(editingProvider?: Provider | null): FormState {
  if (editingProvider) {
    return {
      name: editingProvider.name,
      type: editingProvider.type as ProviderType,
      url: editingProvider.url,
      apiKey: "",
      priority: String(editingProvider.priority ?? 99),
    };
  }
  return {
    name: "",
    type: "openai",
    url: DEFAULT_URLS.openai ?? "",
    apiKey: "",
    priority: "99",
  };
}
```

### Wizard state types

Add these type aliases near the top of `ProviderForm` (not exported):

```typescript
type WizardCategory = "local" | "cluster" | "cloud";
type WizardStep = "category" | "cloud-pick" | "cluster-info" | "config";
```

### `handleSave` — remove model from payload

In the `handleSave` function, remove the `model` line from the payload. The full corrected payload block:

```typescript
const payload: Record<string, unknown> = {
  name: form.name.trim(),
  type: form.type,
  url: form.url.trim(),
  priority: parseInt(form.priority) || 99,
};
if (apiKeySecret) payload.api_key_secret = apiKeySecret;
```

### Complete rewritten `ProviderForm`

Replace the entire `ProviderForm` function (lines 215–517) with:

```typescript
function ProviderForm({
  editing,
  onSave,
  onClose,
}: {
  editing: Provider | null;
  onSave: () => void;
  onClose: () => void;
}) {
  type WizardCategory = "local" | "cluster" | "cloud";
  type WizardStep = "category" | "cloud-pick" | "cluster-info" | "config";

  const isMobile = useIsMobile();
  const isEdit = !!editing;

  const [step, setStep] = useState<WizardStep>(isEdit ? "config" : "category");
  const [category, setCategory] = useState<WizardCategory | null>(null);
  const [form, setForm] = useState<FormState>(() => defaultFormState(editing));
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [forceEnabled, setForceEnabled] = useState(false);

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setTestResult(null);
    setForceEnabled(false);
  }

  function handleTypeChange(t: ProviderType) {
    setForm((prev) => ({ ...prev, type: t, url: DEFAULT_URLS[t] ?? prev.url }));
    setTestResult(null);
    setForceEnabled(false);
  }

  function pickCloudProvider(type: string) {
    const meta = CLOUD_PROVIDER_META[type];
    if (!meta) return;
    setForm((prev) => ({
      ...prev,
      type: type as ProviderType,
      url: meta.url,
      name: prev.name || type,
    }));
    setTestResult(null);
    setForceEnabled(false);
    setStep("config");
  }

  function handleBack() {
    if (step === "config" && category === "cloud") { setStep("cloud-pick"); return; }
    if (step === "config" && category === "local") { setStep("category"); return; }
    if (step === "cloud-pick") { setStep("category"); return; }
    if (step === "cluster-info") { setStep("category"); return; }
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
      } catch { /* continue even if secret save fails */ }
    }

    try {
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        type: form.type,
        url: form.url.trim(),
        priority: parseInt(form.priority) || 99,
      };
      if (apiKeySecret) payload.api_key_secret = apiKeySecret;

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
        try { const err = await res.json(); if (err?.error) msg = String(err.error); } catch { /* ignore */ }
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
  const cloudMeta = CLOUD_PROVIDER_META[form.type];

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
              {step !== "category" && !isEdit && (
                <button
                  onClick={handleBack}
                  className="text-shell-text-tertiary hover:text-shell-text mr-1"
                  aria-label="Go back"
                >
                  ←
                </button>
              )}
              <Cloud size={16} className="text-accent" />
              <h2 className="text-sm font-semibold">
                {isEdit ? "Edit Provider"
                  : step === "category" ? "Add Provider"
                  : step === "cloud-pick" ? "Choose Cloud Provider"
                  : step === "cluster-info" ? "Add Cluster Worker"
                  : "Configure Provider"}
              </h2>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close form" className="h-7 w-7">
              <X size={16} />
            </Button>
          </div>

          {/* Step: category picker */}
          {step === "category" && (
            <div className="grid grid-cols-3 gap-3" role="group" aria-label="Provider category">
              {(["local", "cluster", "cloud"] as WizardCategory[]).map((cat) => {
                const meta: Record<WizardCategory, { icon: string; label: string; desc: string }> = {
                  local: { icon: "🖥️", label: "Local", desc: "On-device AI" },
                  cluster: { icon: "🌐", label: "Cluster", desc: "Linked workers" },
                  cloud: { icon: "☁️", label: "Cloud", desc: "Hosted APIs" },
                };
                const m = meta[cat];
                return (
                  <button
                    key={cat}
                    onClick={() => {
                      setCategory(cat);
                      if (cat === "cloud") setStep("cloud-pick");
                      else if (cat === "cluster") setStep("cluster-info");
                      else { setForm((p) => ({ ...p, type: "rkllama", url: DEFAULT_URLS.rkllama ?? "" })); setStep("config"); }
                    }}
                    className="flex flex-col items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 p-4 hover:bg-white/10 hover:border-accent/40 transition-colors text-center"
                    aria-label={`${m.label}: ${m.desc}`}
                  >
                    <span className="text-2xl" aria-hidden="true">{m.icon}</span>
                    <span className="text-[12px] font-semibold text-shell-text">{m.label}</span>
                    <span className="text-[10px] text-shell-text-tertiary">{m.desc}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Step: cloud provider picker */}
          {step === "cloud-pick" && (
            <div className="grid grid-cols-2 gap-3" role="group" aria-label="Cloud provider">
              {Object.entries(CLOUD_PROVIDER_META).map(([type, meta]) => (
                <button
                  key={type}
                  onClick={() => pickCloudProvider(type)}
                  className="flex flex-col items-start gap-1 rounded-xl border border-white/10 bg-white/5 p-3.5 hover:bg-white/10 hover:border-accent/40 transition-colors text-left"
                  aria-label={`${meta.label}: ${meta.description}`}
                >
                  <span className="text-[13px] font-semibold text-shell-text">{meta.label}</span>
                  <span className="text-[10px] text-shell-text-tertiary">{meta.description}</span>
                </button>
              ))}
            </div>
          )}

          {/* Step: cluster info */}
          {step === "cluster-info" && (
            <div className="space-y-3">
              <p className="text-[12px] text-shell-text-secondary leading-relaxed">
                Cluster workers auto-register when the taOS worker agent is installed and running on a remote machine. No manual entry needed — workers appear automatically in the Network section once connected.
              </p>
              <div className="rounded-lg bg-black/30 border border-white/10 p-3">
                <p className="text-[10px] text-shell-text-tertiary mb-1.5 uppercase tracking-wide">Install worker agent</p>
                <code className="text-[11px] text-shell-text font-mono block">
                  curl -fsSL https://get.tinyagentos.com/worker | bash
                </code>
              </div>
              <p className="text-[10px] text-shell-text-tertiary">
                Point the worker at this controller's address and it will appear here within a few seconds.
              </p>
              <Button variant="secondary" onClick={onClose} className="w-full">Close</Button>
            </div>
          )}

          {/* Step: config form */}
          {step === "config" && (
            <>
              {/* Name */}
              <div className="space-y-1.5">
                <Label htmlFor="prov-name">Name</Label>
                <Input
                  id="prov-name"
                  type="text"
                  value={form.name}
                  onChange={(e) => setField("name", e.target.value)}
                  placeholder={cloudMeta ? cloudMeta.label.toLowerCase() : "my-provider"}
                  disabled={isEdit}
                  autoFocus={!isEdit}
                />
              </div>

              {/* Cloud: read-only URL chip */}
              {category === "cloud" && cloudMeta && !isEdit && (
                <div className="space-y-1.5">
                  <Label>API Endpoint</Label>
                  <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
                    <ExternalLink size={11} className="text-shell-text-tertiary shrink-0" />
                    <code className="text-[11px] text-shell-text-tertiary font-mono truncate">{cloudMeta.url}</code>
                  </div>
                </div>
              )}

              {/* Local: type + URL */}
              {(category === "local" || isEdit) && !cloudMeta && (
                <>
                  {!isEdit && (
                    <div className="space-y-1.5">
                      <Label htmlFor="prov-type">Type</Label>
                      <select
                        id="prov-type"
                        value={form.type}
                        onChange={(e) => handleTypeChange(e.target.value as ProviderType)}
                        className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20"
                      >
                        {LOCAL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                  )}
                  <div className="space-y-1.5">
                    <Label htmlFor="prov-url">URL</Label>
                    <Input
                      id="prov-url"
                      type="url"
                      value={form.url}
                      onChange={(e) => setField("url", e.target.value)}
                      placeholder="http://localhost:8080"
                    />
                  </div>
                </>
              )}

              {/* Edit mode: show URL for any type */}
              {isEdit && (
                <div className="space-y-1.5">
                  <Label htmlFor="prov-url">URL</Label>
                  <Input
                    id="prov-url"
                    type="url"
                    value={form.url}
                    onChange={(e) => setField("url", e.target.value)}
                    placeholder="http://localhost:8080"
                  />
                </div>
              )}

              {/* API Key (cloud only) */}
              {(isCloud(form.type)) && (
                <div className="space-y-1.5">
                  <Label htmlFor="prov-apikey">
                    API Key{isEdit && " (leave blank to keep existing)"}
                  </Label>
                  <Input
                    id="prov-apikey"
                    type="password"
                    value={form.apiKey}
                    onChange={(e) => setField("apiKey", e.target.value)}
                    placeholder={isEdit ? "••••••••" : (cloudMeta?.keyPlaceholder ?? "sk-...")}
                    className="font-mono"
                  />
                  <p className="text-[10px] text-shell-text-tertiary">
                    Saved as <code>provider-{form.name || "{name}"}-key</code>
                  </p>
                </div>
              )}

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
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 1: Update constants — `CLOUD_TYPES`, `LOCAL_TYPES`, `DEFAULT_URLS`, add `CloudProviderMeta` + `CLOUD_PROVIDER_META`**

Replace lines 19–30 in `desktop/src/apps/ProvidersApp.tsx` with the constants block from the Background section above.

- [ ] **Step 2: Update `FormState` — remove `model` field**

Replace the `interface FormState` block (lines ~90–97).

- [ ] **Step 3: Update `defaultFormState` — remove `model`**

Replace `defaultFormState` (lines ~190–209).

- [ ] **Step 4: Replace entire `ProviderForm` function with the wizard version**

Replace lines 215–517 with the complete `ProviderForm` from the Background section above.

Note: the edit flow (isEdit = true) skips to `"config"` step directly. The `category` state remains `null` for edits. In config step rendering, local fields are shown when `category === "local" || isEdit` and no cloudMeta. Cloud fields are shown when `isCloud(form.type)` is true.

- [ ] **Step 5: Build to confirm no TypeScript errors**

```bash
cd desktop && npm run build 2>&1 | tail -8
```
Expected: `✓ built in X.XXs` with no errors.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/apps/ProvidersApp.tsx static/desktop/
git commit -m "feat(ui): guided add-provider wizard — category/cloud-pick/cluster-info/config steps; openrouter + kilo; remove model field"
```

---

## Task 3: Deploy and verify

**Files:** None (on-device work)

- [ ] **Step 1: Push branch**

```bash
git push origin feat/guided-add-provider
```

- [ ] **Step 2: Pull and restart on Pi**

```bash
# SSH: jay@192.168.6.123 (password: alexander04)
cd /home/jay/tinyagentos && git pull origin feat/guided-add-provider && sudo systemctl restart tinyagentos
```

- [ ] **Step 3: Verify wizard flow in browser**

Open the Providers app. Click "Add Provider". Confirm:
1. Category cards appear: Local, Cluster, Cloud
2. Clicking Cloud shows OpenAI, Anthropic, OpenRouter, Kilo cards
3. Picking Kilo pre-fills name="kilocode", URL="https://api.kilo.ai/api/gateway"
4. API key field uses placeholder "kilo-..."
5. No model field anywhere
6. Test connection → result shows online/error
7. Cluster info shows install command text, no form

- [ ] **Step 4: Merge PR to master**

```bash
gh pr create --title "feat: guided add-provider wizard, OpenRouter + Kilo support" --body "..."
gh pr merge --merge --delete-branch
```
