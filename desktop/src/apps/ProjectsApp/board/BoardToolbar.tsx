import styles from "./BoardToolbar.module.css";
import type { ViewMode, GroupBy, Filters } from "./types";
import { BoardFilters } from "./BoardFilters";

export interface BoardToolbarProps {
  viewMode: ViewMode;
  groupBy: GroupBy;
  filters: Filters;
  live: boolean;
  onChangeView: (m: ViewMode) => void;
  onChangeGroup: (g: GroupBy) => void;
  onChangeFilters: (f: Filters) => void;
  onAddTask?: () => void;
}

const VIEWS: ViewMode[] = ["lanes", "kanban", "timeline"];
const VIEW_LABEL: Record<ViewMode, string> = {
  lanes: "▦ Lanes",
  kanban: "▤ Kanban",
  timeline: "⇆ Timeline",
};

export function BoardToolbar(p: BoardToolbarProps) {
  return (
    <div className={styles.bar}>
      <div className={styles.crumb}>Board</div>
      <div className={styles.grow} />
      <div className={styles.seg} role="tablist" aria-label="Board view">
        {VIEWS.map(m => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={p.viewMode === m}
            disabled={m === "timeline"}
            onClick={() => p.onChangeView(m)}
            className={p.viewMode === m ? styles.on : ""}
          >
            {VIEW_LABEL[m]}
          </button>
        ))}
      </div>
      {p.viewMode === "lanes" && (
        <label className={styles.pill} aria-label="Group by">
          Group:
          <select
            value={p.groupBy}
            onChange={(e) => p.onChangeGroup(e.target.value as GroupBy)}
          >
            <option value="assignee">Assignee</option>
            <option value="parent">Parent</option>
            <option value="label">Label</option>
            <option value="priority">Priority</option>
          </select>
        </label>
      )}
      <input
        className={styles.search}
        placeholder="Search tasks…"
        value={p.filters.search}
        onChange={(e) => p.onChangeFilters({ ...p.filters, search: e.target.value })}
        aria-label="Search tasks"
      />
      <BoardFilters value={p.filters} onChange={p.onChangeFilters} />
      <span className={`${styles.pill} ${p.live ? styles.live : styles.dead}`}>● Live</span>
      {p.onAddTask && (
        <button type="button" className={styles.add} onClick={p.onAddTask}>＋ Task</button>
      )}
    </div>
  );
}
