import { useEffect, useState } from "react";
import { useIsMobile } from "@/hooks/use-is-mobile";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<{ outcome: "accepted" | "dismissed" }>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISS_MS = 30 * 24 * 60 * 60 * 1000;
const KEY = "taos-install-dismissed";

export function InstallPromptBanner() {
  const isMobile = useIsMobile();
  const [event, setEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setEvent(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  if (!isMobile || !event || dismissed) return null;

  if (typeof window !== "undefined") {
    const mql = window.matchMedia("(display-mode: standalone)");
    if (mql.matches) return null;
  }

  const prev = localStorage.getItem(KEY);
  if (prev && Date.now() - Number(prev) < DISMISS_MS) return null;

  const install = async () => {
    try {
      await event.prompt();
      await event.userChoice;
    } catch {
      /* ignore */
    }
    setEvent(null);
  };

  const notNow = () => {
    localStorage.setItem(KEY, String(Date.now()));
    setDismissed(true);
  };

  return (
    <div
      role="region"
      aria-label="Install prompt"
      className="flex items-center gap-3 px-4 py-2 bg-sky-500/20 border-b border-sky-500/30 text-sm"
    >
      <span className="flex-1">Install taOS talk for quick access</span>
      <button
        onClick={install}
        className="px-3 py-1 bg-sky-500/40 text-sky-100 rounded hover:bg-sky-500/60"
      >Install</button>
      <button
        onClick={notNow}
        className="px-2 py-1 opacity-70 hover:opacity-100"
      >Not now</button>
    </div>
  );
}
