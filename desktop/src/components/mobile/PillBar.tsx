import { useRef, useCallback } from "react";
import { ChevronLeft, Bell } from "lucide-react";
import { useNotificationStore } from "@/stores/notification-store";

interface Props {
  onHome: () => void;
  onCardSwitcher: () => void;
  onBack: () => void;
}

export function PillBar({ onHome, onCardSwitcher, onBack }: Props) {
  const startY = useRef<number | null>(null);
  const pillRef = useRef<HTMLDivElement>(null);
  const unreadCount = useNotificationStore((s) => s.notifications.filter((n) => !n.read).length);
  const toggleCentre = useNotificationStore((s) => s.toggleCentre);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    e.preventDefault();
    startY.current = e.touches[0].clientY;
    if (pillRef.current) {
      pillRef.current.style.transform = "scale(1.15)";
    }
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    e.preventDefault();
  }, []);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (pillRef.current) {
        pillRef.current.style.transform = "scale(1)";
      }
      if (startY.current === null) return;

      const endY = e.changedTouches[0].clientY;
      const deltaY = endY - startY.current;
      startY.current = null;

      if (deltaY < -60) {
        onCardSwitcher();
      } else {
        onHome();
      }
    },
    [onCardSwitcher, onHome]
  );

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-[9999]"
      style={{
        backgroundColor: "var(--color-dock-bg)",
        borderTop: "1px solid var(--color-dock-border)",
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
      }}
    >
    <div
      className="flex items-center justify-between px-4"
      style={{ height: 48 }}
    >
      <button
        onClick={onBack}
        className="flex items-center justify-center w-10 h-10 rounded-lg bg-white/5 active:bg-white/10 transition-colors"
        aria-label="Go back"
      >
        <ChevronLeft size={20} className="text-white/70" />
      </button>

      <div
        ref={pillRef}
        className="flex items-center justify-center cursor-pointer select-none"
        style={{
          width: 32,
          height: 5,
          borderRadius: 9999,
          backgroundColor: "rgba(255, 255, 255, 0.3)",
          transition: "transform 150ms ease",
          touchAction: "none",
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onClick={onHome}
        role="button"
        aria-label="Home. Swipe up for app switcher."
        tabIndex={0}
      />

      <button
        onClick={toggleCentre}
        className="relative flex items-center justify-center w-10 h-10 rounded-lg bg-white/5 active:bg-white/10 transition-colors"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
      >
        <Bell size={20} className="text-white/70" />
        {unreadCount > 0 && (
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
        )}
      </button>
    </div>
    </div>
  );
}
