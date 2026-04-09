import { useCallback, useRef } from "react";
import { Rnd } from "react-rnd";
import { useProcessStore, type WindowState, type SnapPosition } from "@/stores/process-store";
import { getApp } from "@/registry/app-registry";
import { getSnapBounds } from "@/hooks/use-snap-zones";
import { WindowContent } from "./WindowContent";

interface Props {
  win: WindowState;
  onDrag: (x: number, y: number) => void;
  onDragStop: () => SnapPosition;
}

export function Window({ win, onDrag, onDragStop }: Props) {
  const { focusWindow, closeWindow, minimizeWindow, maximizeWindow, updatePosition, updateSize, snapWindow } =
    useProcessStore();
  const app = getApp(win.appId);
  const preSnapRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);

  const viewport = {
    width: window.innerWidth,
    height: window.innerHeight,
    topBarH: 32,
    dockH: 64,
  };

  let displayPos = win.position;
  let displaySize = win.size;

  if (win.maximized) {
    displayPos = { x: 0, y: viewport.topBarH };
    displaySize = { w: viewport.width, h: viewport.height - viewport.topBarH - viewport.dockH };
  } else if (win.snapped) {
    const snapBounds = getSnapBounds(win.snapped, viewport);
    if (snapBounds) {
      displayPos = { x: snapBounds.x, y: snapBounds.y };
      displaySize = { w: snapBounds.w, h: snapBounds.h };
    }
  }

  const handleDragStart = useCallback(() => {
    focusWindow(win.id);
    if (win.snapped) {
      preSnapRef.current = { ...win.position, ...win.size };
      snapWindow(win.id, null);
    }
  }, [focusWindow, snapWindow, win.id, win.snapped, win.position, win.size]);

  const handleDrag = useCallback(
    (_e: unknown, d: { x: number; y: number }) => {
      onDrag(d.x, d.y);
    },
    [onDrag],
  );

  const handleDragStop = useCallback(
    (_e: unknown, d: { x: number; y: number }) => {
      const snap = onDragStop();
      if (snap) {
        preSnapRef.current = { x: d.x, y: d.y, w: win.size.w, h: win.size.h };
        snapWindow(win.id, snap);
      } else {
        updatePosition(win.id, d.x, d.y);
      }
    },
    [onDragStop, snapWindow, updatePosition, win.id, win.size],
  );

  const handleResizeStop = useCallback(
    (_e: unknown, _dir: unknown, ref: HTMLElement) => {
      updateSize(win.id, ref.offsetWidth, ref.offsetHeight);
    },
    [updateSize, win.id],
  );

  if (win.minimized) return null;

  const minSize = app?.minSize ?? { w: 300, h: 200 };

  return (
    <Rnd
      position={{ x: displayPos.x, y: displayPos.y }}
      size={{ width: displaySize.w, height: displaySize.h }}
      minWidth={minSize.w}
      minHeight={minSize.h}
      style={{ zIndex: win.zIndex }}
      dragHandleClassName="window-titlebar"
      disableDragging={win.maximized}
      enableResizing={!win.maximized && !win.snapped}
      onDragStart={handleDragStart}
      onDrag={handleDrag}
      onDragStop={handleDragStop}
      onResizeStop={handleResizeStop}
      onMouseDown={() => focusWindow(win.id)}
      bounds="parent"
    >
      <div
        className={`flex flex-col h-full rounded-[var(--spacing-window-radius)] overflow-hidden border ${
          win.focused
            ? "border-shell-border-strong shadow-[var(--shadow-window)]"
            : "border-shell-border shadow-[var(--shadow-window-unfocused)]"
        }`}
        style={{ backgroundColor: "var(--color-shell-bg)" }}
      >
        {/* Titlebar */}
        <div className="window-titlebar flex items-center h-8 px-3 shrink-0 bg-shell-surface select-none cursor-default">
          <div className="flex gap-1.5 items-center group">
            <button
              className="w-3 h-3 rounded-full bg-traffic-close hover:brightness-110"
              onClick={(e) => { e.stopPropagation(); closeWindow(win.id); }}
              aria-label="Close window"
            />
            <button
              className="w-3 h-3 rounded-full bg-traffic-minimize hover:brightness-110"
              onClick={(e) => { e.stopPropagation(); minimizeWindow(win.id); }}
              aria-label="Minimize window"
            />
            <button
              className="w-3 h-3 rounded-full bg-traffic-maximize hover:brightness-110"
              onClick={(e) => { e.stopPropagation(); maximizeWindow(win.id); }}
              aria-label="Maximize window"
            />
          </div>
          <div className="flex-1 text-center text-xs text-shell-text-secondary truncate">
            {app?.name ?? win.appId}
          </div>
          <div className="w-12" />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto bg-shell-bg-deep">
          <WindowContent appId={win.appId} windowId={win.id} />
        </div>
      </div>
    </Rnd>
  );
}
