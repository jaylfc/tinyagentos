// desktop/src/apps/chat/AttachmentLightbox.tsx
import { useEffect, useState } from "react";
import type { AttachmentRecord } from "@/lib/chat-attachments-api";

export function AttachmentLightbox({
  images, startIndex, onClose,
}: {
  images: AttachmentRecord[];
  startIndex: number;
  onClose: () => void;
}) {
  const [idx, setIdx] = useState(startIndex);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") setIdx((i) => Math.min(images.length - 1, i + 1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [images.length, onClose]);

  const current = images[idx]!;
  return (
    <div
      role="dialog"
      aria-label="Image viewer"
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
      onClick={onClose}
    >
      <img src={current.url} alt={current.filename}
           className="max-w-[90vw] max-h-[90vh]"
           onClick={(e) => e.stopPropagation()} />
      <div className="absolute top-4 right-4 flex gap-2">
        <a href={current.url} download={current.filename}
           onClick={(e) => e.stopPropagation()}
           className="bg-white/10 hover:bg-white/20 rounded px-3 py-1 text-sm">Download</a>
        <button onClick={onClose} className="bg-white/10 hover:bg-white/20 rounded px-3 py-1 text-sm">Close</button>
      </div>
      {images.length > 1 && (
        <div className="absolute bottom-4 text-white/70 text-xs">{idx + 1} / {images.length}</div>
      )}
    </div>
  );
}
