import { useEffect, useRef, useState } from "react";
import type { AttachmentRecord } from "@/lib/chat-attachments-api";

type Msg = {
  id: string;
  author_id: string;
  content: string;
  created_at?: number;
  [key: string]: unknown;
};

export function ThreadPanel({
  channelId,
  parentId,
  onClose,
  onSend,
}: {
  channelId: string;
  parentId: string;
  onClose: () => void;
  onSend: (content: string, attachments: AttachmentRecord[]) => Promise<void>;
}) {
  const [parent, setParent] = useState<Msg | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    fetch(`/api/chat/messages/${parentId}`)
      .then((r) => r.json())
      .then((d) => { if (alive) setParent(d); });
    return () => { alive = false; };
  }, [parentId]);

  useEffect(() => {
    let alive = true;
    fetch(`/api/chat/channels/${channelId}/threads/${parentId}/messages`)
      .then((r) => r.json())
      .then((d) => { if (alive) setMsgs(d.messages || []); });
    return () => { alive = false; };
  }, [channelId, parentId]);

  async function submit() {
    const content = input.trim();
    if (!content) return;
    setInput("");
    await onSend(content, []);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div
      className="fixed top-0 right-0 h-full w-[360px] bg-shell-surface border-l border-white/10 flex flex-col z-40"
      role="complementary"
      aria-label="Thread panel"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <span className="font-semibold text-sm">Thread</span>
        <button
          aria-label="Close thread"
          onClick={onClose}
          className="p-1 hover:bg-white/5 rounded"
        >✕</button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
        {parent && (
          <div className="pb-3 border-b border-white/10">
            <div className="text-xs text-white/50 mb-1">{parent.author_id}</div>
            <div className="text-sm">{parent.content}</div>
          </div>
        )}
        {msgs.map((m) => (
          <div key={m.id}>
            <div className="text-xs text-white/50 mb-0.5">{m.author_id}</div>
            <div className="text-sm">{m.content}</div>
          </div>
        ))}
      </div>

      <div className="px-4 py-3 border-t border-white/10">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Reply in thread…"
          aria-label="Thread reply"
          rows={2}
          className="w-full bg-white/5 rounded px-3 py-2 text-sm resize-none outline-none border border-white/10 focus:border-sky-400"
        />
      </div>
    </div>
  );
}
