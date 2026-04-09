import { useEffect } from "react";

interface ShortcutHandlers {
  onSearch: () => void;
  onLaunchpad: () => void;
}

export function useKeyboardShortcuts({ onSearch, onLaunchpad }: ShortcutHandlers) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey;

      if (ctrl && e.code === "Space") {
        e.preventDefault();
        onSearch();
      }
      if (ctrl && e.key === "l") {
        e.preventDefault();
        onLaunchpad();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSearch, onLaunchpad]);
}
