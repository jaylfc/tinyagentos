import { useState, useEffect } from "react";

function getGreeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning.";
  if (hour >= 12 && hour < 17) return "Good afternoon.";
  if (hour >= 17 && hour < 21) return "Good evening.";
  return "Good night.";
}

interface SystemSummary {
  agentCount: number;
  taskCount: number;
}

async function fetchSummary(): Promise<SystemSummary | null> {
  try {
    const [agentsRes, jobsRes] = await Promise.all([
      fetch("/api/agents"),
      fetch("/api/jobs"),
    ]);

    if (!agentsRes.ok || !jobsRes.ok) return null;

    const agents = await agentsRes.json();
    const jobs = await jobsRes.json();

    const agentCount = Array.isArray(agents) ? agents.length : (agents?.count ?? 0);
    const taskCount = Array.isArray(jobs) ? jobs.length : (jobs?.count ?? 0);

    return { agentCount, taskCount };
  } catch {
    return null;
  }
}

export function GreetingWidget() {
  const [greeting, setGreeting] = useState(() => getGreeting(new Date().getHours()));
  const [summary, setSummary] = useState<SystemSummary | null>(null);

  useEffect(() => {
    const tick = () => setGreeting(getGreeting(new Date().getHours()));
    const greetingTimer = setInterval(tick, 60_000);
    return () => clearInterval(greetingTimer);
  }, []);

  useEffect(() => {
    fetchSummary().then(setSummary);
    const pollTimer = setInterval(() => {
      fetchSummary().then(setSummary);
    }, 30_000);
    return () => clearInterval(pollTimer);
  }, []);

  const subtitleText = summary !== null
    ? `${summary.agentCount} agent${summary.agentCount !== 1 ? "s" : ""} running · ${summary.taskCount} task${summary.taskCount !== 1 ? "s" : ""} queued`
    : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", justifyContent: "center", height: "100%", gap: 4 }}>
      <span style={{ fontSize: "22px", fontWeight: 600, color: "rgba(255,255,255,0.9)", lineHeight: 1.2 }}>
        {greeting}
      </span>
      {subtitleText !== null && (
        <span style={{ fontSize: "12px", color: "rgba(255,255,255,0.4)" }}>
          {subtitleText}
        </span>
      )}
    </div>
  );
}
