import { Cloud } from "lucide-react";

export function WeatherWidget() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 8 }}>
      <Cloud size={32} style={{ color: "rgba(255,255,255,0.4)" }} />
      <span style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.5)", textAlign: "center", padding: "0 8px" }}>
        Weather widget &mdash; configure location in settings
      </span>
    </div>
  );
}
