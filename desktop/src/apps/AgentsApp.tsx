import { useState, useEffect, useRef, useCallback } from "react";
import { Bot, Plus, Trash2, ScrollText, Play, Server, X, ChevronRight, ChevronLeft, Check } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Agent {
  name: string;
  host: string;
  color: string;
  status: "running" | "stopped" | "error" | "deploying";
  vectors: number;
}

interface Framework {
  id: string;
  name: string;
  description: string;
}

interface Model {
  id: string;
  name: string;
}

/* ------------------------------------------------------------------ */
/*  Fallback data                                                      */
/* ------------------------------------------------------------------ */

const MOCK_AGENTS: Agent[] = [
  { name: "research-agent", host: "localhost", color: "#3b82f6", status: "running", vectors: 1284 },
  { name: "code-reviewer", host: "localhost", color: "#8b5cf6", status: "running", vectors: 562 },
  { name: "data-pipeline", host: "10.0.0.12", color: "#f59e0b", status: "stopped", vectors: 0 },
];

const MOCK_FRAMEWORKS: Framework[] = [
  { id: "langchain", name: "LangChain", description: "Build context-aware reasoning applications" },
  { id: "autogen", name: "AutoGen", description: "Multi-agent conversation framework" },
  { id: "crewai", name: "CrewAI", description: "Role-based autonomous AI agents" },
  { id: "custom", name: "Custom", description: "Bring your own agent framework" },
];

const MOCK_MODELS: Model[] = [
  { id: "qwen2.5-7b", name: "Qwen 2.5 7B" },
  { id: "llama3-8b", name: "Llama 3 8B" },
  { id: "mistral-7b", name: "Mistral 7B" },
  { id: "phi3-mini", name: "Phi-3 Mini" },
];

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
  onDelete,
}: {
  agent: Agent;
  onViewLogs: (name: string) => void;
  onDelete: (name: string) => void;
}) {
  return (
    <tr className="border-b border-white/5 hover:bg-shell-surface/50 transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: agent.color }}
            aria-label={`Color: ${agent.color}`}
          />
          <span className="font-medium text-sm">{agent.name}</span>
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-shell-text-secondary">
        <div className="flex items-center gap-1.5">
          <Server size={13} className="text-shell-text-tertiary" />
          {agent.host}
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_STYLES[agent.status] ?? STATUS_STYLES.stopped}`}
        >
          {agent.status}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-shell-text-secondary tabular-nums">
        {agent.vectors.toLocaleString()}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          <button
            onClick={() => onViewLogs(agent.name)}
            className="p-1.5 rounded-md hover:bg-shell-surface transition-colors text-shell-text-secondary hover:text-shell-text"
            aria-label={`View logs for ${agent.name}`}
            title="View Logs"
          >
            <ScrollText size={15} />
          </button>
          <button
            onClick={() => onDelete(agent.name)}
            className="p-1.5 rounded-md hover:bg-red-500/15 transition-colors text-shell-text-secondary hover:text-red-400"
            aria-label={`Delete ${agent.name}`}
            title="Delete"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </td>
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/*  LogsPanel                                                          */
/* ------------------------------------------------------------------ */

function LogsPanel({
  agentName,
  onClose,
}: {
  agentName: string;
  onClose: () => void;
}) {
  const [logs, setLogs] = useState<string>("Fetching logs...");
  const scrollRef = useRef<HTMLPreElement>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`/api/partials/agent-logs/${agentName}?lines=100`);
      const text = await res.text();
      // If it looks like HTML, show a placeholder
      if (text.trim().startsWith("<")) {
        setLogs(`[${new Date().toLocaleTimeString()}] Log stream connected for ${agentName}\n[${new Date().toLocaleTimeString()}] No structured log data available — endpoint returned HTML.`);
      } else {
        setLogs(text);
      }
    } catch {
      setLogs(`[${new Date().toLocaleTimeString()}] Unable to reach log endpoint for ${agentName}.\n[${new Date().toLocaleTimeString()}] Agent may not be running or the API is unavailable.`);
    }
  }, [agentName]);

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 10_000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="border-t border-white/5 bg-shell-bg-deep">
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/5">
        <div className="flex items-center gap-2 text-sm">
          <ScrollText size={14} className="text-shell-text-tertiary" />
          <span className="text-shell-text-secondary">Logs</span>
          <span className="text-shell-text-tertiary">&mdash;</span>
          <span className="font-medium">{agentName}</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md hover:bg-shell-surface transition-colors text-shell-text-secondary hover:text-shell-text"
          aria-label="Close logs panel"
        >
          <X size={14} />
        </button>
      </div>
      <pre
        ref={scrollRef}
        className="h-48 overflow-auto p-4 text-xs font-mono text-shell-text-secondary leading-relaxed whitespace-pre-wrap"
      >
        {logs}
      </pre>
    </div>
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
  const [frameworks, setFrameworks] = useState<Framework[]>(MOCK_FRAMEWORKS);
  const [selectedFramework, setSelectedFramework] = useState<string>("");

  // Step 3
  const [models, setModels] = useState<Model[]>(MOCK_MODELS);
  const [selectedModel, setSelectedModel] = useState<string>("");

  // Step 4
  const [memory, setMemory] = useState("512");
  const [cpus, setCpus] = useState("1");

  const [deploying, setDeploying] = useState(false);

  // Try to fetch real data
  useEffect(() => {
    if (!open) return;
    (async () => {
      try {
        const res = await fetch("/api/store/catalog?type=agent-framework");
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) setFrameworks(data);
        }
      } catch { /* use fallback */ }
    })();
    (async () => {
      try {
        const res = await fetch("/api/models");
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) setModels(data);
        }
      } catch { /* use fallback */ }
    })();
  }, [open]);

  // Reset when opened
  useEffect(() => {
    if (open) {
      setStep(0);
      setName("");
      setColor(COLORS[0]);
      setSelectedFramework("");
      setSelectedModel("");
      setMemory("512");
      setCpus("1");
      setDeploying(false);
    }
  }, [open]);

  if (!open) return null;

  const STEPS = ["Name & Color", "Framework", "Model", "Resources", "Review"];

  const canNext = () => {
    if (step === 0) return name.trim().length > 0;
    if (step === 1) return selectedFramework.length > 0;
    if (step === 2) return selectedModel.length > 0;
    return true;
  };

  async function handleDeploy() {
    setDeploying(true);
    try {
      await fetch("/api/agents/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          color,
          framework: selectedFramework,
          model: selectedModel,
          memory: parseInt(memory),
          cpus: parseInt(cpus),
        }),
      });
    } catch { /* ignore — deploy may not be wired */ }
    setTimeout(() => onClose(true), 600);
  }

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={() => onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Deploy Agent"
    >
      <div
        className="w-full max-w-lg bg-shell-surface rounded-xl border border-white/10 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Play size={16} className="text-accent" />
            <h2 className="text-sm font-semibold">Deploy Agent</h2>
          </div>
          <button
            onClick={() => onClose()}
            className="p-1 rounded-md hover:bg-white/5 text-shell-text-secondary hover:text-shell-text transition-colors"
            aria-label="Close wizard"
          >
            <X size={16} />
          </button>
        </div>

        {/* Step indicators */}
        <div className="flex items-center gap-1 px-5 py-3 border-b border-white/5">
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
        <div className="px-5 py-5 min-h-[220px]">
          {/* Step 0: Name + Color */}
          {step === 0 && (
            <div className="space-y-4">
              <div>
                <label htmlFor="agent-name" className="block text-xs text-shell-text-secondary mb-1.5">
                  Agent Name
                </label>
                <input
                  id="agent-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="my-agent"
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                  autoFocus
                />
              </div>
              <div>
                <span className="block text-xs text-shell-text-secondary mb-1.5">Color</span>
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
            </div>
          )}

          {/* Step 1: Framework */}
          {step === 1 && (
            <div className="space-y-2">
              <span className="block text-xs text-shell-text-secondary mb-2">Select Framework</span>
              {frameworks.map((fw) => (
                <button
                  key={fw.id}
                  onClick={() => setSelectedFramework(fw.id)}
                  className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                    selectedFramework === fw.id
                      ? "border-accent bg-accent/10"
                      : "border-white/5 bg-shell-bg-deep hover:bg-white/5"
                  }`}
                >
                  <div className="text-sm font-medium">{fw.name}</div>
                  <div className="text-xs text-shell-text-secondary mt-0.5">{fw.description}</div>
                </button>
              ))}
            </div>
          )}

          {/* Step 2: Model */}
          {step === 2 && (
            <div className="space-y-2">
              <span className="block text-xs text-shell-text-secondary mb-2">Select Model</span>
              {models.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setSelectedModel(m.id)}
                  className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                    selectedModel === m.id
                      ? "border-accent bg-accent/10"
                      : "border-white/5 bg-shell-bg-deep hover:bg-white/5"
                  }`}
                >
                  <div className="text-sm font-medium">{m.name}</div>
                  <div className="text-xs text-shell-text-tertiary">{m.id}</div>
                </button>
              ))}
            </div>
          )}

          {/* Step 3: Resources */}
          {step === 3 && (
            <div className="space-y-4">
              <div>
                <label htmlFor="agent-memory" className="block text-xs text-shell-text-secondary mb-1.5">
                  Memory
                </label>
                <select
                  id="agent-memory"
                  value={memory}
                  onChange={(e) => setMemory(e.target.value)}
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value="256">256 MB</option>
                  <option value="512">512 MB</option>
                  <option value="1024">1 GB</option>
                  <option value="2048">2 GB</option>
                  <option value="4096">4 GB</option>
                </select>
              </div>
              <div>
                <label htmlFor="agent-cpus" className="block text-xs text-shell-text-secondary mb-1.5">
                  CPU Cores
                </label>
                <select
                  id="agent-cpus"
                  value={cpus}
                  onChange={(e) => setCpus(e.target.value)}
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value="1">1 Core</option>
                  <option value="2">2 Cores</option>
                  <option value="4">4 Cores</option>
                </select>
              </div>
            </div>
          )}

          {/* Step 4: Review */}
          {step === 4 && (
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

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-white/5">
          <button
            onClick={() => (step === 0 ? onClose() : setStep(step - 1))}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm text-shell-text-secondary hover:bg-white/5 transition-colors"
          >
            <ChevronLeft size={14} />
            {step === 0 ? "Cancel" : "Back"}
          </button>

          {step < 4 ? (
            <button
              onClick={() => setStep(step + 1)}
              disabled={!canNext()}
              className="flex items-center gap-1 px-4 py-1.5 rounded-lg text-sm font-medium bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next
              <ChevronRight size={14} />
            </button>
          ) : (
            <button
              onClick={handleDeploy}
              disabled={deploying}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-60 transition-colors"
            >
              <Play size={13} />
              {deploying ? "Deploying..." : "Deploy Agent"}
            </button>
          )}
        </div>
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
  const [logsAgent, setLogsAgent] = useState<string | null>(null);

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
              }))
            );
            setLoading(false);
            return;
          }
        }
      }
    } catch { /* fall through */ }
    // Fallback to mock data
    setAgents(MOCK_AGENTS);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  function handleDelete(name: string) {
    setAgents((prev) => prev.filter((a) => a.name !== name));
    if (logsAgent === name) setLogsAgent(null);
  }

  function handleWizardClose(deployed?: boolean) {
    setWizardOpen(false);
    if (deployed) fetchAgents();
  }

  return (
    <div className="flex flex-col h-full bg-shell-bg text-shell-text select-none relative">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Bot size={18} className="text-accent" />
          <h1 className="text-sm font-semibold">Agents</h1>
          <span className="text-xs text-shell-text-tertiary">
            {agents.length} deployed
          </span>
        </div>
        <button
          onClick={() => setWizardOpen(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all duration-200"
          style={{ background: "linear-gradient(135deg, #667eea, #764ba2)" }}
          aria-label="Deploy new agent"
        >
          <Plus size={14} />
          Deploy Agent
        </button>
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
              style={{ background: "linear-gradient(135deg, rgba(102,126,234,0.15), rgba(118,75,162,0.08))" }}
            >
              <Bot size={36} className="text-accent/50" />
            </div>
            <div className="text-center">
              <p className="text-base font-medium text-shell-text-secondary mb-1">No agents deployed yet</p>
              <p className="text-xs text-shell-text-tertiary max-w-xs">Deploy your first AI agent to start automating tasks on your device.</p>
            </div>
            <button
              onClick={() => setWizardOpen(true)}
              className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-semibold text-white shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all duration-200 mt-1"
              style={{ background: "linear-gradient(135deg, #667eea, #764ba2)" }}
            >
              <Plus size={15} />
              Deploy your first agent
            </button>
          </div>
        ) : (
          <table className="w-full text-left" aria-label="Agent list">
            <thead>
              <tr className="border-b border-white/5 text-[11px] uppercase tracking-wider text-shell-text-tertiary">
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Host</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Vectors</th>
                <th className="px-4 py-2.5 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <AgentRow
                  key={agent.name}
                  agent={agent}
                  onViewLogs={setLogsAgent}
                  onDelete={handleDelete}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Logs panel */}
      {logsAgent && (
        <LogsPanel agentName={logsAgent} onClose={() => setLogsAgent(null)} />
      )}

      {/* Deploy wizard overlay */}
      <DeployWizard open={wizardOpen} onClose={handleWizardClose} />
    </div>
  );
}
