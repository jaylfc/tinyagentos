import { useState, useCallback } from "react";
import { TopBar } from "@/components/TopBar";
import { Desktop } from "@/components/Desktop";
import { Dock } from "@/components/Dock";
import { Launchpad } from "@/components/Launchpad";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";

export function App() {
  const [launchpadOpen, setLaunchpadOpen] = useState(false);
  const [_searchOpen, setSearchOpen] = useState(false);

  const toggleLaunchpad = useCallback(() => setLaunchpadOpen((v) => !v), []);
  const toggleSearch = useCallback(() => setSearchOpen((v) => !v), []);

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
    </div>
  );
}
