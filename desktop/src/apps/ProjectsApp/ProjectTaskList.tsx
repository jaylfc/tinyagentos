import { useEffect, useState } from "react";
import { projectsApi, type ProjectTask } from "@/lib/projects";

type View = "ready" | "claimed" | "closed";

export function ProjectTaskList({ projectId }: { projectId: string }) {
  const [view, setView] = useState<View>("ready");
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => {
        if (!cancelled && u?.id) setCurrentUserId(u.id);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  const actorId = currentUserId ?? "user";

  const refresh = async () => {
    try {
      if (view === "ready") setTasks(await projectsApi.tasks.ready(projectId));
      else if (view === "claimed") setTasks(await projectsApi.tasks.list(projectId, "claimed"));
      else setTasks(await projectsApi.tasks.list(projectId, "closed"));
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    refresh();
  }, [projectId, view]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const title = newTitle.trim();
    if (!title) return;
    try {
      await projectsApi.tasks.create(projectId, { title });
      setNewTitle("");
      setError(null);
      refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  // Closed view filters older than 7 days client-side per spec default.
  const visible =
    view === "closed"
      ? tasks.filter((t) => (t.closed_at ?? 0) >= Date.now() / 1000 - 7 * 86400)
      : tasks;

  return (
    <section>
      <nav role="tablist" aria-label="Task view" className="flex gap-1 mb-3">
        {(["ready", "claimed", "closed"] as View[]).map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={`px-2 py-1 text-sm rounded ${
              view === v ? "bg-zinc-700" : "bg-zinc-900 text-zinc-400"
            }`}
          >
            {v}
          </button>
        ))}
      </nav>

      <form onSubmit={create} className="flex gap-2 mb-3">
        <input
          aria-label="New task title"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="Add a task…"
          className="flex-1 px-2 py-1 bg-zinc-800 rounded text-sm"
        />
        <button type="submit" className="px-3 py-1 bg-blue-600 rounded text-sm">
          Add
        </button>
      </form>

      {error && <div role="alert" className="text-red-400 text-xs mb-2">{error}</div>}

      <ul className="space-y-1" aria-label={`${view} tasks`}>
        {visible.map((t) => (
          <li key={t.id} className="flex items-center justify-between bg-zinc-900 px-3 py-2 rounded">
            <div className="min-w-0">
              <div className="text-sm truncate">{t.title}</div>
              <div className="text-xs text-zinc-500">
                {t.id}
                {t.claimed_by ? ` · claimed by ${t.claimed_by}` : ""}
                {t.closed_at ? ` · closed` : ""}
              </div>
            </div>
            <div className="flex gap-2 text-xs">
              {view === "ready" && (
                <button
                  type="button"
                  onClick={async () => {
                    await projectsApi.tasks.claim(projectId, t.id, actorId);
                    refresh();
                  }}
                  className="px-2 py-1 bg-zinc-800 rounded"
                >
                  Claim
                </button>
              )}
              {view === "claimed" && (
                <>
                  <button
                    type="button"
                    onClick={async () => {
                      await projectsApi.tasks.release(projectId, t.id, t.claimed_by ?? actorId);
                      refresh();
                    }}
                    className="px-2 py-1 bg-zinc-800 rounded"
                  >
                    Release
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      await projectsApi.tasks.close(projectId, t.id, t.claimed_by ?? actorId);
                      refresh();
                    }}
                    className="px-2 py-1 bg-emerald-700 rounded"
                  >
                    Close
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
        {visible.length === 0 && <li className="text-sm text-zinc-500">No tasks.</li>}
      </ul>
    </section>
  );
}
