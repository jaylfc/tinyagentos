import { useEffect, useState, useCallback } from "react";
import { Activity, Server, Bot, Cpu, MemoryStick, HeartPulse, RefreshCw } from "lucide-react";
import type { ComponentType } from "react";
import { Button, Card, CardContent } from "@/components/ui";

interface Agent {
  name: string;
  status?: string;
  host?: string;
  model?: string;
}

interface Backend {
  name?: string;
  status?: string;
  healthy?: boolean;
}

interface KpiCard {
  label: string;
  value: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  color: string;
  gradient: string;
  sub?: string;
}

const REFRESH_INTERVAL = 15_000;

type HealthTone = "green" | "yellow" | "red" | "unknown";

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("application/json")) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function DashboardApp({ windowId: _windowId }: { windowId: string }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [backends, setBackends] = useState<Backend[]>([]);
  const [cpuPct, setCpuPct] = useState<number | null>(null);
  const [ramPct, setRamPct] = useState<number | null>(null);
  const [health, setHealth] = useState<HealthTone>("unknown");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = useCallback(async () => {
    const [agentsData, backendsData, systemData, healthData] = await Promise.all([
      fetchJson<Agent[] | { agents?: Agent[]; items?: Agent[] }>("/api/agents"),
      fetchJson<{ backends?: Backend[] }>("/api/backends"),
      fetchJson<{ resources?: { cpu_percent?: number; ram_percent?: number } }>("/api/system"),
      fetchJson<{ status?: string; agents?: number; backends?: number }>("/api/health"),
    ]);

    if (agentsData) {
      const list: Agent[] = Array.isArray(agentsData)
        ? agentsData
        : agentsData.agents ?? agentsData.items ?? [];
      setAgents(list);
    } else {
      setAgents([]);
    }

    if (backendsData && Array.isArray(backendsData.backends)) {
      setBackends(backendsData.backends);
    } else {
      setBackends([]);
    }

    if (systemData?.resources) {
      if (typeof systemData.resources.cpu_percent === "number")
        setCpuPct(systemData.resources.cpu_percent);
      if (typeof systemData.resources.ram_percent === "number")
        setRamPct(systemData.resources.ram_percent);
    } else {
      // Fallback: try metrics endpoints for latest values.
      const [cpuSeries, ramSeries] = await Promise.all([
        fetchJson<Array<{ value: number }>>("/api/metrics/system.cpu_pct?range=1h"),
        fetchJson<Array<{ value: number }>>("/api/metrics/system.ram_pct?range=1h"),
      ]);
      if (Array.isArray(cpuSeries) && cpuSeries.length > 0) {
        setCpuPct(cpuSeries[cpuSeries.length - 1].value);
      }
      if (Array.isArray(ramSeries) && ramSeries.length > 0) {
        setRamPct(ramSeries[ramSeries.length - 1].value);
      }
    }

    if (healthData?.status) {
      const s = healthData.status.toLowerCase();
      if (s === "ok" || s === "healthy") setHealth("green");
      else if (s === "warning" || s === "degraded") setHealth("yellow");
      else setHealth("red");
    } else {
      setHealth("unknown");
    }

    if (!agentsData && !backendsData && !systemData && !healthData) {
      setError("Could not reach backend");
    } else {
      setError(null);
    }
    setLoading(false);
    setLastRefresh(new Date());
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchData]);

  const agentIsRunning = (a: Agent) => {
    const s = (a.status ?? "").toLowerCase();
    return s === "online" || s === "running" || s === "ok";
  };
  const activeAgents = agents.filter(agentIsRunning).length;

  const backendIsHealthy = (b: Backend) => {
    if (b.healthy === true) return true;
    const s = (b.status ?? "").toLowerCase();
    return s === "ok" || s === "online" || s === "healthy";
  };
  const backendsOnline = backends.filter(backendIsHealthy).length;

  const healthLabel: Record<HealthTone, string> = {
    green: "Healthy",
    yellow: "Degraded",
    red: "Unhealthy",
    unknown: "Unknown",
  };
  const healthColor: Record<HealthTone, string> = {
    green: "text-emerald-400",
    yellow: "text-amber-400",
    red: "text-red-400",
    unknown: "text-shell-text-tertiary",
  };
  const healthGradient: Record<HealthTone, string> = {
    green: "linear-gradient(135deg, rgba(16,185,129,0.12), rgba(16,185,129,0.04))",
    yellow: "linear-gradient(135deg, rgba(245,158,11,0.12), rgba(245,158,11,0.04))",
    red: "linear-gradient(135deg, rgba(239,68,68,0.12), rgba(239,68,68,0.04))",
    unknown: "linear-gradient(135deg, rgba(148,163,184,0.10), rgba(148,163,184,0.02))",
  };

  const fmtPct = (v: number | null) =>
    v === null || Number.isNaN(v) ? "\u2014" : `${Math.round(v)}%`;

  const kpis: KpiCard[] = [
    {
      label: "System Status",
      value: healthLabel[health],
      icon: HeartPulse,
      color: healthColor[health],
      gradient: healthGradient[health],
    },
    {
      label: "Active Agents",
      value: agents.length === 0 ? "\u2014" : `${activeAgents}`,
      sub: agents.length === 0 ? undefined : `of ${agents.length}`,
      icon: Bot,
      color: "text-emerald-400",
      gradient:
        "linear-gradient(135deg, rgba(16,185,129,0.12), rgba(16,185,129,0.04))",
    },
    {
      label: "Backends Online",
      value: backends.length === 0 ? "\u2014" : `${backendsOnline}`,
      sub: backends.length === 0 ? undefined : `of ${backends.length}`,
      icon: Server,
      color: "text-sky-400",
      gradient:
        "linear-gradient(135deg, rgba(56,189,248,0.12), rgba(56,189,248,0.04))",
    },
    {
      label: "CPU",
      value: fmtPct(cpuPct),
      icon: Cpu,
      color: "text-violet-400",
      gradient:
        "linear-gradient(135deg, rgba(139,92,246,0.12), rgba(139,92,246,0.04))",
    },
    {
      label: "RAM",
      value: fmtPct(ramPct),
      icon: MemoryStick,
      color: "text-amber-400",
      gradient:
        "linear-gradient(135deg, rgba(245,158,11,0.12), rgba(245,158,11,0.04))",
    },
  ];

  return (
    <div className="flex flex-col h-full bg-shell-bg-deep text-shell-text select-none overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/5">
        <h1 className="text-xl font-bold tracking-tight">Dashboard</h1>
        <Button
          variant="ghost"
          size="icon"
          onClick={fetchData}
          aria-label="Refresh dashboard"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-5 space-y-5">
        {/* Error banner */}
        {error && (
          <div
            role="alert"
            className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-sm"
          >
            {error}
          </div>
        )}

        {/* KPI Cards */}
        <section aria-label="Key metrics">
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {kpis.map((kpi) => (
              <Card
                key={kpi.label}
                className="hover:-translate-y-0.5 hover:shadow-xl transition-all duration-200"
                style={{ background: kpi.gradient }}
              >
                <CardContent className="flex items-center gap-4 p-5">
                  <div
                    className={`p-2.5 rounded-xl bg-white/[0.08] ${kpi.color}`}
                  >
                    <kpi.icon size={22} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-shell-text-tertiary mb-0.5">
                      {kpi.label}
                    </p>
                    <p className="text-2xl font-bold tabular-nums truncate">
                      {loading ? "\u2026" : kpi.value}
                    </p>
                    {kpi.sub && (
                      <p className="text-[10px] text-shell-text-tertiary tabular-nums">
                        {kpi.sub}
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Agent Status Grid */}
        <section aria-label="Agent status">
          <h2 className="text-sm font-medium text-shell-text-secondary mb-3">
            Agents
          </h2>
          {agents.length === 0 && !loading ? (
            <p className="text-sm text-shell-text-tertiary">
              No agents configured yet.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {agents.map((agent) => {
                const isOnline = agentIsRunning(agent);
                return (
                  <Card key={agent.name}>
                    <CardContent className="flex items-start gap-3 p-3.5">
                      <span
                        className={`mt-1 h-2.5 w-2.5 rounded-full shrink-0 ${
                          isOnline ? "bg-emerald-400" : "bg-shell-text-tertiary"
                        }`}
                        aria-label={isOnline ? "online" : "offline"}
                      />
                      <div className="min-w-0">
                        <p className="font-medium text-sm truncate">
                          {agent.name}
                        </p>
                        <p className="text-xs text-shell-text-tertiary truncate">
                          {agent.status ?? "unknown"}
                          {agent.host ? ` \u00b7 ${agent.host}` : ""}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </section>

        {/* Backends */}
        <section aria-label="Backends">
          <h2 className="text-sm font-medium text-shell-text-secondary mb-3">
            Backends
          </h2>
          {backends.length === 0 && !loading ? (
            <p className="text-sm text-shell-text-tertiary">
              No backends configured.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {backends.map((b, idx) => {
                const ok = backendIsHealthy(b);
                return (
                  <Card key={(b.name ?? "backend") + idx}>
                    <CardContent className="flex items-start gap-3 p-3.5">
                      <span
                        className={`mt-1 h-2.5 w-2.5 rounded-full shrink-0 ${
                          ok ? "bg-emerald-400" : "bg-red-400"
                        }`}
                        aria-label={ok ? "healthy" : "unhealthy"}
                      />
                      <div className="min-w-0">
                        <p className="font-medium text-sm truncate">
                          {b.name ?? "backend"}
                        </p>
                        <p className="text-xs text-shell-text-tertiary truncate">
                          {b.status ?? (ok ? "healthy" : "unhealthy")}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </section>

        {/* Activity Feed Placeholder */}
        <section aria-label="Activity feed">
          <h2 className="text-sm font-medium text-shell-text-secondary mb-3">
            Activity
          </h2>
          <div className="p-6 rounded-xl bg-shell-surface/40 border border-white/5 text-center">
            <Activity
              size={28}
              className="mx-auto mb-2 text-shell-text-tertiary"
            />
            <p className="text-sm text-shell-text-tertiary">
              Activity feed &mdash; coming soon
            </p>
          </div>
        </section>

        {/* Footer */}
        <p className="text-xs text-shell-text-tertiary text-right">
          Last refreshed {lastRefresh.toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
}
