import React from "react";
import * as icons from "lucide-react";
import { useMobileHomeStore, type HomePage } from "@/stores/mobile-home-store";
import { getApp } from "@/registry/app-registry";
import { GreetingWidget } from "@/components/widgets/GreetingWidget";
import { ClockWidget } from "@/components/widgets/ClockWidget";
import { AgentStatusWidget } from "@/components/widgets/AgentStatusWidget";
import { SystemStatsWidget } from "@/components/widgets/SystemStatsWidget";
import { WeatherWidget } from "@/components/widgets/WeatherWidget";
import { QuickNotesWidget } from "@/components/widgets/QuickNotesWidget";

interface Props {
  onOpenApp: (appId: string) => void;
}

const CATEGORY_GRADIENTS: Record<string, string> = {
  platform: "linear-gradient(135deg, rgba(100,80,200,0.4), rgba(60,50,140,0.6))",
  os: "linear-gradient(135deg, rgba(50,160,140,0.35), rgba(30,100,90,0.55))",
  game: "linear-gradient(135deg, rgba(200,120,50,0.35), rgba(140,70,30,0.55))",
};

function resolveIcon(iconName: string): icons.LucideIcon {
  const key = iconName
    .split("-")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join("") as keyof typeof icons;
  return (icons[key] as icons.LucideIcon) ?? icons.HelpCircle;
}

const CARD_STYLE: React.CSSProperties = {
  borderRadius: "16px",
  background: "rgba(255,255,255,0.06)",
  border: "1px solid rgba(255,255,255,0.08)",
  backdropFilter: "blur(10px)",
  WebkitBackdropFilter: "blur(10px)",
  padding: "12px",
};

function WidgetCard({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <div style={{ ...CARD_STYLE, ...style }}>{children}</div>;
}

function renderWidgetContent(widgetType: string): React.ReactNode {
  switch (widgetType) {
    case "clock":
      return <ClockWidget />;
    case "system-stats":
      return <SystemStatsWidget />;
    case "greeting":
      return <GreetingWidget />;
    case "agent-status":
      return <AgentStatusWidget />;
    case "weather":
      return <WeatherWidget />;
    case "quick-notes":
      return <QuickNotesWidget />;
    default:
      return null;
  }
}

type WidgetGroupItem = { widgetType: string; index: number };
type AppGroupItem = { appId: string; index: number };
type ItemGroup =
  | { kind: "widgets"; items: WidgetGroupItem[] }
  | { kind: "apps"; items: AppGroupItem[] };

function PageContent({ page, onOpenApp }: { page: HomePage; onOpenApp: (appId: string) => void }) {
  // Group consecutive same-type items
  const groups: ItemGroup[] = [];

  for (let i = 0; i < page.items.length; i++) {
    const item = page.items[i];
    if (!item) continue;

    if (item.type === "widget") {
      const last = groups[groups.length - 1];
      if (last?.kind === "widgets") {
        last.items.push({ widgetType: item.widgetType, index: i });
      } else {
        groups.push({ kind: "widgets", items: [{ widgetType: item.widgetType, index: i }] });
      }
    } else {
      const last = groups[groups.length - 1];
      if (last?.kind === "apps") {
        last.items.push({ appId: item.appId, index: i });
      } else {
        groups.push({ kind: "apps", items: [{ appId: item.appId, index: i }] });
      }
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {groups.map((group, gi) => {
        if (group.kind === "widgets") {
          const rendered: React.ReactNode[] = [];
          let skipNext = false;

          for (let wi = 0; wi < group.items.length; wi++) {
            if (skipNext) {
              skipNext = false;
              continue;
            }
            const cur = group.items[wi];
            const next = group.items[wi + 1];

            if (!cur) continue;

            // Greeting renders without a card — it's a hero banner
            if (cur.widgetType === "greeting") {
              rendered.push(
                <div key={cur.index}>{renderWidgetContent("greeting")}</div>
              );
              continue;
            }

            const curIsSide = cur.widgetType === "clock" || cur.widgetType === "system-stats" || cur.widgetType === "weather";
            const nextIsSide = next && (next.widgetType === "clock" || next.widgetType === "system-stats" || next.widgetType === "weather");

            if (curIsSide && nextIsSide && next) {
              rendered.push(
                <div key={`pair-${cur.index}`} style={{ display: "flex", gap: "12px" }}>
                  <WidgetCard style={{ flex: 1 }}>
                    {renderWidgetContent(cur.widgetType)}
                  </WidgetCard>
                  <WidgetCard style={{ flex: 1 }}>
                    {renderWidgetContent(next.widgetType)}
                  </WidgetCard>
                </div>
              );
              skipNext = true;
            } else {
              rendered.push(
                <WidgetCard key={cur.index}>
                  {renderWidgetContent(cur.widgetType)}
                </WidgetCard>
              );
            }
          }

          return <React.Fragment key={`wg-${gi}`}>{rendered}</React.Fragment>;
        }

        // App grid
        return (
          <div
            key={`ag-${gi}`}
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "12px",
              padding: "8px 4px",
            }}
          >
            {group.items.map(({ appId, index }) => {
              const app = getApp(appId);
              if (!app) return null;
              const Icon = resolveIcon(app.icon);
              const gradient = CATEGORY_GRADIENTS[app.category] ?? CATEGORY_GRADIENTS.platform;
              return (
                <button
                  key={index}
                  onClick={() => onOpenApp(appId)}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "6px",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                  }}
                  aria-label={app.name}
                >
                  <div
                    style={{
                      width: 60,
                      height: 60,
                      borderRadius: 16,
                      background: gradient,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <Icon size={26} color="rgba(255,255,255,0.9)" />
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      color: "rgba(255,255,255,0.8)",
                      textAlign: "center",
                      lineHeight: 1.2,
                      maxWidth: 64,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {app.name}
                  </span>
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

export function MobileHomePages({ onOpenApp }: Props) {
  const pages = useMobileHomeStore((s) => s.pages);
  const activePageIndex = useMobileHomeStore((s) => s.activePageIndex);
  const setActivePage = useMobileHomeStore((s) => s.setActivePage);
  const touchStartX = React.useRef<number | null>(null);

  const activePage = pages[activePageIndex] ?? pages[0];

  const handleTouchStart = React.useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0]?.clientX ?? null;
  }, []);

  const handleTouchEnd = React.useCallback((e: React.TouchEvent) => {
    if (touchStartX.current === null) return;
    const dx = (e.changedTouches[0]?.clientX ?? 0) - touchStartX.current;
    touchStartX.current = null;
    if (Math.abs(dx) < 50) return; // ignore small swipes
    if (dx < 0 && activePageIndex < pages.length - 1) {
      setActivePage(activePageIndex + 1);
    } else if (dx > 0 && activePageIndex > 0) {
      setActivePage(activePageIndex - 1);
    }
  }, [activePageIndex, pages.length, setActivePage]);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Scrollable content area */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 16px 0",
        }}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        {activePage && <PageContent page={activePage} onOpenApp={onOpenApp} />}
      </div>

      {/* Page dots */}
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
          padding: "12px 0",
          flexShrink: 0,
        }}
        role="tablist"
        aria-label="Home screen pages"
      >
        {pages.map((_, i) => {
          const isActive = i === activePageIndex;
          return (
            <button
              key={i}
              role="tab"
              aria-selected={isActive}
              aria-label={`Page ${i + 1}`}
              onClick={() => !isActive && setActivePage(i)}
              style={{
                width: isActive ? 36 : 12,
                height: 12,
                borderRadius: isActive ? 6 : "50%",
                background: isActive ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.2)",
                border: "none",
                padding: 0,
                cursor: isActive ? "default" : "pointer",
                transition: "width 0.2s ease, background 0.2s ease",
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
