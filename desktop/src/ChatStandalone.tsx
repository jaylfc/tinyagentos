import { Suspense, lazy } from "react";
import { useThemeStore } from "@/stores/theme-store";

const MessagesApp = lazy(() => import("./apps/MessagesApp").then((m) => ({ default: m.MessagesApp })));

export function ChatStandalone() {
  const wallpaperImage = useThemeStore((s) => s.wallpaperImage);
  const wallpaperFallback = useThemeStore((s) => s.wallpaperFallback);

  return (
    <div
      className="taos-wallpaper h-screen w-screen flex flex-col overflow-hidden text-shell-text"
      style={{ backgroundImage: wallpaperImage, backgroundColor: wallpaperFallback, paddingTop: "env(safe-area-inset-top, 0px)" }}
    >
      <Suspense fallback={
        <div className="flex items-center justify-center h-full text-shell-text-tertiary">
          Loading chat...
        </div>
      }>
        <MessagesApp windowId="standalone-chat" />
      </Suspense>
    </div>
  );
}
