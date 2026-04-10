import { ChevronLeft } from "lucide-react";

interface Props {
  currentAppName: string | null;
  onBack: () => void;
}

export function MobileTopBar({ currentAppName, onBack }: Props) {
  // No bar when on home screen — let iOS status bar stand alone
  if (!currentAppName) return null;

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
        {/* Back button — iOS style */}
        <button
          onClick={onBack}
          className="flex items-center gap-0 px-2 py-2 text-accent active:opacity-60 transition-opacity min-w-[60px]"
          aria-label="Go back to home"
        >
          <ChevronLeft size={20} strokeWidth={2.5} />
          <span className="text-[15px]">Back</span>
        </button>

        {/* Centre — app name */}
        <div className="flex-1 text-center">
          <span className="text-[17px] font-semibold text-shell-text">
            {currentAppName}
          </span>
        </div>

        {/* Right spacer to balance the back button */}
        <div style={{ minWidth: 60 }} />
      </div>
    </div>
  );
}
