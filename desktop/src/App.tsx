import { useState, useCallback, useEffect } from "react";
import * as icons from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Desktop } from "@/components/Desktop";
import { Dock } from "@/components/Dock";
import { Launchpad } from "@/components/Launchpad";
import { SearchPalette } from "@/components/SearchPalette";
import { ShortcutProvider, useShortcut } from "@/hooks/use-shortcut-registry";
import { useSessionPersistence } from "@/hooks/use-session-persistence";
import { useDeviceMode } from "@/hooks/use-device-mode";
import { useThemeStore } from "@/stores/theme-store";
import { useProcessStore } from "@/stores/process-store";
import { useDockStore } from "@/stores/dock-store";
import { getAllApps, getApp } from "@/registry/app-registry";
import { PillBar } from "@/components/mobile/PillBar";
import { CardSwitcher } from "@/components/mobile/CardSwitcher";
import { MobileTopBar } from "@/components/mobile/MobileTopBar";
import { MobileApp } from "@/components/mobile/MobileApp";
import { LoginGate } from "@/components/LoginGate";
import { LoginScreen } from "@/components/LoginScreen";
import { NotificationToasts } from "@/components/NotificationToast";
import { NotificationCentre } from "@/components/NotificationCentre";
import { useNotificationStore } from "@/stores/notification-store";

interface SystemShortcutsProps {
  toggleSearch: () => void;
  toggleLaunchpad: () => void;
}

function SystemShortcuts({ toggleSearch, toggleLaunchpad }: SystemShortcutsProps) {
  const windows = useProcessStore((s) => s.windows);
  const closeWindow = useProcessStore((s) => s.closeWindow);
  const minimizeWindow = useProcessStore((s) => s.minimizeWindow);
  const maximizeWindow = useProcessStore((s) => s.maximizeWindow);
  const focusWindow = useProcessStore((s) => s.focusWindow);
  const openWindow = useProcessStore((s) => s.openWindow);
  const pinned = useDockStore((s) => s.pinned);

  const getFocusedId = useCallback(() => {
    const sorted = [...windows]
      .filter((w) => !w.minimized)
      .sort((a, b) => b.zIndex - a.zIndex);
    return sorted[0]?.id ?? null;
  }, [windows]);

  const closeFocused = useCallback(() => {
    const id = getFocusedId();
    if (id) closeWindow(id);
  }, [getFocusedId, closeWindow]);

  const minimizeFocused = useCallback(() => {
    const id = getFocusedId();
    if (id) minimizeWindow(id);
  }, [getFocusedId, minimizeWindow]);

  const maximizeFocused = useCallback(() => {
    const id = getFocusedId();
    if (id) maximizeWindow(id);
  }, [getFocusedId, maximizeWindow]);

  const cycleNext = useCallback(() => {
    const visible = [...windows].filter((w) => !w.minimized).sort((a, b) => b.zIndex - a.zIndex);
    if (visible.length < 2) return;
    const next = visible[1]; if (next) focusWindow(next.id);
  }, [windows, focusWindow]);

  const cyclePrev = useCallback(() => {
    const visible = [...windows].filter((w) => !w.minimized).sort((a, b) => a.zIndex - b.zIndex);
    if (visible.length < 2) return;
    const prev = visible[0]; if (prev) focusWindow(prev.id);
  }, [windows, focusWindow]);

  useShortcut("Ctrl+Space", toggleSearch, "Toggle search palette", "system");
  useShortcut("Ctrl+l", toggleLaunchpad, "Toggle launchpad", "system");
  useShortcut("Ctrl+w", closeFocused, "Close focused window", "system");
  useShortcut("Ctrl+m", minimizeFocused, "Minimize focused window", "system");
  useShortcut("Ctrl+f", maximizeFocused, "Maximize/restore focused window", "system");
  useShortcut("Ctrl+Tab", cycleNext, "Cycle to next window", "system");
  useShortcut("Ctrl+Shift+Tab", cyclePrev, "Cycle to previous window", "system");

  // Ctrl+1 through Ctrl+9 — open/focus Nth pinned dock app
  const openPinned = useCallback((n: number) => {
    const appId = pinned[n];
    if (!appId) return;
    const app = getApp(appId);
    if (app) openWindow(appId, app.defaultSize);
  }, [pinned, openWindow]);

  useShortcut("Ctrl+1", useCallback(() => openPinned(0), [openPinned]), "Open pinned app 1", "system");
  useShortcut("Ctrl+2", useCallback(() => openPinned(1), [openPinned]), "Open pinned app 2", "system");
  useShortcut("Ctrl+3", useCallback(() => openPinned(2), [openPinned]), "Open pinned app 3", "system");
  useShortcut("Ctrl+4", useCallback(() => openPinned(3), [openPinned]), "Open pinned app 4", "system");
  useShortcut("Ctrl+5", useCallback(() => openPinned(4), [openPinned]), "Open pinned app 5", "system");
  useShortcut("Ctrl+6", useCallback(() => openPinned(5), [openPinned]), "Open pinned app 6", "system");
  useShortcut("Ctrl+7", useCallback(() => openPinned(6), [openPinned]), "Open pinned app 7", "system");
  useShortcut("Ctrl+8", useCallback(() => openPinned(7), [openPinned]), "Open pinned app 8", "system");
  useShortcut("Ctrl+9", useCallback(() => openPinned(8), [openPinned]), "Open pinned app 9", "system");

  return null;
}

const CATEGORY_GRADIENTS: Record<string, string> = {
  platform: "linear-gradient(135deg, rgba(102,126,234,0.25), rgba(118,75,162,0.15))",
  os: "linear-gradient(135deg, rgba(67,233,123,0.2), rgba(56,249,215,0.1))",
  game: "linear-gradient(135deg, rgba(250,112,154,0.2), rgba(254,225,64,0.1))",
  streaming: "linear-gradient(135deg, rgba(79,172,254,0.2), rgba(0,242,254,0.1))",
};

function resolveIcon(iconName: string): icons.LucideIcon {
  const key = iconName
    .split("-")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join("") as keyof typeof icons;
  return (icons[key] as icons.LucideIcon) ?? icons.HelpCircle;
}

export function App() {
  const [launched, setLaunched] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
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

  useSessionPersistence();

  // Welcome notification — shown once per install, gated on a
  // localStorage flag so reload / refresh / re-mount don't replay it.
  // Users can re-trigger by clearing the flag from devtools.
  useEffect(() => {
    const WELCOME_FLAG = "taos.welcome.shown";
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(WELCOME_FLAG)) return;
    useNotificationStore.getState().addNotification({
      source: "system",
      title: "Welcome to taOS",
      body: "Click the bell to see notifications from your agents",
      level: "info",
    });
    window.localStorage.setItem(WELCOME_FLAG, "1");
  }, []);

  // Track fullscreen state for the "Return to fullscreen" pill
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

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
      <ShortcutProvider>
        <SystemShortcuts toggleSearch={toggleSearch} toggleLaunchpad={toggleLaunchpad} />
        <LoginGate>
          {!launched && <LoginScreen onLaunch={() => setLaunched(true)} />}
          {launched && !isFullscreen && (
            <button
              onClick={() => document.documentElement.requestFullscreen().catch(() => {})}
              className="fixed top-2 left-1/2 -translate-x-1/2 z-[9998] px-4 py-1.5 rounded-full bg-accent/90 text-white text-xs font-medium shadow-lg hover:bg-accent transition-colors"
              aria-label="Return to fullscreen"
            >
              Return to fullscreen
            </button>
          )}
          <div className={`transition-all duration-500 ${launched ? "opacity-100 scale-100" : "opacity-0 scale-95"}`}>
            <div className="h-screen w-screen flex flex-col overflow-hidden bg-shell-bg text-shell-text">
              <TopBar onSearchOpen={toggleSearch} />
              <Desktop />
              <Dock onLaunchpadOpen={toggleLaunchpad} />
              <Launchpad open={launchpadOpen} onClose={() => setLaunchpadOpen(false)} onOpenApp={(wid) => setActiveWindowId(wid)} />
              <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} onOpenApp={(wid) => setActiveWindowId(wid)} />
              <NotificationToasts />
              <NotificationCentre />
            </div>
          </div>
        </LoginGate>
      </ShortcutProvider>
    );
  }

  // Mobile/Tablet layout
  return (
    <ShortcutProvider>
      <SystemShortcuts toggleSearch={toggleSearch} toggleLaunchpad={toggleLaunchpad} />
      <LoginGate>
        {!launched && <LoginScreen onLaunch={() => setLaunched(true)} />}
        {launched && !isFullscreen && (
          <button
            onClick={() => document.documentElement.requestFullscreen().catch(() => {})}
            className="fixed top-2 left-1/2 -translate-x-1/2 z-[9998] px-4 py-1.5 rounded-full bg-accent/90 text-white text-xs font-medium shadow-lg hover:bg-accent transition-colors"
            aria-label="Return to fullscreen"
          >
            Return to fullscreen
          </button>
        )}
    <div
      className={`h-screen w-screen flex flex-col overflow-hidden text-shell-text transition-all duration-500 ${launched ? "opacity-100 scale-100" : "opacity-0 scale-95"}`}
      style={{ background: wallpaperStyle }}
    >
      <MobileTopBar
        currentAppName={activeApp?.name ?? null}
        onBack={handleMobileBack}
      />
      <div className="flex-1 relative overflow-hidden" style={{ paddingBottom: "calc(40px + env(safe-area-inset-bottom, 0px) * 0.35)" }}>
        {activeWindowId && activeWindow ? (
          <MobileApp appId={activeWindow.appId} windowId={activeWindowId} />
        ) : (
          <div className="h-full overflow-y-auto" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 32px)" }}>
            {/* iOS-style home grid */}
            <div className="px-6 pb-8">
              <div className="grid grid-cols-4 gap-x-4 gap-y-7 max-w-sm mx-auto">
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
                        <div className="w-[60px] h-[60px] rounded-[16px] flex items-center justify-center shadow-lg"
                          style={{
                            background: CATEGORY_GRADIENTS[app.category] ?? "rgba(255,255,255,0.08)",
                            backdropFilter: "blur(10px)",
                            WebkitBackdropFilter: "blur(10px)",
                            border: "1px solid rgba(255,255,255,0.08)",
                          }}
                        >
                          <Icon size={26} className="text-white/80" />
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
        onSearch={() => setSearchOpen(true)}
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
      <Launchpad open={launchpadOpen} onClose={() => setLaunchpadOpen(false)} onOpenApp={(wid) => setActiveWindowId(wid)} />
      <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} onOpenApp={(wid) => setActiveWindowId(wid)} />
      <NotificationToasts />
      <NotificationCentre />
    </div>
      </LoginGate>
    </ShortcutProvider>
  );
}
