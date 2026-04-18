import { useEffect, useState } from "react";

interface PersonaTabProps {
  agent: {
    name: string;
    soul_md?: string;
    agent_md?: string;
    source_persona_id?: string | null;
  };
  onUpdated: () => void;
}

export function PersonaTab({ agent, onUpdated }: PersonaTabProps) {
  const [soul, setSoul] = useState(agent.soul_md ?? "");
  const [agentMd, setAgentMd] = useState(agent.agent_md ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSoul(agent.soul_md ?? "");
    setAgentMd(agent.agent_md ?? "");
  }, [agent.name]);

  const save = async () => {
    setSaving(true);
    await fetch(`/api/agents/${agent.name}/persona`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ soul_md: soul, agent_md: agentMd }),
    });
    setSaving(false);
    onUpdated();
  };

  const sourceLabel = agent.source_persona_id
    ? `From: ${agent.source_persona_id}`
    : soul || agentMd
      ? "Custom"
      : "Blank";

  return (
    <div className="h-full overflow-auto p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase opacity-60">{sourceLabel}</span>
        {/* Swap button added in Task 8.2 */}
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase opacity-60">Soul</span>
        <textarea
          value={soul}
          onChange={(e) => setSoul(e.target.value)}
          rows={10}
          className="border border-white/10 rounded bg-shell-bg px-2 py-1 font-mono text-xs text-shell-text-secondary resize-none focus:outline-none focus:ring-1 focus:ring-white/20"
          aria-label="Agent soul (identity)"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs uppercase opacity-60">Agent.md — operational rules</span>
        <textarea
          value={agentMd}
          onChange={(e) => setAgentMd(e.target.value)}
          rows={8}
          className="border border-white/10 rounded bg-shell-bg px-2 py-1 font-mono text-xs text-shell-text-secondary resize-none focus:outline-none focus:ring-1 focus:ring-white/20"
          aria-label="Agent operational rules"
        />
      </label>
      <button
        disabled={saving}
        onClick={save}
        className="self-end bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-3 py-1.5 rounded text-sm text-white transition-colors"
      >
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
