import { useState, useMemo } from "react";
import { Search, X } from "lucide-react";
import { getAllApps, getApp } from "@/registry/app-registry";
import { useProcessStore } from "@/stores/process-store";
import { LaunchpadIcon } from "./LaunchpadIcon";

interface Props {
  open: boolean;
  onClose: () => void;
  onOpenApp?: (windowId: string) => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  platform: "Platform",
  os: "Utilities",
  streaming: "Streaming Apps",
  game: "Games",
};

export function Launchpad({ open, onClose, onOpenApp }: Props) {
  const [query, setQuery] = useState("");
  const { openWindow } = useProcessStore();

  const apps = useMemo(() => {
    const all = getAllApps();
    if (!query.trim()) return all;
    const q = query.toLowerCase();
    return all.filter((a) => a.name.toLowerCase().includes(q));
  }, [query]);

  const grouped = useMemo(() => {
    const groups: Record<string, typeof apps> = {};
    for (const app of apps) {
      (groups[app.category] ??= []).push(app);
    }
    return groups;
  }, [apps]);

  const handleLaunch = (appId: string) => {
    const app = getApp(appId);
    if (app) {
      const wid = openWindow(appId, app.defaultSize);
      onOpenApp?.(wid);
    }
    onClose();
    setQuery("");
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[10000] flex flex-col items-center backdrop-blur-md bg-black/40"
      onClick={onClose}
    >
      <div className="w-full max-w-3xl mt-16 px-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 py-2 mb-8 rounded-xl bg-white/10 border border-white/10">
          <Search size={16} className="text-shell-text-tertiary" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search apps..."
            className="flex-1 bg-transparent text-sm text-shell-text outline-none placeholder:text-shell-text-tertiary"
            autoFocus
          />
          {query && (
            <button onClick={() => setQuery("")} aria-label="Clear search">
              <X size={14} className="text-shell-text-tertiary" />
            </button>
          )}
        </div>

        <div className="max-h-[60vh] overflow-y-auto space-y-8">
          {Object.entries(grouped).map(([category, categoryApps]) => (
            <div key={category}>
              <h3 className="text-xs font-medium text-shell-text-tertiary uppercase tracking-wide mb-3 px-1">
                {CATEGORY_LABELS[category] ?? category}
              </h3>
              <div className="grid grid-cols-6 gap-2">
                {categoryApps.map((app) => (
                  <LaunchpadIcon key={app.id} app={app} onClick={() => handleLaunch(app.id)} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
