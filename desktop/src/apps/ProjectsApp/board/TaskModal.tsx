import { useEffect, useState } from "react";
import styles from "./TaskModal.module.css";
import { Hero } from "./modal/Hero";
import { SubTasks } from "./modal/SubTasks";
import { Relationships } from "./modal/Relationships";
import { Activity } from "./modal/Activity";
import { projectsApi } from "../../../lib/projects";
import type { Task } from "./types";

export interface TaskModalProps {
  projectId: string;
  taskId: string | null;
  currentUserId: string;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

export function TaskModal({ projectId, taskId, currentUserId, onClose, onPrev, onNext }: TaskModalProps) {
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [task, setTask] = useState<Task | null>(null);

  useEffect(() => {
    if (!taskId) { setTask(null); return; }
    let cancelled = false;
    (async () => {
      const all = (await projectsApi.tasks.list(projectId)) as unknown as Task[];
      if (cancelled) return;
      setAllTasks(all);
      setTask(all.find(t => t.id === taskId) ?? null);
    })();
    return () => { cancelled = true; };
  }, [projectId, taskId]);

  useEffect(() => {
    if (!taskId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowDown") onNext?.();
      else if (e.key === "ArrowUp") onPrev?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [taskId, onClose, onNext, onPrev]);

  if (!taskId) return null;
  return (
    <div className={styles.scrim} role="dialog" aria-modal="true" aria-label={task?.title ?? "Task"}>
      <div className={styles.frame}>
        <header className={styles.bar}>
          <span className={styles.crumb}>Board / <b>{task?.id ?? taskId}</b></span>
          <span className={styles.grow} />
          <button type="button" onClick={onPrev} aria-label="Previous task">↑</button>
          <button type="button" onClick={onNext} aria-label="Next task">↓</button>
          <button type="button" onClick={onClose} aria-label="Close">✕</button>
        </header>
        {task && <Hero task={task} />}
        <div className={styles.body}>
          {task ? (
            <>
              <h1 className={styles.title}>{task.title}</h1>
              {task.body && <p className={styles.bodyText}>{task.body}</p>}
              <SubTasks all={allTasks} parentId={task.id} />
              <Relationships projectId={projectId} taskId={task.id} />
              <Activity projectId={projectId} taskId={task.id} currentUserId={currentUserId} />
            </>
          ) : <p className={styles.loading}>Loading…</p>}
        </div>
      </div>
    </div>
  );
}
