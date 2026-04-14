import { Suspense, lazy } from "react";
import { useThemeStore } from "@/stores/theme-store";

const MessagesApp = lazy(() => import("./apps/MessagesApp").then((m) => ({ default: m.MessagesApp })));

export function ChatStandalone() {
  const wallpaperImage = useThemeStore((s) => s.wallpaperImage);
  const wallpaperMobileImage = useThemeStore((s) => s.wallpaperMobileImage);
  const wallpaperFallback = useThemeStore((s) => s.wallpaperFallback);

  return (
    <div
      className="taos-wallpaper h-screen w-screen flex flex-col overflow-hidden text-shell-text"
      style={{ backgroundColor: wallpaperFallback, paddingTop: "env(safe-area-inset-top, 0px)", ["--wallpaper-desktop" as never]: wallpaperImage, ["--wallpaper-mobile" as never]: wallpaperMobileImage }}
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
