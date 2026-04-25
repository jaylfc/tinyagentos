import { useEffect, useState } from "react";
import { projectsApi, type ProjectActivity } from "@/lib/projects";

export function ProjectActivity({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<ProjectActivity[]>([]);

  useEffect(() => {
    projectsApi.activity(projectId).then(setItems);
  }, [projectId]);

  return (
    <ul className="space-y-1" aria-label="Activity">
      {items.map((a) => (
        <li key={a.id} className="bg-zinc-900 px-3 py-2 rounded text-sm">
          <span className="text-zinc-500 mr-2">{new Date(a.created_at * 1000).toLocaleString()}</span>
          <span className="font-medium">{a.action}</span>
          {a.payload && Object.keys(a.payload).length > 0 && (
            <span className="ml-2 text-zinc-500 text-xs">{JSON.stringify(a.payload)}</span>
          )}
        </li>
      ))}
      {items.length === 0 && <li className="text-sm text-zinc-500">No activity.</li>}
    </ul>
  );
}
