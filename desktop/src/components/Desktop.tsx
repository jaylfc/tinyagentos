import { useProcessStore } from "@/stores/process-store";
import { useSnapZones } from "@/hooks/use-snap-zones";
import { Window } from "./Window";
import { SnapOverlay } from "./SnapOverlay";

export function Desktop() {
  const windows = useProcessStore((s) => s.windows);

  const viewport = {
    width: typeof window !== "undefined" ? window.innerWidth : 1920,
    height: typeof window !== "undefined" ? window.innerHeight : 1080,
    topBarH: 32,
    dockH: 64,
  };

  const { previewBounds, onDrag, onDragStop } = useSnapZones(viewport);

  return (
    <div
      className="relative flex-1 overflow-hidden"
      style={{
        background: "linear-gradient(160deg, #1a1b2e 0%, #1e2140 40%, #252848 100%)",
      }}
    >
      <SnapOverlay bounds={previewBounds} />
      {windows.map((win) => (
        <Window key={win.id} win={win} onDrag={onDrag} onDragStop={onDragStop} />
      ))}
    </div>
  );
}
