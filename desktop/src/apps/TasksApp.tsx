import { useState, useEffect, useCallback } from "react";
import { CalendarClock, Plus, Edit, Trash2, Play, Pause, X } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Task {
  id: string;
  name: string;
  agent: string;
  schedule: string;
  command: string;
  description: string;
  enabled: boolean;
  lastRun: string | null;
}

interface Preset {
  name: string;
  schedule: string;
  command: string;
  description: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const MOCK_AGENTS = ["research-agent", "code-reviewer", "data-pipeline"];

const PRESETS: Preset[] = [
  { name: "Daily Summary", schedule: "0 9 * * *", command: "summarize --last 24h", description: "Generate a daily summary every morning at 9 AM" },
  { name: "Hourly Sync", schedule: "0 * * * *", command: "sync --sources all", description: "Sync all data sources every hour" },
  { name: "Weekly Report", schedule: "0 10 * * 1", command: "report --type weekly", description: "Generate a weekly report every Monday at 10 AM" },
  { name: "Nightly Cleanup", schedule: "0 2 * * *", command: "cleanup --older-than 30d", description: "Clean up old data every night at 2 AM" },
  { name: "Health Check", schedule: "*/15 * * * *", command: "health-check", description: "Run health checks every 15 minutes" },
  { name: "Backup", schedule: "0 3 * * 0", command: "backup --full", description: "Full backup every Sunday at 3 AM" },
];

/* ------------------------------------------------------------------ */
/*  TasksApp                                                           */
/* ------------------------------------------------------------------ */

export function TasksApp({ windowId: _windowId }: { windowId: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<string[]>(MOCK_AGENTS);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formAgent, setFormAgent] = useState("");
  const [formSchedule, setFormSchedule] = useState("");
  const [formCommand, setFormCommand] = useState("");
  const [formDesc, setFormDesc] = useState("");

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch("/api/tasks", {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data)) {
            setTasks(data);
            setLoading(false);
            return;
          }
        }
      }
    } catch { /* fall through */ }
    setTasks([]);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/agents", {
          headers: { Accept: "application/json" },
        });
        if (res.ok) {
          const ct = res.headers.get("content-type") ?? "";
          if (ct.includes("application/json")) {
            const data = await res.json();
            if (Array.isArray(data) && data.length > 0) {
              setAgents(data.map((a: Record<string, unknown>) => String(a.name ?? "unknown")));
            }
          }
        }
      } catch { /* use fallback */ }
    })();
  }, []);

  function resetForm() {
    setFormName("");
    setFormAgent("");
    setFormSchedule("");
    setFormCommand("");
    setFormDesc("");
    setEditingId(null);
    setShowDialog(false);
  }

  function openEdit(task: Task) {
    setFormName(task.name);
    setFormAgent(task.agent);
    setFormSchedule(task.schedule);
    setFormCommand(task.command);
    setFormDesc(task.description);
    setEditingId(task.id);
    setShowDialog(true);
  }

  function applyPreset(preset: Preset) {
    setFormName(preset.name);
    setFormSchedule(preset.schedule);
    setFormCommand(preset.command);
    setFormDesc(preset.description);
    setEditingId(null);
    setShowDialog(true);
  }

  async function handleSave() {
    if (!formName.trim() || !formSchedule.trim() || !formCommand.trim()) return;

    if (editingId) {
      setTasks((prev) =>
        prev.map((t) =>
          t.id === editingId
            ? { ...t, name: formName, agent: formAgent, schedule: formSchedule, command: formCommand, description: formDesc }
            : t
        )
      );
    } else {
      const newTask: Task = {
        id: `task-${Date.now()}`,
        name: formName.trim(),
        agent: formAgent,
        schedule: formSchedule.trim(),
        command: formCommand.trim(),
        description: formDesc.trim(),
        enabled: true,
        lastRun: null,
      };
      try {
        await fetch("/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(newTask),
        });
      } catch { /* ignore */ }
      setTasks((prev) => [...prev, newTask]);
    }
    resetForm();
  }

  function toggleEnabled(id: string) {
    setTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, enabled: !t.enabled } : t))
    );
  }

  function handleDelete(id: string) {
    setTasks((prev) => prev.filter((t) => t.id !== id));
    fetch(`/api/tasks/${id}`, { method: "DELETE" }).catch(() => {});
  }

  return (
    <div className="flex flex-col h-full bg-shell-bg text-shell-text select-none relative">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <CalendarClock size={18} className="text-accent" />
          <h1 className="text-sm font-semibold">Tasks</h1>
          <span className="text-xs text-shell-text-tertiary">
            {tasks.length} scheduled
          </span>
        </div>
        <button
          onClick={() => { resetForm(); setShowDialog(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent text-white hover:bg-accent/90 transition-colors"
          aria-label="Add task"
        >
          <Plus size={14} />
          Add Task
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
            Loading tasks...
          </div>
        ) : tasks.length === 0 && !showDialog ? (
          <div className="p-4 space-y-6">
            {/* Empty state */}
            <div className="flex flex-col items-center justify-center py-8 gap-3 text-shell-text-tertiary">
              <CalendarClock size={40} className="opacity-30" />
              <p className="text-sm">No scheduled tasks</p>
            </div>

            {/* Presets */}
            <div>
              <h2 className="text-sm font-medium text-shell-text-secondary mb-3">Quick Start Presets</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {PRESETS.map((preset) => (
                  <div
                    key={preset.name}
                    className="p-3.5 rounded-xl bg-shell-surface/60 border border-white/5 space-y-2"
                  >
                    <p className="text-sm font-medium">{preset.name}</p>
                    <p className="text-xs text-shell-text-tertiary">{preset.description}</p>
                    <p className="text-[11px] text-shell-text-tertiary font-mono">{preset.schedule}</p>
                    <button
                      onClick={() => applyPreset(preset)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
                    >
                      <Play size={11} />
                      Apply
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="p-4 space-y-4">
            {/* Task table */}
            {tasks.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left" aria-label="Task list">
                  <thead>
                    <tr className="border-b border-white/5 text-[11px] uppercase tracking-wider text-shell-text-tertiary">
                      <th className="px-4 py-2.5 font-medium">Name</th>
                      <th className="px-4 py-2.5 font-medium">Agent</th>
                      <th className="px-4 py-2.5 font-medium">Schedule</th>
                      <th className="px-4 py-2.5 font-medium">Command</th>
                      <th className="px-4 py-2.5 font-medium">Status</th>
                      <th className="px-4 py-2.5 font-medium">Last Run</th>
                      <th className="px-4 py-2.5 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map((task) => (
                      <tr key={task.id} className="border-b border-white/5 hover:bg-shell-surface/50 transition-colors">
                        <td className="px-4 py-3 text-sm font-medium">{task.name}</td>
                        <td className="px-4 py-3 text-sm text-shell-text-secondary">{task.agent || "\u2014"}</td>
                        <td className="px-4 py-3 text-xs font-mono text-shell-text-secondary">{task.schedule}</td>
                        <td className="px-4 py-3 text-xs font-mono text-shell-text-secondary max-w-[200px] truncate">{task.command}</td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => toggleEnabled(task.id)}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium transition-colors ${
                              task.enabled
                                ? "bg-emerald-500/20 text-emerald-400"
                                : "bg-zinc-500/20 text-zinc-400"
                            }`}
                            aria-label={`Toggle ${task.name} ${task.enabled ? "off" : "on"}`}
                          >
                            {task.enabled ? <Play size={10} /> : <Pause size={10} />}
                            {task.enabled ? "Enabled" : "Disabled"}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-xs text-shell-text-tertiary tabular-nums">
                          {task.lastRun ?? "Never"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => openEdit(task)}
                              className="p-1.5 rounded-md hover:bg-shell-surface transition-colors text-shell-text-secondary hover:text-shell-text"
                              aria-label={`Edit ${task.name}`}
                              title="Edit"
                            >
                              <Edit size={15} />
                            </button>
                            <button
                              onClick={() => handleDelete(task.id)}
                              className="p-1.5 rounded-md hover:bg-red-500/15 transition-colors text-shell-text-secondary hover:text-red-400"
                              aria-label={`Delete ${task.name}`}
                              title="Delete"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Presets */}
            <div>
              <h2 className="text-sm font-medium text-shell-text-secondary mb-3">Presets</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {PRESETS.map((preset) => (
                  <div
                    key={preset.name}
                    className="p-3 rounded-xl bg-shell-surface/60 border border-white/5 space-y-1.5"
                  >
                    <p className="text-sm font-medium">{preset.name}</p>
                    <p className="text-xs text-shell-text-tertiary">{preset.description}</p>
                    <button
                      onClick={() => applyPreset(preset)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
                    >
                      <Play size={11} />
                      Apply
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Add/Edit Task Dialog */}
      {showDialog && (
        <div
          className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => resetForm()}
          role="dialog"
          aria-modal="true"
          aria-label={editingId ? "Edit Task" : "Add Task"}
        >
          <div
            className="w-full max-w-md bg-shell-surface rounded-xl border border-white/10 shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
              <h2 className="text-sm font-semibold">{editingId ? "Edit Task" : "Add Task"}</h2>
              <button
                onClick={resetForm}
                className="p-1 rounded-md hover:bg-white/5 text-shell-text-secondary hover:text-shell-text transition-colors"
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>

            <div className="px-5 py-4 space-y-3">
              <div>
                <label htmlFor="task-name" className="block text-xs text-shell-text-secondary mb-1.5">Name</label>
                <input
                  id="task-name"
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="My Task"
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                  autoFocus
                />
              </div>
              <div>
                <label htmlFor="task-agent" className="block text-xs text-shell-text-secondary mb-1.5">Agent (optional)</label>
                <select
                  id="task-agent"
                  value={formAgent}
                  onChange={(e) => setFormAgent(e.target.value)}
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value="">None</option>
                  {agents.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="task-schedule" className="block text-xs text-shell-text-secondary mb-1.5">Schedule (cron)</label>
                <input
                  id="task-schedule"
                  type="text"
                  value={formSchedule}
                  onChange={(e) => setFormSchedule(e.target.value)}
                  placeholder="0 9 * * *"
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm font-mono text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <div>
                <label htmlFor="task-command" className="block text-xs text-shell-text-secondary mb-1.5">Command</label>
                <input
                  id="task-command"
                  type="text"
                  value={formCommand}
                  onChange={(e) => setFormCommand(e.target.value)}
                  placeholder="summarize --last 24h"
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm font-mono text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <div>
                <label htmlFor="task-desc" className="block text-xs text-shell-text-secondary mb-1.5">Description</label>
                <input
                  id="task-desc"
                  type="text"
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="Optional description"
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-white/5">
              <button
                onClick={resetForm}
                className="px-3 py-1.5 rounded-lg text-sm text-shell-text-secondary hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!formName.trim() || !formSchedule.trim() || !formCommand.trim()}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Plus size={14} />
                {editingId ? "Save Changes" : "Add Task"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
