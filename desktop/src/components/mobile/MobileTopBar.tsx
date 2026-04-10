import { ChevronLeft, Bell } from "lucide-react";
import { useClock } from "@/hooks/use-clock";

interface Props {
  currentAppName: string | null;
  onBack: () => void;
}

export function MobileTopBar({ currentAppName, onBack }: Props) {
  const clockFull = useClock();
  // Extract just HH:MM from the formatted string (time is after the double space)
  const time = clockFull.split("  ").pop() ?? "";

  return (
    <div
      className="shrink-0"
      style={{
        backgroundColor: "var(--color-shell-surface)",
        borderBottom: "1px solid var(--color-shell-border, rgba(255,255,255,0.08))",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        paddingTop: "env(safe-area-inset-top, 0px)",
      }}
    >
    <div
      className="flex items-center justify-between px-3"
      style={{ height: 28 }}
    >
      {/* Left */}
      <div className="flex items-center gap-1.5 min-w-0 flex-1">
        {currentAppName ? (
          <button
            onClick={onBack}
            className="flex items-center gap-0.5 text-shell-text-secondary hover:text-shell-text transition-colors"
            aria-label="Go back to home"
          >
            <ChevronLeft size={14} />
            <span className="text-[11px]">Back</span>
          </button>
        ) : (
          <div className="flex items-center gap-1.5">
            <div
              className="rounded-sm"
              style={{
                width: 10,
                height: 10,
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              }}
            />
            <span className="text-[11px] font-medium text-shell-text">
              TinyAgentOS
            </span>
          </div>
        )}
      </div>

      {/* Centre */}
      <div className="flex-1 text-center">
        {currentAppName && (
          <span className="text-[11px] font-medium text-shell-text truncate">
            {currentAppName}
          </span>
        )}
      </div>

      {/* Right */}
      <div className="flex items-center gap-2 flex-1 justify-end">
        <span className="text-[11px] text-shell-text-secondary tabular-nums">
          {time}
        </span>
        <Bell size={12} className="text-shell-text-secondary" />
      </div>
    </div>
    </div>
  );
}
