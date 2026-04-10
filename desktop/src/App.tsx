import { useState, useCallback, useEffect } from "react";
import * as icons from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Desktop } from "@/components/Desktop";
import { Dock } from "@/components/Dock";
import { Launchpad } from "@/components/Launchpad";
import { SearchPalette } from "@/components/SearchPalette";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { useDeviceMode } from "@/hooks/use-device-mode";
import { useThemeStore } from "@/stores/theme-store";
import { useProcessStore } from "@/stores/process-store";
import { getAllApps, getApp } from "@/registry/app-registry";
import { PillBar } from "@/components/mobile/PillBar";
import { CardSwitcher } from "@/components/mobile/CardSwitcher";
import { MobileTopBar } from "@/components/mobile/MobileTopBar";
import { MobileApp } from "@/components/mobile/MobileApp";

function resolveIcon(iconName: string): icons.LucideIcon {
  const key = iconName
    .split("-")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join("") as keyof typeof icons;
  return (icons[key] as icons.LucideIcon) ?? icons.HelpCircle;
}

export function App() {
  const [launchpadOpen, setLaunchpadOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [cardSwitcherOpen, setCardSwitcherOpen] = useState(false);
  const [activeWindowId, setActiveWindowId] = useState<string | null>(null);

  const mode = useDeviceMode();
  const wallpaperStyle = useThemeStore((s) => s.wallpaperStyle);
  const windows = useProcessStore((s) => s.windows);
  const openWindow = useProcessStore((s) => s.openWindow);

  const activeWindow = windows.find((w) => w.id === activeWindowId);
  const activeApp = activeWindow ? getApp(activeWindow.appId) : null;

  // Clear activeWindowId if the window was closed externally
  useEffect(() => {
    if (activeWindowId && !windows.find((w) => w.id === activeWindowId)) {
      setActiveWindowId(null);
    }
  }, [activeWindowId, windows]);

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

  // Mobile handlers
  const handleMobileBack = useCallback(() => {
    if (activeWindowId) {
      setActiveWindowId(null);
    }
  }, [activeWindowId]);

  const handleSelectApp = useCallback((windowId: string) => {
    setActiveWindowId(windowId);
    setCardSwitcherOpen(false);
  }, []);

  const handleMobileHome = useCallback(() => {
    setActiveWindowId(null);
    setLaunchpadOpen(true);
  }, []);

  if (mode === "desktop") {
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

  // Mobile/Tablet layout
  return (
    <div
      className="h-screen w-screen flex flex-col overflow-hidden text-shell-text"
      style={{ background: wallpaperStyle }}
    >
      <MobileTopBar
        currentAppName={activeApp?.name ?? null}
        onBack={handleMobileBack}
      />
      <div className="flex-1 relative overflow-hidden" style={{ paddingBottom: "calc(48px + env(safe-area-inset-bottom, 0px))" }}>
        {activeWindowId && activeWindow ? (
          <MobileApp appId={activeWindow.appId} windowId={activeWindowId} />
        ) : (
          <div className="h-full overflow-y-auto" style={{ paddingTop: "env(safe-area-inset-top, 20px)" }}>
            {/* iOS-style home grid */}
            <div className="px-6 pt-8 pb-4">
              <div className="grid grid-cols-4 gap-x-5 gap-y-6 max-w-sm mx-auto">
                {getAllApps()
                  .slice(0, 20)
                  .map((app) => {
                    const Icon = resolveIcon(app.icon);
                    return (
                      <button
                        key={app.id}
                        onClick={() => {
                          const wid = openWindow(app.id, app.defaultSize);
                          setActiveWindowId(wid);
                        }}
                        className="flex flex-col items-center gap-1.5 active:scale-90 transition-transform"
                        aria-label={`Open ${app.name}`}
                      >
                        <div className="w-[60px] h-[60px] rounded-[14px] flex items-center justify-center"
                          style={{
                            background: "rgba(255,255,255,0.08)",
                            backdropFilter: "blur(10px)",
                            WebkitBackdropFilter: "blur(10px)",
                            border: "1px solid rgba(255,255,255,0.06)",
                          }}
                        >
                          <Icon size={26} className="text-white/70" />
                        </div>
                        <span className="text-[11px] text-white/70 truncate w-full text-center leading-tight">
                          {app.name}
                        </span>
                      </button>
                    );
                  })}
              </div>
            </div>
          </div>
        )}
      </div>
      <PillBar
        onHome={handleMobileHome}
        onCardSwitcher={() => setCardSwitcherOpen(true)}
        onBack={handleMobileBack}
      />
      <CardSwitcher
        open={cardSwitcherOpen}
        onClose={() => setCardSwitcherOpen(false)}
        onSelectApp={handleSelectApp}
        onLaunchpad={() => {
          setCardSwitcherOpen(false);
          setLaunchpadOpen(true);
        }}
      />
      <Launchpad open={launchpadOpen} onClose={() => setLaunchpadOpen(false)} />
      <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
