import { useEffect, useRef, useState } from "react";
import Plyr from "plyr";
import "plyr/dist/plyr.css";

export function MediaPlayerApp({ windowId: _windowId }: { windowId: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<Plyr | null>(null);
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (mediaUrl) URL.revokeObjectURL(mediaUrl);

    const url = URL.createObjectURL(file);
    setMediaUrl(url);
    setFileName(file.name);
  }

  useEffect(() => {
    if (!videoRef.current || !mediaUrl) return;

    playerRef.current = new Plyr(videoRef.current, {
      controls: [
        "play-large",
        "play",
        "progress",
        "current-time",
        "mute",
        "volume",
        "fullscreen",
      ],
    });

    playerRef.current.play().catch(() => {
      // autoplay may be blocked by browser policy
    });

    return () => {
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [mediaUrl]);

  useEffect(() => {
    return () => {
      if (mediaUrl) URL.revokeObjectURL(mediaUrl);
    };
  }, [mediaUrl]);

  return (
    <div className="flex flex-col h-full bg-[#1a1a2e] select-none">
      {!mediaUrl ? (
        <div className="flex flex-col items-center justify-center flex-1 gap-4 p-8">
          <div className="text-shell-text-secondary text-lg">
            No media loaded
          </div>
          <label
            className="px-4 py-2 rounded-lg bg-accent text-white cursor-pointer hover:bg-accent/90 transition-colors"
            aria-label="Choose media file"
          >
            Open File
            <input
              type="file"
              accept="video/*,audio/*"
              onChange={handleFileSelect}
              className="hidden"
            />
          </label>
        </div>
      ) : (
        <div className="flex flex-col h-full">
          <div className="flex items-center gap-2 px-3 py-2 bg-[#12122a] border-b border-white/10">
            <span className="text-shell-text text-sm truncate flex-1">
              {fileName}
            </span>
            <label
              className="px-3 py-1 rounded text-xs bg-shell-surface text-shell-text-secondary cursor-pointer hover:bg-shell-surface/80 transition-colors"
              aria-label="Choose a different media file"
            >
              Open
              <input
                type="file"
                accept="video/*,audio/*"
                onChange={handleFileSelect}
                className="hidden"
              />
            </label>
          </div>
          <div className="flex-1 flex items-center justify-center bg-black min-h-0">
            <video
              ref={videoRef}
              src={mediaUrl}
              className="max-w-full max-h-full"
              aria-label="Media player"
            />
          </div>
        </div>
      )}
    </div>
  );
}
