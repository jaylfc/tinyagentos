import { Suspense, lazy } from "react";
import { useThemeStore } from "@/stores/theme-store";

const MessagesApp = lazy(() => import("./apps/MessagesApp").then((m) => ({ default: m.MessagesApp })));

export function ChatStandalone() {
  const wallpaperStyle = useThemeStore((s) => s.wallpaperStyle);

  return (
    <div
      className="h-screen w-screen flex flex-col overflow-hidden text-shell-text"
      style={{ background: wallpaperStyle, paddingTop: "env(safe-area-inset-top, 0px)" }}
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
