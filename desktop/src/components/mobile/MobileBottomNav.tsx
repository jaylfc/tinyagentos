import { ChevronLeft, Search, LayoutGrid, Layers } from "lucide-react";

interface Props {
  onBack: () => void;
  onHome: () => void;
  onSearch: () => void;
  onSwitcher: () => void;
  hasActiveApp: boolean;
}

export function MobileBottomNav({ onBack, onHome, onSearch, onSwitcher, hasActiveApp }: Props) {
  return (
    <nav
      className="shrink-0 flex items-center justify-around relative"
      style={{
        height: "calc(52px + env(safe-area-inset-bottom, 0px))",
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
        backgroundColor: "rgba(20, 20, 42, 0.98)",
        borderTop: "1px solid rgba(255, 255, 255, 0.1)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        zIndex: 9500,
      }}
      aria-label="Navigation"
    >
      <button
        onClick={onBack}
        className={`flex flex-col items-center justify-center w-16 h-12 rounded-lg active:bg-white/10 transition-colors ${hasActiveApp ? "text-white/70" : "text-white/30"}`}
        aria-label="Back"
        disabled={!hasActiveApp}
      >
        <ChevronLeft size={22} />
        <span className="text-[10px] mt-0.5">Back</span>
      </button>

      <button
        onClick={onHome}
        className="flex flex-col items-center justify-center w-16 h-12 rounded-lg active:bg-white/10 transition-colors text-white/70"
        aria-label="Home"
      >
        <LayoutGrid size={20} />
        <span className="text-[10px] mt-0.5">Menu</span>
      </button>

      <button
        onClick={onSearch}
        className="flex flex-col items-center justify-center w-16 h-12 rounded-lg active:bg-white/10 transition-colors text-white/70"
        aria-label="Search"
      >
        <Search size={20} />
        <span className="text-[10px] mt-0.5">Search</span>
      </button>

      <button
        onClick={onSwitcher}
        className="flex flex-col items-center justify-center w-16 h-12 rounded-lg active:bg-white/10 transition-colors text-white/70"
        aria-label="App Switcher"
      >
        <Layers size={20} />
        <span className="text-[10px] mt-0.5">Apps</span>
      </button>
    </nav>
  );
}
