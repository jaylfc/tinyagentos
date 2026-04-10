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
      className="fixed bottom-0 left-0 right-0 z-[9999] flex items-center px-4"
      style={{
        // Flex + items-center = icons vertically centred in the full bar height.
        // Solid background (no alpha) so no wallpaper bleed-through.
        // Bar extends all the way down to the physical screen edge.
        height: "calc(48px + env(safe-area-inset-bottom, 0px))",
        backgroundColor: "#14142a",
        borderTop: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {/* Left — back button */}
      <div className="flex-1 flex justify-start">
        <button
          onClick={onBack}
          className="flex items-center justify-center w-9 h-9 rounded-lg active:bg-white/10 transition-colors"
          aria-label="Go back"
        >
          <ChevronLeft size={20} className="text-white/60" />
        </button>
      </div>

      {/* Centre — pill handle */}
      <div className="flex-1 flex justify-center">
        <div
          ref={pillRef}
          className="cursor-pointer select-none"
          style={{
            width: 120,
            height: 5,
            borderRadius: 9999,
            backgroundColor: "rgba(255, 255, 255, 0.35)",
            transition: "transform 150ms ease, background-color 150ms ease",
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
      </div>

      {/* Right — notifications */}
      <div className="flex-1 flex justify-end">
        <button
          onClick={toggleCentre}
          className="relative flex items-center justify-center w-9 h-9 rounded-lg active:bg-white/10 transition-colors"
          aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
        >
          <Bell size={20} className="text-white/60" />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
          )}
        </button>
      </div>
    </div>
  );
}
