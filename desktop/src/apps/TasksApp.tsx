import { useState, useEffect, useCallback } from "react";
import { CalendarClock, Plus, Edit, Trash2, Play, Pause, X } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@/components/ui";

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
  const [agents, setAgents] = useState<string[]>([]);
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
        <Button
          size="sm"
          onClick={() => { resetForm(); setShowDialog(true); }}
          aria-label="Add task"
        >
          <Plus size={14} />
          Add Task
        </Button>
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
                  <Card key={preset.name}>
                    <CardContent className="p-3.5 space-y-2">
                      <p className="text-sm font-medium">{preset.name}</p>
                      <p className="text-xs text-shell-text-tertiary">{preset.description}</p>
                      <p className="text-[11px] text-shell-text-tertiary font-mono">{preset.schedule}</p>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => applyPreset(preset)}
                      >
                        <Play size={11} />
                        Apply
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="p-4 space-y-4">
            {/* Task rows */}
            {tasks.length > 0 && (
              <div className="space-y-2" aria-label="Task list">
                {tasks.map((task) => (
                  <Card key={task.id}>
                    <CardContent className="flex items-center gap-3 p-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium truncate">{task.name}</p>
                          <span className="text-xs text-shell-text-secondary">
                            {task.agent || "\u2014"}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-shell-text-tertiary">
                          <span className="font-mono">{task.schedule}</span>
                          <span className="font-mono truncate max-w-[200px]">{task.command}</span>
                          <span className="tabular-nums">
                            Last: {task.lastRun ?? "Never"}
                          </span>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => toggleEnabled(task.id)}
                        className={
                          task.enabled
                            ? "text-emerald-400 hover:text-emerald-300"
                            : "text-zinc-400"
                        }
                        aria-label={`Toggle ${task.name} ${task.enabled ? "off" : "on"}`}
                        title={task.enabled ? "Enabled" : "Disabled"}
                      >
                        {task.enabled ? <Play size={14} /> : <Pause size={14} />}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openEdit(task)}
                        aria-label={`Edit ${task.name}`}
                        title="Edit"
                      >
                        <Edit size={15} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(task.id)}
                        className="hover:text-red-400 hover:bg-red-500/15"
                        aria-label={`Delete ${task.name}`}
                        title="Delete"
                      >
                        <Trash2 size={15} />
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {/* Presets */}
            <div>
              <h2 className="text-sm font-medium text-shell-text-secondary mb-3">Presets</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {PRESETS.map((preset) => (
                  <Card key={preset.name}>
                    <CardContent className="p-3 space-y-1.5">
                      <p className="text-sm font-medium">{preset.name}</p>
                      <p className="text-xs text-shell-text-tertiary">{preset.description}</p>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => applyPreset(preset)}
                      >
                        <Play size={11} />
                        Apply
                      </Button>
                    </CardContent>
                  </Card>
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
          <Card
            className="w-full max-w-md shadow-2xl overflow-hidden bg-shell-surface"
            onClick={(e) => e.stopPropagation()}
          >
            <CardHeader className="flex flex-row items-center justify-between border-b border-white/5 px-5 py-4">
              <CardTitle className="text-sm font-semibold">{editingId ? "Edit Task" : "Add Task"}</CardTitle>
              <Button
                variant="ghost"
                size="icon"
                onClick={resetForm}
                aria-label="Close dialog"
                className="h-7 w-7"
              >
                <X size={16} />
              </Button>
            </CardHeader>

            <CardContent className="px-5 py-4 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="task-name">Name</Label>
                <Input
                  id="task-name"
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="My Task"
                  autoFocus
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="task-agent">Agent (optional)</Label>
                <select
                  id="task-agent"
                  value={formAgent}
                  onChange={(e) => setFormAgent(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20"
                >
                  <option value="">None</option>
                  {agents.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="task-schedule">Schedule (cron)</Label>
                <Input
                  id="task-schedule"
                  type="text"
                  value={formSchedule}
                  onChange={(e) => setFormSchedule(e.target.value)}
                  placeholder="0 9 * * *"
                  className="font-mono"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="task-command">Command</Label>
                <Input
                  id="task-command"
                  type="text"
                  value={formCommand}
                  onChange={(e) => setFormCommand(e.target.value)}
                  placeholder="summarize --last 24h"
                  className="font-mono"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="task-desc">Description</Label>
                <Input
                  id="task-desc"
                  type="text"
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="Optional description"
                />
              </div>
            </CardContent>

            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-white/5">
              <Button
                variant="ghost"
                onClick={resetForm}
              >
                Cancel
              </Button>
              <Button
                onClick={handleSave}
                disabled={!formName.trim() || !formSchedule.trim() || !formCommand.trim()}
              >
                <Plus size={14} />
                {editingId ? "Save Changes" : "Add Task"}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
