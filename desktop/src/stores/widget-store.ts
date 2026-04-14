import { create } from "zustand";

export interface Widget {
  id: string;
  type: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  config?: Record<string, unknown>;
}

interface WidgetStore {
  widgets: Widget[];
  showWidgets: boolean;
  addWidget: (type: string) => void;
  removeWidget: (id: string) => void;
  updateLayout: (layouts: { id: string; x: number; y: number; w: number; h: number }[]) => void;
  toggleWidgets: () => void;
}

const WIDGET_DEFAULTS: Record<string, { w: number; h: number; minW?: number; minH?: number }> = {
  clock:          { w: 3, h: 2, minW: 2, minH: 2 },
  "agent-status": { w: 4, h: 3, minW: 2, minH: 2 },
  "quick-notes":  { w: 4, h: 4, minW: 2, minH: 2 },
  "system-stats": { w: 3, h: 3, minW: 2, minH: 2 },
  weather:        { w: 3, h: 3, minW: 2, minH: 2 },
};

let nextId = 1;

function makeId(): string {
  return `widget-${Date.now()}-${nextId++}`;
}

function findOpenSpot(widgets: Widget[], w: number, h: number): { x: number; y: number } {
  const cols = 12;
  for (let row = 0; row < 100; row++) {
    for (let col = 0; col <= cols - w; col++) {
      const overlaps = widgets.some(
        (wg) =>
          col < wg.x + wg.w &&
          col + w > wg.x &&
          row < wg.y + wg.h &&
          row + h > wg.y,
      );
      if (!overlaps) return { x: col, y: row };
    }
  }
  return { x: 0, y: 0 };
}

export const useWidgetStore = create<WidgetStore>((set, get) => ({
  widgets: [
    { id: "default-clock", type: "clock", x: 0, y: 0, w: 3, h: 2 },
    { id: "default-agents", type: "agent-status", x: 3, y: 0, w: 4, h: 3 },
  ],
  showWidgets: true,

  addWidget(type) {
    const defaults = WIDGET_DEFAULTS[type] ?? { w: 3, h: 2 };
    const pos = findOpenSpot(get().widgets, defaults.w, defaults.h);
    const widget: Widget = {
      id: makeId(),
      type,
      x: pos.x,
      y: pos.y,
      w: defaults.w,
      h: defaults.h,
      minW: defaults.minW,
      minH: defaults.minH,
    };
    set((s) => ({ widgets: [...s.widgets, widget] }));
  },

  removeWidget(id) {
    set((s) => ({ widgets: s.widgets.filter((w) => w.id !== id) }));
  },

  updateLayout(layouts) {
    set((s) => ({
      widgets: s.widgets.map((w) => {
        const update = layouts.find((l) => l.id === w.id);
        if (!update) return w;
        return { ...w, x: update.x, y: update.y, w: update.w, h: update.h };
      }),
    }));
  },

  toggleWidgets() {
    set((s) => ({ showWidgets: !s.showWidgets }));
  },
}));
