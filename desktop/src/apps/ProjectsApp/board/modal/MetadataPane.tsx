import { useState } from "react";
import { projectsApi } from "../../../../lib/projects";
import type { ProjectTask } from "../../../../lib/projects";
import type { Task } from "../types";

export interface MetadataPaneProps {
  projectId: string;
  task: Task;
  onUpdated: (t: Task) => void;
}

type FieldKey = "priority" | "assignee" | "labels";

export function MetadataPane({ projectId, task, onUpdated }: MetadataPaneProps) {
  const [editing, setEditing] = useState<FieldKey | null>(null);

  const save = async (patch: Partial<ProjectTask>) => {
    const updated = await projectsApi.tasks.update(projectId, task.id, patch);
    onUpdated(updated as unknown as Task);
    setEditing(null);
  };

  return (
    <aside className="board-meta">
      <Field label="Status" value={task.status} />
      <Field
        label="Priority"
        value={String(task.priority)}
        editing={editing === "priority"}
        onEdit={() => setEditing("priority")}
        onCancel={() => setEditing(null)}
        onSave={(v) => save({ priority: Number(v) })}
      />
      <Field
        label="Assignee"
        value={task.assignee_id ?? "—"}
        editing={editing === "assignee"}
        onEdit={() => setEditing("assignee")}
        onCancel={() => setEditing(null)}
        onSave={(v) => save({ assignee_id: v.trim() || null })}
      />
      <Field
        label="Labels"
        value={task.labels.join(", ")}
        editing={editing === "labels"}
        onEdit={() => setEditing("labels")}
        onCancel={() => setEditing(null)}
        onSave={(v) => save({ labels: v.split(",").map(s => s.trim()).filter(Boolean) })}
      />
    </aside>
  );
}

interface FieldProps {
  label: string;
  value: string;
  editing?: boolean;
  onEdit?: () => void;
  onCancel?: () => void;
  onSave?: (v: string) => void;
}

function Field({ label, value, editing, onEdit, onCancel, onSave }: FieldProps) {
  const [draft, setDraft] = useState(value);
  return (
    <div>
      <h4>{label}</h4>
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => onSave?.(draft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSave?.(draft);
            else if (e.key === "Escape") { setDraft(value); onCancel?.(); }
          }}
          aria-label={label}
        />
      ) : (
        <span
          role={onEdit ? "button" : undefined}
          tabIndex={onEdit ? 0 : undefined}
          onClick={onEdit}
          onKeyDown={(e) => { if (onEdit && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onEdit(); } }}
        >
          {value}
        </span>
      )}
    </div>
  );
}
