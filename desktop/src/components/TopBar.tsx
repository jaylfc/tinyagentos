import { Bell, Search } from "lucide-react";
import { useClock } from "@/hooks/use-clock";

interface Props {
  onSearchOpen: () => void;
}

export function TopBar({ onSearchOpen }: Props) {
  const clock = useClock();

  return (
    <div
      className="flex items-center justify-between px-4 shrink-0 select-none"
      style={{
        height: "var(--spacing-topbar-h)",
        backgroundColor: "var(--color-shell-surface)",
        borderBottom: "1px solid var(--color-shell-border)",
      }}
    >
      <div className="flex items-center gap-2">
        <div className="w-4 h-4 rounded bg-accent" />
        <span className="text-xs font-medium text-shell-text-secondary">TinyAgentOS</span>
      </div>

      <button
        onClick={onSearchOpen}
        className="flex items-center gap-2 px-3 py-1 rounded-md bg-shell-surface-hover text-shell-text-tertiary text-xs hover:bg-shell-surface-active transition-colors"
        aria-label="Search"
      >
        <Search size={12} />
        <span>Search</span>
        <kbd className="ml-2 text-[10px] opacity-50">Ctrl+Space</kbd>
      </button>

      <div className="flex items-center gap-3">
        <span className="text-xs text-shell-text-tertiary">{clock}</span>
        <button className="relative p-1 rounded hover:bg-shell-surface-hover transition-colors" aria-label="Notifications">
          <Bell size={14} className="text-shell-text-secondary" />
        </button>
      </div>
    </div>
  );
}
