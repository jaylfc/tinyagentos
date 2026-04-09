import { useState, useCallback, useEffect } from "react";
import { TopBar } from "@/components/TopBar";
import { Desktop } from "@/components/Desktop";
import { Dock } from "@/components/Dock";
import { Launchpad } from "@/components/Launchpad";
import { SearchPalette } from "@/components/SearchPalette";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";

export function App() {
  const [launchpadOpen, setLaunchpadOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const toggleLaunchpad = useCallback(() => setLaunchpadOpen((v) => !v), []);
  const toggleSearch = useCallback(() => setSearchOpen((v) => !v), []);

  // Listen for launchpad open event from context menu
  useEffect(() => {
    const handler = () => setLaunchpadOpen(true);
    window.addEventListener("open-launchpad", handler);
    return () => window.removeEventListener("open-launchpad", handler);
  }, []);

  useKeyboardShortcuts({
    onSearch: toggleSearch,
    onLaunchpad: toggleLaunchpad,
  });

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-shell-bg text-shell-text">
      <TopBar onSearchOpen={toggleSearch} />
      <Desktop />
      <Dock onLaunchpadOpen={toggleLaunchpad} />
      <Launchpad open={launchpadOpen} onClose={() => setLaunchpadOpen(false)} />
      <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
