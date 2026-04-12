import { ChevronLeft, Bell } from "lucide-react";
import { useNotificationStore } from "@/stores/notification-store";
import { StatusIndicators } from "../StatusIndicators";

interface Props {
  currentAppName: string | null;
  onBack: () => void;
}

export function MobileTopBar({ currentAppName, onBack }: Props) {
  const unreadCount = useNotificationStore((s) => s.notifications.filter((n) => !n.read).length);
  const toggleCentre = useNotificationStore((s) => s.toggleCentre);

  const isHome = !currentAppName;

  return (
    <div
      className="shrink-0"
      style={{
        backgroundColor: "rgba(26, 27, 46, 0.85)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        paddingTop: "env(safe-area-inset-top, 0px)",
      }}
    >
      <div
        className="flex items-center px-1"
        style={{ height: 44 }}
      >
        {/* Left — back button (in app) or logo (home) */}
        {isHome ? (
          <div className="flex items-center gap-2 px-2 min-w-[60px]">
            <img src="/static/taos-logo.png" alt="taOS" className="h-4 w-auto" />
          </div>
        ) : (
          <button
            onClick={onBack}
            className="flex items-center gap-0 px-2 py-2 text-accent active:opacity-60 transition-opacity min-w-[60px]"
            aria-label="Go back to home"
          >
            <ChevronLeft size={20} strokeWidth={2.5} />
            <span className="text-[15px]">Back</span>
          </button>
        )}

        {/* Centre — app name or taOS */}
        <div className="flex-1 text-center">
          <span className="text-[17px] font-semibold text-shell-text">
            {isHome ? "taOS" : currentAppName}
          </span>
        </div>

        {/* Right — indicators + notifications bell */}
        <div className="flex items-center justify-end gap-1" style={{ minWidth: 60 }}>
          <StatusIndicators compact />
          <button
            onClick={toggleCentre}
            className="relative flex items-center justify-center w-10 h-10 rounded-lg active:bg-white/10 transition-colors"
            aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
          >
            <Bell size={20} className="text-white/70" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
