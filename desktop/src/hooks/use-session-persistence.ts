import { useEffect, useRef } from "react";
import { useProcessStore, type SnapPosition } from "@/stores/process-store";
import { useDockStore } from "@/stores/dock-store";
import { useThemeStore } from "@/stores/theme-store";
import { getApp } from "@/registry/app-registry";

interface SavedWindow {
  appId: string;
  x: number;
  y: number;
  w: number;
  h: number;
  maximized: boolean;
  snapped: string | null;
}

export function useSessionPersistence() {
  const windows = useProcessStore((s) => s.windows);
  const openWindow = useProcessStore((s) => s.openWindow);
  const updatePosition = useProcessStore((s) => s.updatePosition);
  const updateSize = useProcessStore((s) => s.updateSize);
  const maximizeWindow = useProcessStore((s) => s.maximizeWindow);
  const snapWindow = useProcessStore((s) => s.snapWindow);
  const pinned = useDockStore((s) => s.pinned);
  const wallpaperId = useThemeStore((s) => s.wallpaperId);

  const restored = useRef(false);
  const saveTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dockTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wallpaperTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Restore everything on mount (once)
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;

    // Restore windows
    fetch("/api/desktop/windows")
      .then((r) => r.json())
      .then((positions: SavedWindow[]) => {
        if (!Array.isArray(positions)) return;
        for (const saved of positions) {
          const app = getApp(saved.appId);
          if (!app) continue;
          const wid = openWindow(saved.appId, { w: saved.w, h: saved.h });
          updatePosition(wid, saved.x, saved.y);
          updateSize(wid, saved.w, saved.h);
          if (saved.maximized) {
            maximizeWindow(wid);
          }
          if (saved.snapped) {
            snapWindow(wid, saved.snapped as SnapPosition);
          }
        }
      })
      .catch(() => {});

    // Restore dock
    fetch("/api/desktop/dock")
      .then((r) => r.json())
      .then((data: { pinned?: string[] }) => {
        if (data.pinned && Array.isArray(data.pinned)) {
          useDockStore.getState().reorder(data.pinned);
        }
      })
      .catch(() => {});

    // Restore wallpaper
    fetch("/api/desktop/settings")
      .then((r) => r.json())
      .then((data: { wallpaper?: string }) => {
        if (data.wallpaper && data.wallpaper !== "default") {
          useThemeStore.getState().setWallpaper(data.wallpaper);
        }
      })
      .catch(() => {});
  }, [openWindow, updatePosition, updateSize, maximizeWindow, snapWindow]);

  // Auto-save windows (debounced 2s)
  useEffect(() => {
    if (!restored.current) return;

    if (saveTimeout.current) clearTimeout(saveTimeout.current);
    saveTimeout.current = setTimeout(() => {
      const state: SavedWindow[] = windows.map((w) => ({
        appId: w.appId,
        x: w.position.x,
        y: w.position.y,
        w: w.size.w,
        h: w.size.h,
        maximized: w.maximized,
        snapped: w.snapped,
      }));

      fetch("/api/desktop/windows", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ positions: state }),
      }).catch(() => {});
    }, 2000);

    return () => {
      if (saveTimeout.current) clearTimeout(saveTimeout.current);
    };
  }, [windows]);

  // Auto-save dock (debounced 1s)
  useEffect(() => {
    if (!restored.current) return;

    if (dockTimeout.current) clearTimeout(dockTimeout.current);
    dockTimeout.current = setTimeout(() => {
      fetch("/api/desktop/dock", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pinned }),
      }).catch(() => {});
    }, 1000);

    return () => {
      if (dockTimeout.current) clearTimeout(dockTimeout.current);
    };
  }, [pinned]);

  // Auto-save wallpaper (debounced 500ms)
  useEffect(() => {
    if (!restored.current) return;

    if (wallpaperTimeout.current) clearTimeout(wallpaperTimeout.current);
    wallpaperTimeout.current = setTimeout(() => {
      fetch("/api/desktop/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallpaper: wallpaperId }),
      }).catch(() => {});
    }, 500);

    return () => {
      if (wallpaperTimeout.current) clearTimeout(wallpaperTimeout.current);
    };
  }, [wallpaperId]);
}
