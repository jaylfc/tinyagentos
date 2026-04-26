export type TaskStatus = "open" | "claimed" | "closed";

export interface Task {
  id: string;
  project_id: string;
  parent_task_id: string | null;
  title: string;
  body: string;
  status: TaskStatus;
  priority: number;
  labels: string[];
  assignee_id: string | null;
  claimed_by: string | null;
  claimed_at: string | null;
  closed_at: string | null;
  closed_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export type ViewMode = "lanes" | "kanban" | "timeline";
export type GroupBy = "assignee" | "parent" | "label" | "priority";

export interface LaneHeader {
  key: string;            // stable key for React
  kind: GroupBy;
  title: string;
  subtitle?: string;
  avatarSeed?: string;    // for color hashing
}

export interface Lane {
  header: LaneHeader;
  cards: Task[];
}

export interface Filters {
  assignees: string[];
  labels: string[];
  priorities: number[];
  parentTaskId: string | null;
  hasAttachments: boolean;
  hideClosed: boolean;
  search: string;
}

export const EMPTY_FILTERS: Filters = {
  assignees: [], labels: [], priorities: [], parentTaskId: null,
  hasAttachments: false, hideClosed: false, search: "",
};
