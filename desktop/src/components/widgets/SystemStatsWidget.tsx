import { useState, useEffect } from "react";

interface Stats {
  cpu: number;
  ram: number;
}

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "rgba(255,255,255,0.7)" }}>
        <span>{label}</span>
        <span>{Math.round(value)}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: "rgba(255,255,255,0.1)", overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${Math.min(100, Math.max(0, value))}%`,
            borderRadius: 3,
            background: value > 80 ? "#f87171" : value > 60 ? "#fbbf24" : "#4ade80",
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}

export function SystemStatsWidget() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      try {
        let res = await fetch("/api/metrics");
        if (!res.ok) res = await fetch("/api/dashboard");
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();
        if (!cancelled) {
          setStats({
            cpu: data.cpu_percent ?? data.cpu ?? data.cpuPercent ?? 0,
            ram: data.memory_percent ?? data.ram ?? data.memoryPercent ?? 0,
          });
        }
      } catch {
        if (!cancelled) setError(true);
      }
    }

    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div style={{ padding: "8px 4px", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", gap: 10 }}>
      <div style={{ fontSize: "0.7rem", fontWeight: 600, color: "rgba(255,255,255,0.5)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        System
      </div>
      {error || !stats ? (
        <div style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.4)" }}>
          {error ? "Stats unavailable" : "Loading..."}
        </div>
      ) : (
        <>
          <Bar label="CPU" value={stats.cpu} />
          <Bar label="RAM" value={stats.ram} />
        </>
      )}
    </div>
  );
}
