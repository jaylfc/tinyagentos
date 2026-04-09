import type { ComponentType } from "react";

export interface AppManifest {
  id: string;
  name: string;
  icon: string;
  category: "platform" | "os" | "streaming" | "game";
  component: () => Promise<{ default: ComponentType<{ windowId: string }> }>;
  defaultSize: { w: number; h: number };
  minSize: { w: number; h: number };
  singleton: boolean;
  pinned: boolean;
  launchpadOrder: number;
}

const placeholder = () =>
  import("@/apps/PlaceholderApp").then((m) => ({ default: m.PlaceholderApp }));

const apps: AppManifest[] = [
  // Platform apps
  { id: "messages", name: "Messages", icon: "message-circle", category: "platform", component: placeholder, defaultSize: { w: 900, h: 600 }, minSize: { w: 400, h: 300 }, singleton: true, pinned: true, launchpadOrder: 1 },
  { id: "agents", name: "Agents", icon: "bot", category: "platform", component: placeholder, defaultSize: { w: 1000, h: 650 }, minSize: { w: 500, h: 400 }, singleton: true, pinned: true, launchpadOrder: 2 },
  { id: "files", name: "Files", icon: "folder", category: "platform", component: placeholder, defaultSize: { w: 900, h: 550 }, minSize: { w: 400, h: 300 }, singleton: true, pinned: true, launchpadOrder: 3 },
  { id: "store", name: "Store", icon: "shopping-bag", category: "platform", component: placeholder, defaultSize: { w: 1000, h: 700 }, minSize: { w: 600, h: 400 }, singleton: true, pinned: true, launchpadOrder: 4 },
  { id: "settings", name: "Settings", icon: "settings", category: "platform", component: placeholder, defaultSize: { w: 800, h: 550 }, minSize: { w: 500, h: 400 }, singleton: true, pinned: true, launchpadOrder: 5 },
  { id: "models", name: "Models", icon: "brain", category: "platform", component: placeholder, defaultSize: { w: 900, h: 600 }, minSize: { w: 500, h: 400 }, singleton: true, pinned: false, launchpadOrder: 6 },
  { id: "dashboard", name: "Dashboard", icon: "layout-dashboard", category: "platform", component: placeholder, defaultSize: { w: 1000, h: 650 }, minSize: { w: 600, h: 400 }, singleton: true, pinned: false, launchpadOrder: 7 },
  { id: "memory", name: "Memory", icon: "database", category: "platform", component: placeholder, defaultSize: { w: 850, h: 550 }, minSize: { w: 450, h: 350 }, singleton: true, pinned: false, launchpadOrder: 8 },
  { id: "channels", name: "Channels", icon: "radio", category: "platform", component: placeholder, defaultSize: { w: 800, h: 500 }, minSize: { w: 450, h: 350 }, singleton: true, pinned: false, launchpadOrder: 9 },
  { id: "secrets", name: "Secrets", icon: "key-round", category: "platform", component: placeholder, defaultSize: { w: 750, h: 500 }, minSize: { w: 400, h: 300 }, singleton: true, pinned: false, launchpadOrder: 10 },
  { id: "tasks", name: "Tasks", icon: "calendar-clock", category: "platform", component: placeholder, defaultSize: { w: 800, h: 500 }, minSize: { w: 450, h: 350 }, singleton: true, pinned: false, launchpadOrder: 11 },
  { id: "import", name: "Import", icon: "upload", category: "platform", component: placeholder, defaultSize: { w: 700, h: 450 }, minSize: { w: 400, h: 300 }, singleton: true, pinned: false, launchpadOrder: 12 },
  { id: "images", name: "Images", icon: "image", category: "platform", component: placeholder, defaultSize: { w: 900, h: 600 }, minSize: { w: 500, h: 400 }, singleton: true, pinned: false, launchpadOrder: 13 },

  // OS apps
  { id: "calculator", name: "Calculator", icon: "calculator", category: "os", component: placeholder, defaultSize: { w: 320, h: 480 }, minSize: { w: 280, h: 400 }, singleton: true, pinned: false, launchpadOrder: 20 },
  { id: "calendar", name: "Calendar", icon: "calendar", category: "os", component: placeholder, defaultSize: { w: 900, h: 600 }, minSize: { w: 600, h: 400 }, singleton: true, pinned: false, launchpadOrder: 21 },
  { id: "contacts", name: "Contacts", icon: "contact", category: "os", component: placeholder, defaultSize: { w: 700, h: 500 }, minSize: { w: 400, h: 300 }, singleton: true, pinned: false, launchpadOrder: 22 },
  { id: "browser", name: "Browser", icon: "globe", category: "os", component: placeholder, defaultSize: { w: 1024, h: 700 }, minSize: { w: 600, h: 400 }, singleton: false, pinned: false, launchpadOrder: 23 },
  { id: "media-player", name: "Media Player", icon: "play-circle", category: "os", component: placeholder, defaultSize: { w: 800, h: 500 }, minSize: { w: 400, h: 300 }, singleton: false, pinned: false, launchpadOrder: 24 },
  { id: "text-editor", name: "Text Editor", icon: "file-text", category: "os", component: placeholder, defaultSize: { w: 800, h: 550 }, minSize: { w: 400, h: 300 }, singleton: false, pinned: false, launchpadOrder: 25 },
  { id: "image-viewer", name: "Image Viewer", icon: "eye", category: "os", component: placeholder, defaultSize: { w: 800, h: 600 }, minSize: { w: 400, h: 300 }, singleton: false, pinned: false, launchpadOrder: 26 },
  { id: "terminal", name: "Terminal", icon: "terminal", category: "os", component: placeholder, defaultSize: { w: 800, h: 500 }, minSize: { w: 400, h: 250 }, singleton: false, pinned: false, launchpadOrder: 27 },

  // Games
  { id: "chess", name: "Chess", icon: "crown", category: "game", component: placeholder, defaultSize: { w: 700, h: 700 }, minSize: { w: 500, h: 500 }, singleton: true, pinned: false, launchpadOrder: 40 },
  { id: "wordle", name: "Wordle", icon: "spell-check", category: "game", component: placeholder, defaultSize: { w: 500, h: 650 }, minSize: { w: 400, h: 550 }, singleton: true, pinned: false, launchpadOrder: 41 },
  { id: "crosswords", name: "Crosswords", icon: "grid-3x3", category: "game", component: placeholder, defaultSize: { w: 700, h: 600 }, minSize: { w: 500, h: 450 }, singleton: true, pinned: false, launchpadOrder: 42 },
];

export function getApp(id: string): AppManifest | undefined {
  return apps.find((a) => a.id === id);
}

export function getAppsByCategory(category: AppManifest["category"]): AppManifest[] {
  return apps.filter((a) => a.category === category);
}

export function getAllApps(): AppManifest[] {
  return [...apps].sort((a, b) => a.launchpadOrder - b.launchpadOrder);
}
