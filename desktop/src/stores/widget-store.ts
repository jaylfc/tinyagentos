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
  hydrated: boolean;
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

// Server-persistence wiring. Widget layout + visibility live in a single
// namespaced preference so they follow the user across devices. The
// localStorage mirror avoids a flash of default widgets on page load while
// the network round-trip is in flight.

const PREF_KEY = "widgets";
const CACHE_KEY = `taos-pref:${PREF_KEY}`;
const SAVE_DEBOUNCE_MS = 500;

const DEFAULT_WIDGETS: Widget[] = [
  { id: "default-clock", type: "clock", x: 0, y: 0, w: 3, h: 2 },
  { id: "default-agents", type: "agent-status", x: 3, y: 0, w: 4, h: 3 },
];

type PersistedShape = { widgets: Widget[]; showWidgets: boolean };

function readCache(): PersistedShape | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedShape;
    if (Array.isArray(parsed?.widgets) && typeof parsed?.showWidgets === "boolean") {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

function writeCache(value: PersistedShape): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(value));
  } catch {
    // quota / private mode — not fatal, the server is authoritative
  }
}

const initial = readCache();

export const useWidgetStore = create<WidgetStore>((set, get) => ({
  widgets: initial?.widgets ?? DEFAULT_WIDGETS,
  showWidgets: initial?.showWidgets ?? true,
  hydrated: false,

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

// Hydrate from the server once on module load. If the server has a saved
// layout it wins over the localStorage mirror (the user may have changed
// things on another device). If it has nothing saved, the local/default
// stays and the next change push will seed the server.
(async () => {
  try {
    const resp = await fetch(`/api/preferences/${PREF_KEY}`);
    if (!resp.ok) {
      useWidgetStore.setState({ hydrated: true });
      return;
    }
    const blob = (await resp.json()) as Partial<PersistedShape>;
    if (
      blob &&
      Array.isArray(blob.widgets) &&
      typeof blob.showWidgets === "boolean"
    ) {
      useWidgetStore.setState({
        widgets: blob.widgets,
        showWidgets: blob.showWidgets,
        hydrated: true,
      });
      writeCache({ widgets: blob.widgets, showWidgets: blob.showWidgets });
    } else {
      useWidgetStore.setState({ hydrated: true });
    }
  } catch {
    useWidgetStore.setState({ hydrated: true });
  }
})();

// Debounced persistence. We subscribe to every store change after hydration
// and push the new shape to the server. localStorage is written immediately
// so a hard reload picks up the latest state even if the network PUT is
// still in flight.
let saveTimer: ReturnType<typeof setTimeout> | null = null;

useWidgetStore.subscribe((state) => {
  if (!state.hydrated) return; // don't write back the default shape before we've loaded
  const payload: PersistedShape = {
    widgets: state.widgets,
    showWidgets: state.showWidgets,
  };
  writeCache(payload);
  if (saveTimer !== null) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveTimer = null;
    fetch(`/api/preferences/${PREF_KEY}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {
      // best-effort; the cache has the value and we'll try again on the
      // next change
    });
  }, SAVE_DEBOUNCE_MS);
});
