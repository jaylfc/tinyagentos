import { create } from "zustand";

export interface Notification {
  id: string;
  source: string;       // agent ID, "system", or app ID
  title: string;
  body: string;
  icon?: string;        // lucide icon name
  level: "info" | "success" | "warning" | "error";
  action?: string;      // URL or app ID to open on click
  read: boolean;
  timestamp: number;
}

interface NotificationStore {
  notifications: Notification[];
  centreOpen: boolean;

  addNotification: (n: Omit<Notification, "id" | "read" | "timestamp">) => string;
  markRead: (id: string) => void;
  markAllRead: () => void;
  dismiss: (id: string) => void;
  clearAll: () => void;
  toggleCentre: () => void;
  closeCentre: () => void;
  unreadCount: () => number;
}

let counter = 0;

export const useNotificationStore = create<NotificationStore>((set, get) => ({
  notifications: [],
  centreOpen: false,

  addNotification(n) {
    const id = `notif-${++counter}`;
    const notif: Notification = {
      ...n,
      id,
      read: false,
      timestamp: Date.now(),
    };
    set((s) => ({ notifications: [notif, ...s.notifications].slice(0, 100) }));
    return id;
  },

  markRead(id) {
    set((s) => ({
      notifications: s.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
    }));
  },

  markAllRead() {
    set((s) => ({ notifications: s.notifications.map((n) => ({ ...n, read: true })) }));
  },

  dismiss(id) {
    set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) }));
  },

  clearAll() {
    set({ notifications: [] });
  },

  toggleCentre() {
    set((s) => ({ centreOpen: !s.centreOpen }));
  },

  closeCentre() {
    set({ centreOpen: false });
  },

  unreadCount() {
    return get().notifications.filter((n) => !n.read).length;
  },
}));
