export interface PinnedMessage {
  id: string;
  author_id: string;
  content: string;
  created_at: number;
  pinned_by: string;
  pinned_at: number;
}

export function PinnedMessagesPopover({
  pins, onJumpTo, onClose,
}: {
  pins: PinnedMessage[];
  onJumpTo: (messageId: string) => void;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-label="Pinned messages"
      className="absolute top-full right-0 mt-1 w-[320px] max-h-[400px] overflow-y-auto bg-shell-surface border border-white/10 rounded-md shadow-lg z-40"
    >
      <header className="flex items-center justify-between px-3 py-2 border-b border-white/10">
        <span className="text-xs font-semibold">Pinned ({pins.length})</span>
        <button onClick={onClose} aria-label="Close" className="text-sm opacity-70 hover:opacity-100">×</button>
      </header>
      {pins.length === 0 ? (
        <div className="p-4 text-sm text-white/50">No pinned messages yet.</div>
      ) : (
        <ul className="divide-y divide-white/5">
          {pins.map((p) => (
            <li key={p.id} className="p-2 text-sm">
              <div className="text-xs opacity-60 mb-0.5">@{p.author_id}</div>
              <div className="line-clamp-2">{p.content}</div>
              <button
                onClick={() => onJumpTo(p.id)}
                className="mt-1 text-xs text-sky-300 hover:text-sky-200"
              >Jump to →</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
