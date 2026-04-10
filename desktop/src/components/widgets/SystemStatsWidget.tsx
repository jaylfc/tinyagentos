import { useState, useEffect } from "react";

interface Stats {
  cpu: number;
  ram: number;
}

function barColor(v: number): string {
  if (v >= 80) return "#f87171";
  if (v >= 50) return "#fbbf24";
  return "#4ade80";
}

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "0.75rem",
          color: "rgba(255,255,255,0.7)",
        }}
      >
        <span>{label}</span>
        <span>{Math.round(value)}%</span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 3,
          background: "rgba(255,255,255,0.1)",
          overflow: "hidden",
        }}
        role="progressbar"
        aria-label={`${label} usage`}
        aria-valuenow={Math.round(value)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.min(100, Math.max(0, value))}%`,
            borderRadius: 3,
            background: barColor(value),
            transition: "width 0.3s ease, background 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}

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

export function SystemStatsWidget() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      // Prefer /api/system (returns instantaneous cpu/ram).
      const sys = await fetchJson<{
        resources?: { cpu_percent?: number; ram_percent?: number };
      }>("/api/system");

      if (sys?.resources) {
        if (cancelled) return;
        setStats({
          cpu: sys.resources.cpu_percent ?? 0,
          ram: sys.resources.ram_percent ?? 0,
        });
        setError(false);
        return;
      }

      // Fallback: time-series metrics.
      const [cpuSeries, ramSeries] = await Promise.all([
        fetchJson<Array<{ value: number }>>(
          "/api/metrics/system.cpu_pct?range=1h",
        ),
        fetchJson<Array<{ value: number }>>(
          "/api/metrics/system.ram_pct?range=1h",
        ),
      ]);

      if (cancelled) return;
      const cpu =
        Array.isArray(cpuSeries) && cpuSeries.length > 0
          ? cpuSeries[cpuSeries.length - 1].value
          : null;
      const ram =
        Array.isArray(ramSeries) && ramSeries.length > 0
          ? ramSeries[ramSeries.length - 1].value
          : null;

      if (cpu === null && ram === null) {
        setError(true);
        return;
      }
      setStats({ cpu: cpu ?? 0, ram: ram ?? 0 });
      setError(false);
    }

    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div
      style={{
        padding: "8px 4px",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 10,
      }}
    >
      <div
        style={{
          fontSize: "0.7rem",
          fontWeight: 600,
          color: "rgba(255,255,255,0.5)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
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
