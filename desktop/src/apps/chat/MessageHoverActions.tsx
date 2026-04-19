export function MessageHoverActions({
  onReact,
  onReplyInThread,
  onMore,
}: {
  onReact: () => void;
  onReplyInThread: () => void;
  onMore: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      role="toolbar"
      aria-label="Message actions"
      className="inline-flex items-center gap-0.5 bg-shell-surface border border-white/10 rounded-md shadow-sm px-1"
    >
      <button aria-label="Add reaction" onClick={onReact} className="p-1 hover:bg-white/5">😀</button>
      <button aria-label="Reply in thread" onClick={onReplyInThread} className="p-1 hover:bg-white/5">💬</button>
      <button aria-label="More" onClick={onMore} className="p-1 hover:bg-white/5">⋯</button>
    </div>
  );
}
