import { create } from "zustand";

const DEFAULT_PINNED = ["messages", "agents", "files", "store", "settings"];

interface DockStore {
  pinned: string[];
  pin: (appId: string) => void;
  unpin: (appId: string) => void;
  reorder: (appIds: string[]) => void;
}

export const useDockStore = create<DockStore>((set, get) => ({
  pinned: DEFAULT_PINNED,

  pin(appId) {
    if (get().pinned.includes(appId)) return;
    set((s) => ({ pinned: [...s.pinned, appId] }));
  },

  unpin(appId) {
    set((s) => ({ pinned: s.pinned.filter((id) => id !== appId) }));
  },

  reorder(appIds) {
    set({ pinned: appIds });
  },
}));
