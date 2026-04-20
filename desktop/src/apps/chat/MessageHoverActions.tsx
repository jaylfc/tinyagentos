export function MessageHoverActions({
  onReact,
  onReplyInThread,
  onOverflow,
  dragHandle,
}: {
  onReact: () => void;
  onReplyInThread: () => void;
  onOverflow: (e: React.MouseEvent) => void;
  dragHandle?: React.ReactNode;
}) {
  return (
    <div
      role="toolbar"
      aria-label="Message actions"
      className="inline-flex items-center gap-0.5 bg-shell-surface border border-white/10 rounded-md shadow-sm px-1"
    >
      {dragHandle}
      <button aria-label="Add reaction" onClick={onReact} className="p-1 hover:bg-white/5">😀</button>
      <button aria-label="Reply in thread" onClick={onReplyInThread} className="p-1 hover:bg-white/5">💬</button>
      <button aria-label="More" onClick={onOverflow} className="p-1 hover:bg-white/5">⋯</button>
    </div>
  );
}
