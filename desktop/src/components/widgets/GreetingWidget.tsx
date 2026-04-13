import { useState, useEffect } from "react";

function getGreeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning.";
  if (hour >= 12 && hour < 17) return "Good afternoon.";
  if (hour >= 17 && hour < 21) return "Good evening.";
  return "Good night.";
}

function getGreetingEmoji(hour: number): string {
  if (hour >= 5 && hour < 12) return "☀️";
  if (hour >= 12 && hour < 17) return "🌤";
  if (hour >= 17 && hour < 21) return "🌅";
  return "🌙";
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
  const [now, setNow] = useState(() => new Date());
  const [summary, setSummary] = useState<SystemSummary | null>(null);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    fetchSummary().then(setSummary);
    const timer = setInterval(() => fetchSummary().then(setSummary), 30_000);
    return () => clearInterval(timer);
  }, []);

  const hour = now.getHours();
  const greeting = getGreeting(hour);
  const emoji = getGreetingEmoji(hour);

  const subtitleParts: string[] = [];
  if (summary !== null) {
    if (summary.agentCount > 0) subtitleParts.push(`${summary.agentCount} agent${summary.agentCount !== 1 ? "s" : ""} running`);
    if (summary.taskCount > 0) subtitleParts.push(`${summary.taskCount} task${summary.taskCount !== 1 ? "s" : ""} queued`);
  }
  const subtitleText = subtitleParts.length > 0 ? subtitleParts.join(" · ") : "All systems operational";

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px 16px 20px",
      gap: 8,
    }}>
      <span style={{ fontSize: 36, lineHeight: 1 }}>{emoji}</span>
      <span style={{
        fontSize: 28,
        fontWeight: 700,
        color: "rgba(255,255,255,0.95)",
        lineHeight: 1.2,
        textAlign: "center",
        letterSpacing: "-0.5px",
      }}>
        {greeting}
      </span>
      <span style={{
        fontSize: 13,
        color: "rgba(255,255,255,0.45)",
        textAlign: "center",
      }}>
        {subtitleText}
      </span>
    </div>
  );
}
