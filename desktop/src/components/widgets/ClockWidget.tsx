import { useState, useEffect } from "react";

export function ClockWidget() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const time = now.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const date = now.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 4 }}>
      <span style={{ fontSize: "2rem", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "#fff", lineHeight: 1 }}>
        {time}
      </span>
      <span style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.6)" }}>
        {date}
      </span>
    </div>
  );
}
