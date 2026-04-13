import { Search, Bell } from "lucide-react";
import { useNotificationStore } from "@/stores/notification-store";
import { StatusIndicators } from "../StatusIndicators";

interface Props {
  onHome: () => void;
  onSearch: () => void;
}

export function MobileTopBar({ onHome, onSearch }: Props) {
  const unreadCount = useNotificationStore((s) => s.notifications.filter((n) => !n.read).length);
  const toggleCentre = useNotificationStore((s) => s.toggleCentre);

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
        className="flex items-center px-2"
        style={{ height: 44 }}
      >
        {/* Left — taOS (tap to go home) */}
        <button
          onClick={onHome}
          className="px-2 py-1 active:opacity-60 transition-opacity"
          aria-label="Go to home screen"
        >
          <span className="text-[17px] font-semibold text-shell-text">taOS</span>
        </button>

        {/* Centre — status indicators */}
        <div className="flex-1 flex items-center justify-center">
          <StatusIndicators compact />
        </div>

        {/* Right — glass buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={onSearch}
            className="relative flex items-center justify-center active:opacity-60 transition-opacity"
            style={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              background: "rgba(255,255,255,0.08)",
              backdropFilter: "blur(10px)",
              WebkitBackdropFilter: "blur(10px)",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
            aria-label="Search"
          >
            <Search size={15} className="text-white/70" />
          </button>
          <button
            onClick={toggleCentre}
            className="relative flex items-center justify-center active:opacity-60 transition-opacity"
            style={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              background: "rgba(255,255,255,0.08)",
              backdropFilter: "blur(10px)",
              WebkitBackdropFilter: "blur(10px)",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
            aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
          >
            <Bell size={15} className="text-white/70" />
            {unreadCount > 0 && (
              <span
                className="absolute bg-red-500 rounded-full"
                style={{ width: 6, height: 6, top: 5, right: 5 }}
              />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
