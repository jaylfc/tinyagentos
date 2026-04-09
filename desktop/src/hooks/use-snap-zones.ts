import { useCallback, useState } from "react";
import type { SnapPosition } from "@/stores/process-store";

const EDGE_THRESHOLD = 16;
const CORNER_SIZE = 100;

interface Viewport {
  width: number;
  height: number;
  topBarH: number;
  dockH: number;
}

export function detectSnapZone(x: number, y: number, vp: Viewport): SnapPosition {
  const nearLeft = x <= EDGE_THRESHOLD;
  const nearRight = x >= vp.width - EDGE_THRESHOLD;
  const nearTop = y <= vp.topBarH + CORNER_SIZE;
  const nearBottom = y >= vp.height - vp.dockH - CORNER_SIZE;

  if (nearLeft && nearTop) return "top-left";
  if (nearLeft && nearBottom) return "bottom-left";
  if (nearRight && nearTop) return "top-right";
  if (nearRight && nearBottom) return "bottom-right";
  if (nearLeft) return "left";
  if (nearRight) return "right";
  return null;
}

export function getSnapBounds(snap: SnapPosition, vp: Viewport): { x: number; y: number; w: number; h: number } | null {
  if (!snap) return null;

  const usableH = vp.height - vp.topBarH - vp.dockH;
  const halfW = Math.floor(vp.width / 2);
  const halfH = Math.floor(usableH / 2);

  switch (snap) {
    case "left":
      return { x: 0, y: vp.topBarH, w: halfW, h: usableH };
    case "right":
      return { x: halfW, y: vp.topBarH, w: halfW, h: usableH };
    case "top-left":
      return { x: 0, y: vp.topBarH, w: halfW, h: halfH };
    case "top-right":
      return { x: halfW, y: vp.topBarH, w: halfW, h: halfH };
    case "bottom-left":
      return { x: 0, y: vp.topBarH + halfH, w: halfW, h: halfH };
    case "bottom-right":
      return { x: halfW, y: vp.topBarH + halfH, w: halfW, h: halfH };
  }
}

export function useSnapZones(viewport: Viewport) {
  const [preview, setPreview] = useState<SnapPosition>(null);

  const onDrag = useCallback((x: number, y: number) => {
    setPreview(detectSnapZone(x, y, viewport));
  }, [viewport]);

  const onDragStop = useCallback(() => {
    const result = preview;
    setPreview(null);
    return result;
  }, [preview]);

  return { preview, previewBounds: getSnapBounds(preview, viewport), onDrag, onDragStop };
}
