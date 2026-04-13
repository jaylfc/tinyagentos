import { create } from "zustand";

type WidgetItem = { type: "widget"; widgetType: string };
type AppItem = { type: "app"; appId: string };
export type HomeItem = WidgetItem | AppItem;

export interface HomePage {
  items: HomeItem[];
}

const ALL_APP_IDS = [
  "messages", "agents", "files", "store", "settings", "models", "providers",
  "activity", "cluster", "memory", "channels", "secrets", "tasks", "import",
  "images", "library", "reddit", "youtube", "github", "x-monitor",
  "agent-browsers", "calculator", "calendar", "contacts",
];

const DEFAULT_DOCK: string[] = ["messages", "agents", "files", "store"];

const DEFAULT_PAGES: HomePage[] = [
  {
    items: [
      { type: "widget", widgetType: "greeting" },
      { type: "widget", widgetType: "weather" },
      { type: "widget", widgetType: "system-stats" },
      { type: "widget", widgetType: "agent-status" },
    ],
  },
  {
    items: ALL_APP_IDS.map((appId) => ({ type: "app", appId }) as AppItem),
  },
];

interface MobileHomeStore {
  dockApps: string[];
  pages: HomePage[];
  activePageIndex: number;
  setActivePage: (index: number) => void;
  setDockApps: (appIds: string[]) => void;
  addPage: () => void;
  removePage: (index: number) => void;
  addItemToPage: (pageIndex: number, item: HomeItem) => void;
  removeItemFromPage: (pageIndex: number, itemIndex: number) => void;
}

export const useMobileHomeStore = create<MobileHomeStore>((set) => ({
  dockApps: DEFAULT_DOCK,
  pages: DEFAULT_PAGES,
  activePageIndex: 0,

  setActivePage(index) {
    set({ activePageIndex: index });
  },

  setDockApps(appIds) {
    set({ dockApps: appIds });
  },

  addPage() {
    set((s) => ({ pages: [...s.pages, { items: [] }] }));
  },

  removePage(index) {
    set((s) => {
      const pages = s.pages.filter((_, i) => i !== index);
      const activePageIndex = Math.min(s.activePageIndex, Math.max(0, pages.length - 1));
      return { pages, activePageIndex };
    });
  },

  addItemToPage(pageIndex, item) {
    set((s) => ({
      pages: s.pages.map((page, i) =>
        i === pageIndex ? { items: [...page.items, item] } : page
      ),
    }));
  },

  removeItemFromPage(pageIndex, itemIndex) {
    set((s) => ({
      pages: s.pages.map((page, i) =>
        i === pageIndex
          ? { items: page.items.filter((_, j) => j !== itemIndex) }
          : page
      ),
    }));
  },
}));
