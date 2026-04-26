import { useEffect, useState } from "react";
import { projectsApi } from "../../../../lib/projects";
import type { ProjectRelationship } from "../../../../lib/projects";

export function Relationships({ projectId, taskId }: { projectId: string; taskId: string }) {
  const [rels, setRels] = useState<ProjectRelationship[]>([]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [from, to] = await Promise.all([
        projectsApi.tasks.listRelationships(projectId, taskId, "from"),
        projectsApi.tasks.listRelationships(projectId, taskId, "to"),
      ]);
      if (!cancelled) setRels([...from, ...to]);
    })();
    return () => { cancelled = true; };
  }, [projectId, taskId]);
  if (rels.length === 0) return null;
  return (
    <section className="board-section">
      <h3>Relationships</h3>
      <ul>
        {rels.map(r => (
          <li key={r.id}>
            <b>{r.kind}</b>{" "}
            {r.from_task_id === taskId ? "→" : "←"}{" "}
            {r.from_task_id === taskId ? r.to_task_id : r.from_task_id}
          </li>
        ))}
      </ul>
    </section>
  );
}
