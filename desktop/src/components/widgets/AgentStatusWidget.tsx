import { useState, useEffect } from "react";

interface Agent {
  name: string;
  status: string;
}

export function AgentStatusWidget() {
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchAgents() {
      try {
        const res = await fetch("/api/agents");
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();
        if (!cancelled) {
          const list = Array.isArray(data) ? data : data.agents ?? [];
          setAgents(
            list.map((a: Record<string, unknown>) => ({
              name: (a.name as string) ?? (a.id as string) ?? "Unknown",
              status: (a.status as string) ?? "unknown",
            })),
          );
        }
      } catch {
        if (!cancelled) setError(true);
      }
    }

    fetchAgents();
    const interval = setInterval(fetchAgents, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const dotColor = (status: string) => {
    if (status === "online" || status === "running") return "#4ade80";
    if (status === "offline" || status === "stopped") return "#f87171";
    return "#fbbf24";
  };

  return (
    <div style={{ padding: "8px 4px", height: "100%", overflow: "auto" }}>
      <div style={{ fontSize: "0.7rem", fontWeight: 600, color: "rgba(255,255,255,0.5)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
        Agents
      </div>
      {error || !agents ? (
        <div style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.4)" }}>
          {error ? "No agents configured" : "Loading..."}
        </div>
      ) : agents.length === 0 ? (
        <div style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.4)" }}>
          No agents configured
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {agents.map((agent) => (
            <div key={agent.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.8rem", color: "#fff" }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  backgroundColor: dotColor(agent.status),
                  flexShrink: 0,
                }}
              />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {agent.name}
              </span>
              <span style={{ marginLeft: "auto", fontSize: "0.65rem", color: "rgba(255,255,255,0.4)" }}>
                {agent.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
