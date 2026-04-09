import { useEffect, useState, useCallback } from "react";
import { Activity, Server, Bot, Database, RefreshCw } from "lucide-react";
import type { ComponentType } from "react";

interface Agent {
  name: string;
  status: string;
  host?: string;
  model?: string;
}

interface KpiCard {
  label: string;
  value: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  color: string;
}

const REFRESH_INTERVAL = 30_000;

export function DashboardApp({ windowId: _windowId }: { windowId: string }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/agents", {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const contentType = res.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          const data = await res.json();
          const list: Agent[] = Array.isArray(data)
            ? data
            : data.agents ?? data.items ?? [];
          setAgents(list);
          setError(null);
        } else {
          // endpoint returned HTML or other non-JSON
          setAgents([]);
          setError(null);
        }
      } else if (res.status === 404) {
        setAgents([]);
        setError(null);
      } else {
        setError(`API returned ${res.status}`);
      }
    } catch {
      setError("Could not reach backend");
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchData]);

  const onlineCount = agents.filter(
    (a) => a.status === "online" || a.status === "running",
  ).length;

  const kpis: KpiCard[] = [
    {
      label: "Agents Online",
      value: agents.length > 0 ? `${onlineCount}` : "\u2014",
      icon: Bot,
      color: "text-emerald-400",
    },
    {
      label: "Total Agents",
      value: agents.length > 0 ? `${agents.length}` : "\u2014",
      icon: Server,
      color: "text-sky-400",
    },
    {
      label: "Models",
      value: "\u2014", // TODO: fetch /api/models
      icon: Database,
      color: "text-violet-400",
    },
    {
      label: "System Uptime",
      value: "\u2014", // TODO: fetch /api/settings/system-info
      icon: Activity,
      color: "text-amber-400",
    },
  ];

  return (
    <div className="flex flex-col h-full bg-shell-bg-deep text-shell-text select-none overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/5">
        <h1 className="text-lg font-semibold tracking-tight">Dashboard</h1>
        <button
          onClick={fetchData}
          aria-label="Refresh dashboard"
          className="p-1.5 rounded-lg hover:bg-shell-surface transition-colors text-shell-text-secondary hover:text-shell-text"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
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
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {kpis.map((kpi) => (
              <div
                key={kpi.label}
                className="flex items-center gap-3 p-4 rounded-xl bg-shell-surface/60 border border-white/5"
              >
                <div
                  className={`p-2 rounded-lg bg-white/5 ${kpi.color}`}
                >
                  <kpi.icon size={20} />
                </div>
                <div>
                  <p className="text-xs text-shell-text-tertiary">
                    {kpi.label}
                  </p>
                  <p className="text-xl font-semibold tabular-nums">
                    {loading ? "\u2026" : kpi.value}
                  </p>
                </div>
              </div>
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
              No agent data available. The backend may not expose a JSON API yet.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {agents.map((agent) => {
                const isOnline =
                  agent.status === "online" || agent.status === "running";
                return (
                  <div
                    key={agent.name}
                    className="flex items-start gap-3 p-3.5 rounded-xl bg-shell-surface/60 border border-white/5"
                  >
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
                        {agent.status}
                        {agent.host ? ` \u00b7 ${agent.host}` : ""}
                      </p>
                    </div>
                  </div>
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

        {/* System Info Placeholder */}
        <section aria-label="System information">
          <h2 className="text-sm font-medium text-shell-text-secondary mb-3">
            System
          </h2>
          <div className="p-6 rounded-xl bg-shell-surface/40 border border-white/5 text-center">
            <Server
              size={28}
              className="mx-auto mb-2 text-shell-text-tertiary"
            />
            <p className="text-sm text-shell-text-tertiary">
              System information &mdash; coming soon
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
