import { useState, useEffect, useRef, useCallback } from "react";
import { Bot, Plus, Trash2, ScrollText, Play, Server, X, ChevronRight, ChevronLeft, Check, Wrench, MessageSquare, PauseCircle, RotateCcw } from "lucide-react";
import { AgentSkillsPanel } from "./AgentSkillsPanel";
import { AgentMessagesPanel } from "./AgentMessagesPanel";
import {
  fetchClusterWorkers,
  workersToAggregated,
  HOST_BADGE_CLASS,
  CLOUD_PROVIDER_TYPES,
} from "@/lib/models";
import { availableKvQuantOptions, type KvQuantOptions } from "@/lib/cluster";
import {
  Button,
  Card,
  Input,
  Label,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import { ModelPickerFlow, type AgentModel } from "@/components/ModelPickerFlow";
import { ModelPickerModal } from "@/components/ModelPickerModal";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Agent {
  name: string;
  display_name?: string;
  host: string;
  color: string;
  status: "running" | "stopped" | "error" | "deploying";
  vectors: number;
  framework?: string;
  paused?: boolean;
  on_worker_failure?: "pause" | "fallback" | "escalate-immediately";
  fallback_models?: string[];
  kv_cache_quant_k?: string;
  kv_cache_quant_v?: string;
  kv_cache_quant_boundary_layers?: number;
}

interface Framework {
  id: string;
  name: string;
  description: string;
  verification_status: "tested" | "beta" | "experimental" | "broken";
}

// AgentModel is defined and exported from ModelPickerFlow
type Model = AgentModel;

/* ------------------------------------------------------------------ */
/*  Fallback data                                                      */
/* ------------------------------------------------------------------ */


const COLORS = [
  "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b",
  "#10b981", "#ef4444", "#06b6d4", "#f97316",
];

const STATUS_STYLES: Record<string, string> = {
  running: "bg-emerald-500/20 text-emerald-400",
  stopped: "bg-zinc-500/20 text-zinc-400",
  error: "bg-red-500/20 text-red-400",
  deploying: "bg-amber-500/20 text-amber-400",
};

/* ------------------------------------------------------------------ */
/*  AgentRow                                                           */
/* ------------------------------------------------------------------ */

function AgentRow({
  agent,
  onViewLogs,
  onViewSkills,
  onViewMessages,
  onDelete,
  onResume,
}: {
  agent: Agent;
  onViewLogs: (name: string) => void;
  onViewSkills: (name: string) => void;
  onViewMessages: (name: string) => void;
  onDelete: (name: string) => void;
  onResume: (name: string) => void;
}) {
  return (
    <Card className="flex items-center gap-4 px-4 py-3 hover:bg-shell-surface/50 transition-colors">
      <div className="flex items-center gap-2.5 flex-1 min-w-0">
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ backgroundColor: agent.color }}
          aria-label={`Color: ${agent.color}`}
        />
        <span className="font-medium text-sm truncate">{agent.display_name || agent.name}</span>
        {agent.paused && (
          <span
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/20 text-amber-400 border border-amber-500/20"
            title="This agent is paused due to a worker failure"
          >
            <PauseCircle size={10} aria-hidden="true" />
            paused
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5 text-sm text-shell-text-secondary min-w-0">
        <Server size={13} className="text-shell-text-tertiary" />
        <span className="truncate">{agent.host}</span>
      </div>
      <span
        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_STYLES[agent.status] ?? STATUS_STYLES.stopped}`}
        aria-label={`Status: ${agent.status}`}
      >
        {agent.status}
      </span>
      <span className="text-sm text-shell-text-secondary tabular-nums w-20 text-right">
        {agent.vectors.toLocaleString()}
      </span>
      <div className="flex items-center gap-1">
        {agent.paused && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 hover:bg-emerald-500/15 hover:text-emerald-400 text-amber-400"
            onClick={() => onResume(agent.name)}
            aria-label={`Resume ${agent.name}`}
            title="Resume agent"
          >
            <RotateCcw size={15} />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => onViewLogs(agent.name)}
          aria-label={`View logs for ${agent.name}`}
          title="View Logs"
        >
          <ScrollText size={15} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => onViewSkills(agent.name)}
          aria-label={`Manage skills for ${agent.name}`}
          title="Skills"
        >
          <Wrench size={15} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => onViewMessages(agent.name)}
          aria-label={`View messages for ${agent.name}`}
          title="Messages"
        >
          <MessageSquare size={15} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 hover:bg-red-500/15 hover:text-red-400"
          onClick={() => onDelete(agent.name)}
          aria-label={`Delete ${agent.name}`}
          title="Delete"
        >
          <Trash2 size={15} />
        </Button>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  AgentDetailPanel (Logs + Skills tabs)                              */
/* ------------------------------------------------------------------ */

type DetailTab = "logs" | "skills" | "messages";

function AgentDetailPanel({
  agent,
  initialTab,
  onClose,
}: {
  agent: Agent;
  initialTab: DetailTab;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<DetailTab>(initialTab);
  const [logs, setLogs] = useState<string>("Fetching logs...");
  const scrollRef = useRef<HTMLPreElement>(null);
  const agentName = agent.name;

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/agents/${encodeURIComponent(agentName)}/logs?lines=100`,
        { headers: { Accept: "application/json" } }
      );
      if (!res.ok) {
        setLogs(`[${new Date().toLocaleTimeString()}] Log fetch failed (${res.status}) for ${agentName}.`);
        return;
      }
      const data = await res.json();
      const logText = typeof data?.logs === "string"
        ? data.logs
        : Array.isArray(data?.logs)
          ? data.logs.join("\n")
          : JSON.stringify(data);
      setLogs(logText || `[${new Date().toLocaleTimeString()}] No logs available for ${agentName}.`);
    } catch {
      setLogs(`[${new Date().toLocaleTimeString()}] Unable to reach log endpoint for ${agentName}.\n[${new Date().toLocaleTimeString()}] Agent may not be running or the API is unavailable.`);
    }
  }, [agentName]);

  useEffect(() => {
    if (tab !== "logs") return;
    fetchLogs();
    const interval = setInterval(fetchLogs, 10_000);
    return () => clearInterval(interval);
  }, [fetchLogs, tab]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <Tabs
      value={tab}
      onValueChange={(v) => setTab(v as DetailTab)}
      className="border-t border-white/5 bg-shell-bg-deep flex flex-col"
      style={{ height: "22rem" }}
    >
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-sm">
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: agent.color }}
              aria-hidden
            />
            <span className="font-medium">{agentName}</span>
          </div>
          <TabsList aria-label="Agent detail tabs">
            <TabsTrigger value="logs">
              <ScrollText size={13} className="mr-1.5" />
              Logs
            </TabsTrigger>
            <TabsTrigger value="skills">
              <Wrench size={13} className="mr-1.5" />
              Skills
            </TabsTrigger>
            <TabsTrigger value="messages">
              <MessageSquare size={13} className="mr-1.5" />
              Messages
            </TabsTrigger>
          </TabsList>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onClose}
          aria-label="Close detail panel"
        >
          <X size={14} />
        </Button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        <TabsContent value="logs" className="h-full mt-0">
          <pre
            ref={scrollRef}
            className="h-full overflow-auto p-4 text-xs font-mono text-shell-text-secondary leading-relaxed whitespace-pre-wrap"
          >
            {logs}
          </pre>
        </TabsContent>
        <TabsContent value="skills" className="h-full mt-0">
          <AgentSkillsPanel
            agentId={agent.name}
            framework={agent.framework || "smolagents"}
          />
        </TabsContent>
        <TabsContent value="messages" className="h-full mt-0">
          <AgentMessagesPanel agentName={agent.name} />
        </TabsContent>
      </div>
    </Tabs>
  );
}

/* ------------------------------------------------------------------ */
/*  DeployWizard                                                       */
/* ------------------------------------------------------------------ */

function DeployWizard({
  open,
  onClose,
}: {
  open: boolean;
  onClose: (deployed?: boolean) => void;
}) {
  const [step, setStep] = useState(0);

  // Step 1
  const [name, setName] = useState("");
  const [color, setColor] = useState(COLORS[0]);

  // Step 2
  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [selectedFramework, setSelectedFramework] = useState<string>("");
  const [showExperimental, setShowExperimental] = useState(false);

  // Step 3
  const [models, setModels] = useState<Model[]>([]);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>("");

  // Advanced (no wizard step — defaults to unlimited)
  const [memory, setMemory] = useState("");
  const [cpus, setCpus] = useState("");

  // Step 3 — Permissions
  const [canReadUserMemory, setCanReadUserMemory] = useState(false);

  // Step 4 — Worker failure policy
  const [onWorkerFailure, setOnWorkerFailure] = useState<"pause" | "fallback" | "escalate-immediately">("pause");
  const [fallbackModels, setFallbackModels] = useState<string[]>([]);
  const [fallbackModelOpen, setFallbackModelOpen] = useState(false);

  // KV cache quantization — split K / V / boundary controls.  Visible only
  // when the cluster advertises more than fp16 for the respective axis.
  // Fetched once when the wizard opens from /api/cluster/kv-quant-options.
  const [kvQuantOptions, setKvQuantOptions] = useState<KvQuantOptions>({
    k: ["fp16"],
    v: ["fp16"],
    boundary: false,
    flat: ["fp16"],
  });
  const [kvCacheQuantK, setKvCacheQuantK] = useState<string>("fp16");
  const [kvCacheQuantV, setKvCacheQuantV] = useState<string>("fp16");
  const [kvCacheQuantBoundaryLayers, setKvCacheQuantBoundaryLayers] = useState<number>(0);

  const [deploying, setDeploying] = useState(false);

  const [deployError, setDeployError] = useState<string | null>(null);

  // Try to fetch real data
  useEffect(() => {
    if (!open) return;
    (async () => {
      try {
        const res = await fetch("/api/frameworks", {
          headers: { Accept: "application/json" },
        });
        const ct = res.headers.get("content-type") ?? "";
        if (res.ok && ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            // Filter out broken adapters entirely
            const visible = data.filter(
              (a: Record<string, unknown>) => a.verification_status !== "broken"
            );
            setFrameworks(
              visible.map((a: Record<string, unknown>) => ({
                id: String(a.id),
                name: String(a.name ?? a.id),
                description: String(a.description ?? ""),
                verification_status: (a.verification_status as Framework["verification_status"]) ?? "experimental",
              }))
            );
          }
        }
      } catch { /* leave frameworks empty, wizard will show nothing selectable */ }
    })();
    // Fetch cluster-wide KV quant options.  The K/V/boundary controls only
    // render when the cluster reports more than fp16 for the relevant axis,
    // so this is a no-op on single-worker fp16-only clusters.
    (async () => {
      try {
        const res = await fetch("/api/cluster/kv-quant-options", {
          headers: { Accept: "application/json" },
        });
        const ct = res.headers.get("content-type") ?? "";
        if (res.ok && ct.includes("application/json")) {
          const data = await res.json();
          // Accept the new K/V/boundary shape.  Fall back to the legacy
          // flat "options" field if the controller hasn't upgraded yet.
          const k: string[] = Array.isArray(data?.k) && data.k.length > 0
            ? data.k
            : Array.isArray(data?.options) && data.options.length > 0
              ? data.options
              : ["fp16"];
          const v: string[] = Array.isArray(data?.v) && data.v.length > 0
            ? data.v
            : Array.isArray(data?.options) && data.options.length > 0
              ? data.options
              : ["fp16"];
          const boundary = Boolean(data?.boundary_layer_protect);
          const flatSet = new Set([...k, ...v]);
          setKvQuantOptions({
            k,
            v,
            boundary,
            flat: Array.from(flatSet).sort(),
          });
        }
      } catch {
        // Fall back to computing from the workers fetch below.
        // If that also fails we stay on the fp16-only default and no
        // controls are shown.
      }
    })();

    (async () => {
      const localModels: Model[] = [];
      try {
        const res = await fetch("/api/models", {
          headers: { Accept: "application/json" },
        });
        const ct = res.headers.get("content-type") ?? "";
        if (res.ok && ct.includes("application/json")) {
          const data = await res.json();
          // /api/models returns { models: [...], downloaded_files: [...] }
          const list: Record<string, unknown>[] = Array.isArray(data)
            ? data
            : Array.isArray(data?.models)
              ? data.models
              : [];
          // Only include models the user has actually downloaded.
          const downloaded = list.filter((m) => m.has_downloaded_variant === true);
          localModels.push(
            ...downloaded.map((m) => ({
              id: String(m.id),
              name: String(m.name ?? m.id),
              host: "controller",
              hostKind: "controller" as const,
            }))
          );
        }
      } catch { /* leave local models empty */ }

      // Union in cluster-worker-hosted models. Each worker reports its
      // backends[].models[] via heartbeat; any of them is a valid deploy
      // target as far as the wizard is concerned — the user can pick it
      // and the controller-side scheduler/copy will route accordingly.
      const workerModels: Model[] = [];
      try {
        const workers = await fetchClusterWorkers();
        for (const a of workersToAggregated(workers)) {
          workerModels.push({
            id: a.id,
            name: a.name,
            host: a.host,
            hostKind: "worker",
          });
        }
        // Fall back: if the dedicated kv-quant-options fetch above already
        // found K or V options beyond fp16, leave those results.  Otherwise
        // compute from the workers we just fetched so we avoid a second
        // round-trip.
        setKvQuantOptions((prev) => {
          if (prev.k.length > 1 || prev.v.length > 1 || prev.boundary) return prev;
          return availableKvQuantOptions(workers);
        });
      } catch { /* ignore */ }

      // Also fetch cloud provider models
      const cloudModels: Model[] = [];
      try {
        const res = await fetch("/api/providers", {
          headers: { Accept: "application/json" },
        });
        const ct = res.headers.get("content-type") ?? "";
        if (res.ok && ct.includes("application/json")) {
          const providers = await res.json();
          for (const p of (Array.isArray(providers) ? providers : [])) {
            if (!(CLOUD_PROVIDER_TYPES as readonly string[]).includes(p.type)) continue;
            const pModels: { id?: string; name?: string }[] = Array.isArray(p.models) ? p.models : [];
            if (pModels.length === 0) {
              cloudModels.push({
                id: p.model ?? "default",
                name: `${p.name} default`,
                host: p.name,
                hostKind: "cloud",
              });
            } else {
              for (const m of pModels) {
                const modelId = m.id ?? m.name ?? "unknown";
                cloudModels.push({
                  id: modelId,
                  name: `${m.name ?? modelId} (${p.name})`,
                  host: p.name,
                  hostKind: "cloud",
                });
              }
            }
          }
        }
      } catch { /* ignore */ }

      // Dedupe: if the controller and a worker both report the same model id,
      // prefer the controller entry. Worker entries with duplicate (host,id)
      // pairs (e.g. same model under two backends) are kept once per worker.
      const seen = new Set<string>();
      const union: Model[] = [];
      for (const m of [...localModels, ...workerModels, ...cloudModels]) {
        const key = `${m.hostKind ?? "?"}:${m.host ?? "?"}:${m.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        union.push(m);
      }
      setModels(union);
      setModelsLoaded(true);
    })();
  }, [open]);

  // Reset when opened
  useEffect(() => {
    if (open) {
      setStep(0);
      setName("");
      setColor(COLORS[0]);
      setSelectedFramework("");
      setShowExperimental(false);
      setSelectedModel("");
      setModels([]);
      setModelsLoaded(false);
      setMemory("");
      setCpus("");
      setCanReadUserMemory(false);
      setOnWorkerFailure("pause");
      setFallbackModels([]);
      setKvQuantOptions({ k: ["fp16"], v: ["fp16"], boundary: false, flat: ["fp16"] });
      setKvCacheQuantK("fp16");
      setKvCacheQuantV("fp16");
      setKvCacheQuantBoundaryLayers(0);
      setDeploying(false);
      setDeployError(null);
    }
  }, [open]);

  // Derive default policy heuristic: if fallback models are configured use
  // "fallback", otherwise "pause".
  useEffect(() => {
    if (fallbackModels.length > 0 && onWorkerFailure === "pause") {
      setOnWorkerFailure("fallback");
    }
  }, [fallbackModels, onWorkerFailure]);

  if (!open) return null;

  const STEPS = ["Name & Color", "Framework", "Model", "Permissions", "Failure Policy", "Review"];

  const canNext = () => {
    if (step === 0) return name.trim().length > 0;
    if (step === 1) return selectedFramework.length > 0;
    if (step === 2) return selectedModel.length > 0;
    return true;
  };

  const totalSteps = STEPS.length;
  const reviewStep = totalSteps - 1;

  async function handleDeploy() {
    setDeploying(true);
    setDeployError(null);
    try {
      const memMb = memory ? parseInt(memory, 10) : null;
      const memoryLimit = memMb === null ? null : memMb >= 1024 ? `${Math.round(memMb / 1024)}GB` : `${memMb}MB`;
      const res = await fetch("/api/agents/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          framework: selectedFramework,
          model: selectedModel,
          color,
          memory_limit: memoryLimit,
          cpu_limit: cpus ? parseInt(cpus, 10) : null,
          can_read_user_memory: canReadUserMemory,
          on_worker_failure: onWorkerFailure,
          fallback_models: fallbackModels,
          kv_cache_quant_k: kvCacheQuantK,
          kv_cache_quant_v: kvCacheQuantV,
          kv_cache_quant_boundary_layers: kvCacheQuantBoundaryLayers,
        }),
      });
      if (!res.ok) {
        let msg = `Deploy failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.error) msg = String(err.error);
        } catch { /* ignore */ }
        setDeployError(msg);
        setDeploying(false);
        return;
      }
      onClose(true);
    } catch (e) {
      setDeployError(e instanceof Error ? e.message : "Network error");
      setDeploying(false);
    }
  }

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      style={{
        paddingTop: "calc(1rem + env(safe-area-inset-top, 0px))",
        paddingBottom: "calc(1rem + env(safe-area-inset-bottom, 0px))",
      }}
      onClick={() => onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Deploy Agent"
    >
      <div
        className="w-full max-w-lg max-h-full min-h-0 bg-shell-surface rounded-xl border border-white/10 shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/5 shrink-0">
          <div className="flex items-center gap-2">
            <Play size={16} className="text-accent" />
            <h2 className="text-sm font-semibold">Deploy Agent</h2>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => onClose()}
            aria-label="Close wizard"
          >
            <X size={16} />
          </Button>
        </div>

        {/* Step indicators */}
        <div className="flex items-center gap-1 px-5 py-3 border-b border-white/5 shrink-0 overflow-x-auto">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-1">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium transition-colors ${
                  i < step
                    ? "bg-accent/20 text-accent"
                    : i === step
                      ? "bg-accent text-white"
                      : "bg-white/5 text-shell-text-tertiary"
                }`}
              >
                {i < step ? <Check size={12} /> : i + 1}
              </div>
              <span
                className={`text-[11px] hidden sm:inline ${
                  i === step ? "text-shell-text" : "text-shell-text-tertiary"
                }`}
              >
                {label}
              </span>
              {i < STEPS.length - 1 && (
                <div className="w-4 h-px bg-white/10 mx-0.5" />
              )}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="px-5 py-5 flex-1 min-h-0 overflow-y-auto">
          {/* Step 0: Name + Color */}
          {step === 0 && (
            <Card className="p-0 border-0 bg-transparent shadow-none space-y-4">
              <div>
                <Label htmlFor="agent-name" className="mb-1.5 block">
                  Agent Name
                </Label>
                <Input
                  id="agent-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="my-agent"
                  autoFocus
                />
              </div>
              <div>
                <Label className="mb-1.5 block">Color</Label>
                <div className="flex gap-2" role="radiogroup" aria-label="Agent color">
                  {COLORS.map((c) => (
                    <button
                      key={c}
                      onClick={() => setColor(c)}
                      className={`w-7 h-7 rounded-full border-2 transition-all ${
                        color === c ? "border-white scale-110" : "border-transparent"
                      }`}
                      style={{ backgroundColor: c }}
                      role="radio"
                      aria-checked={color === c}
                      aria-label={c}
                    />
                  ))}
                </div>
              </div>
            </Card>
          )}

          {/* Step 1: Framework */}
          {step === 1 && (
            <div className="space-y-2">
              <span className="block text-xs text-shell-text-secondary mb-2">Select Framework</span>
              {frameworks
                .filter((fw) => fw.verification_status !== "experimental" || showExperimental)
                .map((fw) => {
                  const isExperimental = fw.verification_status === "experimental";
                  const selectable = !isExperimental || showExperimental;
                  return (
                    <button
                      key={fw.id}
                      onClick={() => selectable ? setSelectedFramework(fw.id) : undefined}
                      disabled={!selectable}
                      aria-disabled={!selectable}
                      className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                        !selectable
                          ? "border-white/5 bg-shell-bg-deep opacity-40 cursor-not-allowed"
                          : selectedFramework === fw.id
                            ? "border-accent bg-accent/10"
                            : "border-white/5 bg-shell-bg-deep hover:bg-white/5"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-medium ${isExperimental ? "text-shell-text-tertiary" : ""}`}>
                          {fw.name}
                        </span>
                        {fw.verification_status === "beta" && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/20 text-amber-400 leading-none">
                            beta
                          </span>
                        )}
                        {fw.verification_status === "experimental" && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-zinc-500/20 text-zinc-400 leading-none">
                            experimental
                          </span>
                        )}
                      </div>
                      <div className={`text-xs mt-0.5 ${isExperimental ? "text-shell-text-tertiary" : "text-shell-text-secondary"}`}>
                        {fw.description}
                      </div>
                    </button>
                  );
                })}
              {/* Experimental toggle */}
              <label
                htmlFor="show-experimental-frameworks"
                className="flex items-center gap-2 mt-3 cursor-pointer select-none"
              >
                <input
                  id="show-experimental-frameworks"
                  type="checkbox"
                  checked={showExperimental}
                  onChange={(e) => {
                    setShowExperimental(e.target.checked);
                    // Deselect if currently selected framework becomes hidden
                    if (!e.target.checked) {
                      const fw = frameworks.find((f) => f.id === selectedFramework);
                      if (fw?.verification_status === "experimental") setSelectedFramework("");
                    }
                  }}
                  className="accent-accent"
                />
                <span className="text-xs text-shell-text-secondary">Show experimental frameworks</span>
              </label>
            </div>
          )}

          {/* Step 2: Model */}
          {step === 2 && (
            <div className="space-y-2">
              {selectedModel ? (
                /* Summary card — shown after a model is picked */
                <div>
                  <span className="block text-xs text-shell-text-secondary mb-2">Selected Model</span>
                  <div className="px-4 py-3 rounded-lg border border-accent/30 bg-accent/5 flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <div className="text-sm font-medium truncate">
                          {models.find(m => m.id === selectedModel)?.name ?? selectedModel}
                        </div>
                        {(() => {
                          const m = models.find(mo => mo.id === selectedModel);
                          return m?.host && m.hostKind !== "controller" ? (
                            <span className={HOST_BADGE_CLASS}>{m.host}</span>
                          ) : null;
                        })()}
                      </div>
                      <div className="text-xs text-shell-text-tertiary mt-0.5">{selectedModel}</div>
                    </div>
                    <button
                      onClick={() => setSelectedModel("")}
                      className="text-xs text-shell-text-tertiary hover:text-shell-text shrink-0 mt-0.5 transition-colors"
                    >
                      Change
                    </button>
                  </div>
                </div>
              ) : (
                /* Tiered picker — source → provider → list */
                <ModelPickerFlow
                  models={models}
                  modelsLoaded={modelsLoaded}
                  onSelect={(id) => setSelectedModel(id)}
                  onBack={() => setStep(1)}
                />
              )}
            </div>
          )}

          {/* Step 3: Permissions */}
          {step === 3 && (
            <div className="space-y-4">
              <span className="block text-xs text-shell-text-secondary mb-2">Permissions</span>
              <label
                htmlFor="agent-user-memory"
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  canReadUserMemory
                    ? "border-accent bg-accent/10"
                    : "border-white/5 bg-shell-bg-deep hover:bg-white/5"
                }`}
              >
                <input
                  id="agent-user-memory"
                  type="checkbox"
                  checked={canReadUserMemory}
                  onChange={(e) => setCanReadUserMemory(e.target.checked)}
                  className="mt-0.5 accent-accent"
                  aria-describedby="agent-user-memory-desc"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium">Allow this agent to read your memory</div>
                  <div
                    id="agent-user-memory-desc"
                    className="text-xs text-shell-text-secondary mt-0.5"
                  >
                    Agents with this permission can search your notes, conversations, and files. Read-only access.
                  </div>
                </div>
              </label>
            </div>
          )}

          {/* Step 4: Failure Policy */}
          {step === 4 && (
            <div className="space-y-4">
              <span className="block text-xs text-shell-text-secondary mb-2">Worker Failure Policy</span>
              <div>
                <Label htmlFor="agent-failure-policy" className="mb-1.5 block">
                  On worker failure
                </Label>
                <select
                  id="agent-failure-policy"
                  value={onWorkerFailure}
                  onChange={(e) => setOnWorkerFailure(e.target.value as typeof onWorkerFailure)}
                  className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                  aria-describedby="agent-failure-policy-desc"
                >
                  <option value="pause">Pause (wait for human to intervene)</option>
                  <option value="fallback">Fallback (try alternate models before pausing)</option>
                  <option value="escalate-immediately">Escalate immediately (notify at first sign of trouble)</option>
                </select>
                <p id="agent-failure-policy-desc" className="mt-1 text-xs text-shell-text-tertiary">
                  {onWorkerFailure === "pause" && "Retries briefly, then pauses and notifies you."}
                  {onWorkerFailure === "fallback" && "Retries, falls back to alternate models, then pauses if all fail."}
                  {onWorkerFailure === "escalate-immediately" && "Notifies you as soon as the first retry fails."}
                </p>
              </div>
              <div>
                <Label className="mb-1.5 block">
                  Fallback models{" "}
                  <span className="font-normal text-shell-text-tertiary">(optional, in priority order)</span>
                </Label>
                <div className="space-y-1.5">
                  {fallbackModels.filter(Boolean).map((m, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-white/5 bg-shell-bg-deep">
                      <span className="flex-1 text-sm truncate">
                        {models.find(mo => mo.id === m)?.name ?? m}
                      </span>
                      <button
                        onClick={() => setFallbackModels(prev => prev.filter((_, j) => j !== i))}
                        className="text-shell-text-tertiary hover:text-red-400 transition-colors"
                        aria-label={`Remove fallback model ${i + 1}`}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                  {modelsLoaded && models.filter(mo => mo.id !== selectedModel && !fallbackModels.includes(mo.id)).length > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setFallbackModelOpen(true)}
                      className="w-full"
                    >
                      <Plus size={13} />
                      Add fallback model
                    </Button>
                  )}
                </div>
                <ModelPickerModal
                  open={fallbackModelOpen}
                  onClose={() => setFallbackModelOpen(false)}
                  models={models.filter(mo => mo.id !== selectedModel && !fallbackModels.includes(mo.id))}
                  modelsLoaded={modelsLoaded}
                  title="Add Fallback Model"
                  onSelect={(id) => setFallbackModels(prev => [...prev, id])}
                />
              </div>
              {/* KV cache quant — split K / V / boundary controls.
                  Each sub-control is only rendered when its axis has more than
                  the fp16 baseline. If the cluster has no TurboQuant-capable
                  workers, this whole section is absent from the DOM. */}
              {(kvQuantOptions.k.length > 1 || kvQuantOptions.v.length > 1 || kvQuantOptions.boundary) && (
                <div className="space-y-3">
                  {kvQuantOptions.k.length > 1 && (
                    <div>
                      <Label htmlFor="agent-kv-quant-k" className="mb-1.5 block">
                        K cache bits
                      </Label>
                      <select
                        id="agent-kv-quant-k"
                        value={kvCacheQuantK}
                        onChange={(e) => setKvCacheQuantK(e.target.value)}
                        className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                        aria-describedby="agent-kv-quant-k-desc"
                      >
                        {kvQuantOptions.k.map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                      <p id="agent-kv-quant-k-desc" className="mt-1 text-xs text-shell-text-tertiary">
                        Quantization for the key cache (-ctk). fp16 is the default.
                      </p>
                    </div>
                  )}
                  {kvQuantOptions.v.length > 1 && (
                    <div>
                      <Label htmlFor="agent-kv-quant-v" className="mb-1.5 block">
                        V cache bits
                      </Label>
                      <select
                        id="agent-kv-quant-v"
                        value={kvCacheQuantV}
                        onChange={(e) => setKvCacheQuantV(e.target.value)}
                        className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                        aria-describedby="agent-kv-quant-v-desc"
                      >
                        {kvQuantOptions.v.map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                      <p id="agent-kv-quant-v-desc" className="mt-1 text-xs text-shell-text-tertiary">
                        Quantization for the value cache (-ctv). fp16 is the default.
                      </p>
                    </div>
                  )}
                  {kvQuantOptions.boundary && (
                    <div>
                      <Label htmlFor="agent-kv-boundary-layers" className="mb-1.5 block">
                        Boundary layers
                      </Label>
                      <input
                        id="agent-kv-boundary-layers"
                        type="number"
                        min={0}
                        max={4}
                        step={1}
                        value={kvCacheQuantBoundaryLayers}
                        onChange={(e) => {
                          const v = Math.max(0, Math.min(4, parseInt(e.target.value, 10) || 0));
                          setKvCacheQuantBoundaryLayers(v);
                        }}
                        className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                        aria-describedby="agent-kv-boundary-layers-desc"
                      />
                      <p id="agent-kv-boundary-layers-desc" className="mt-1 text-xs text-shell-text-tertiary">
                        Number of leading transformer layers kept in fp16 regardless of KV quant setting. Range 0-4.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Step 5: Review */}
          {step === 5 && (
            <div className="space-y-3">
              <span className="block text-xs text-shell-text-secondary mb-2">Review Configuration</span>
              <div className="rounded-lg bg-shell-bg-deep border border-white/5 divide-y divide-white/5">
                {[
                  ["Name", name],
                  ["Color", color],
                  ["Framework", frameworks.find((f) => f.id === selectedFramework)?.name ?? selectedFramework],
                  ["Model", models.find((m) => m.id === selectedModel)?.name ?? selectedModel],
                  ["Memory", `${memory} MB`],
                  ["CPUs", `${cpus} Core${cpus !== "1" ? "s" : ""}`],
                  ["User Memory", canReadUserMemory ? "Allowed (read-only)" : "Denied"],
                  ["On failure", onWorkerFailure],
                  ["Fallbacks", fallbackModels.filter(Boolean).join(", ") || "none"],
                  // Only include KV quant rows in the review when the cluster
                  // actually offered a choice — avoids surfacing fp16-only
                  // entries that would confuse users who never saw the controls.
                  ...(kvQuantOptions.k.length > 1 ? [["K cache bits", kvCacheQuantK]] : []),
                  ...(kvQuantOptions.v.length > 1 ? [["V cache bits", kvCacheQuantV]] : []),
                  ...(kvQuantOptions.boundary ? [["Boundary layers", String(kvCacheQuantBoundaryLayers)]] : []),
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-xs text-shell-text-secondary">{label}</span>
                    <span className="text-sm font-medium flex items-center gap-1.5">
                      {label === "Color" && (
                        <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: value }} />
                      )}
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Error */}
        {deployError && (
          <div
            role="alert"
            className="mx-5 mb-3 px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300"
          >
            {deployError}
          </div>
        )}

        {/* Footer — hidden while the inline model picker is active (has its own nav) */}
        {!(step === 2 && !selectedModel) && (
        <div className="flex items-center justify-between px-5 py-3 border-t border-white/5 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => (step === 0 ? onClose() : setStep(step - 1))}
          >
            <ChevronLeft size={14} />
            {step === 0 ? "Cancel" : "Back"}
          </Button>

          {step < reviewStep ? (
            <Button
              size="sm"
              onClick={() => setStep(step + 1)}
              disabled={!canNext()}
            >
              Next
              <ChevronRight size={14} />
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={handleDeploy}
              disabled={deploying}
              className="bg-emerald-600 hover:bg-emerald-500 text-white"
            >
              <Play size={13} />
              {deploying ? "Deploying..." : "Deploy Agent"}
            </Button>
          )}
        </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  AgentsApp (main)                                                   */
/* ------------------------------------------------------------------ */

export function AgentsApp({ windowId: _windowId }: { windowId: string }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [detail, setDetail] = useState<{ name: string; tab: DetailTab } | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch("/api/agents");
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data)) {
            setAgents(
              data.map((a: Record<string, unknown>) => ({
                name: String(a.name ?? "unknown"),
                host: String(a.host ?? "localhost"),
                color: String(a.color ?? "#3b82f6"),
                status: String(a.status ?? "stopped") as Agent["status"],
                vectors: Number(a.vectors ?? 0),
                framework: a.framework ? String(a.framework) : undefined,
                paused: Boolean(a.paused),
                on_worker_failure: (a.on_worker_failure as Agent["on_worker_failure"]) ?? "pause",
                fallback_models: Array.isArray(a.fallback_models) ? (a.fallback_models as string[]) : [],
                kv_cache_quant_k: a.kv_cache_quant_k ? String(a.kv_cache_quant_k) : (a.kv_cache_quant ? String(a.kv_cache_quant) : "fp16"),
                kv_cache_quant_v: a.kv_cache_quant_v ? String(a.kv_cache_quant_v) : (a.kv_cache_quant ? String(a.kv_cache_quant) : "fp16"),
                kv_cache_quant_boundary_layers: typeof a.kv_cache_quant_boundary_layers === "number" ? a.kv_cache_quant_boundary_layers : 0,
              }))
            );
            setLoading(false);
            return;
          }
        }
      }
    } catch { /* fall through */ }
    setAgents([]);
    setLoading(false);
  }, []);

  // Listen for agent-resumed events from the notification toast
  useEffect(() => {
    const handler = () => fetchAgents();
    window.addEventListener("taos:agent-resumed", handler);
    return () => window.removeEventListener("taos:agent-resumed", handler);
  }, [fetchAgents]);

  async function handleResume(name: string) {
    try {
      const res = await fetch(`/api/agents/${encodeURIComponent(name)}/resume`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        let msg = `Resume failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.error) msg = String(err.error);
        } catch { /* ignore */ }
        window.alert(msg);
        return;
      }
      fetchAgents();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Network error");
    }
  }

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  async function handleDelete(name: string) {
    if (!window.confirm(`Delete agent "${name}"? This cannot be undone.`)) return;
    try {
      const res = await fetch(`/api/agents/${encodeURIComponent(name)}`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        let msg = `Delete failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.error) msg = String(err.error);
        } catch { /* ignore */ }
        window.alert(msg);
        return;
      }
      if (detail?.name === name) setDetail(null);
      fetchAgents();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Network error");
    }
  }

  function handleWizardClose(deployed?: boolean) {
    setWizardOpen(false);
    if (deployed) fetchAgents();
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden bg-shell-bg text-shell-text select-none relative">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Bot size={18} className="text-accent" />
          <h1 className="text-sm font-semibold">Agents</h1>
          <span className="text-xs text-shell-text-tertiary">
            {agents.length} deployed
          </span>
        </div>
        <Button
          onClick={() => setWizardOpen(true)}
          size="sm"
          className="text-white shadow-lg hover:shadow-xl hover:-translate-y-0.5 hover:brightness-110 border-0"
          style={{ background: "linear-gradient(135deg, #8b92a3, #5b6170)" }}
          aria-label="Deploy new agent"
        >
          <Plus size={14} />
          Deploy Agent
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
            Loading agents...
          </div>
        ) : agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-shell-text-tertiary">
            <div className="w-20 h-20 rounded-2xl flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, rgba(139,146,163,0.15), rgba(91,97,112,0.08))" }}
            >
              <Bot size={36} className="text-accent/50" />
            </div>
            <div className="text-center">
              <p className="text-base font-medium text-shell-text-secondary mb-1">No agents deployed yet</p>
              <p className="text-xs text-shell-text-tertiary max-w-xs">Deploy your first AI agent to start automating tasks on your device.</p>
            </div>
            <Button
              onClick={() => setWizardOpen(true)}
              className="text-white shadow-lg hover:shadow-xl hover:-translate-y-0.5 hover:brightness-110 border-0 mt-1"
              style={{ background: "linear-gradient(135deg, #8b92a3, #5b6170)" }}
            >
              <Plus size={15} />
              Deploy your first agent
            </Button>
          </div>
        ) : (
          <div className="p-4 space-y-2" role="list" aria-label="Agent list">
            {agents.map((agent) => (
              <AgentRow
                key={agent.name}
                agent={agent}
                onViewLogs={(name) => setDetail({ name, tab: "logs" })}
                onViewSkills={(name) => setDetail({ name, tab: "skills" })}
                onViewMessages={(name) => setDetail({ name, tab: "messages" })}
                onDelete={handleDelete}
                onResume={handleResume}
              />
            ))}
          </div>
        )}
      </div>

      {/* Detail panel (Logs + Skills tabs) */}
      {detail && (() => {
        const agent = agents.find((a) => a.name === detail.name);
        if (!agent) return null;
        return (
          <AgentDetailPanel
            agent={agent}
            initialTab={detail.tab}
            onClose={() => setDetail(null)}
          />
        );
      })()}

      {/* Deploy wizard overlay */}
      <DeployWizard open={wizardOpen} onClose={handleWizardClose} />
    </div>
  );
}

// TODO (#144): Cluster widget KV quant chip.
// Once a backend actually reports a type beyond fp16, add a small chip to the
// loaded-model row in ActivityApp's cluster widget showing the active KV
// quant mode.  The chip should be absent when the mode is fp16 (the default),
// visible for anything else.  The data is already in ClusterWorker
// kv_cache_quant_support and flows through to the model list in
// /api/cluster/backends.  No dead widget today — wait for a real reporter.

