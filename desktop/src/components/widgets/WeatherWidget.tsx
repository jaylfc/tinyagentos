import { useState, useEffect } from "react";

interface WeatherData {
  temp: number;
  feelsLike: number;
  condition: string;
  icon: string;
  humidity: number;
  wind: number;
  location: string;
}

const CONDITION_ICONS: Record<string, string> = {
  "Sunny": "☀️",
  "Clear": "🌙",
  "Partly cloudy": "⛅",
  "Cloudy": "☁️",
  "Overcast": "☁️",
  "Mist": "🌫",
  "Fog": "🌫",
  "Light rain": "🌦",
  "Moderate rain": "🌧",
  "Heavy rain": "🌧",
  "Light drizzle": "🌦",
  "Patchy rain possible": "🌦",
  "Patchy light rain": "🌦",
  "Light rain shower": "🌦",
  "Thundery outbreaks possible": "⛈",
  "Snow": "🌨",
  "Light snow": "🌨",
  "Blizzard": "🌨",
  "Sleet": "🌨",
};

function getIcon(condition: string, hour?: number): string {
  const match = Object.entries(CONDITION_ICONS).find(([key]) =>
    condition.toLowerCase().includes(key.toLowerCase())
  );
  if (match) return match[1];
  // Default based on time
  if (hour !== undefined && (hour >= 21 || hour < 5)) return "🌙";
  return "🌤";
}

async function fetchWeather(): Promise<WeatherData | null> {
  try {
    const resp = await fetch("https://wttr.in/?format=j1", { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) return null;
    const data = await resp.json();
    const current = data.current_condition?.[0];
    const area = data.nearest_area?.[0];
    if (!current) return null;

    const condition = current.weatherDesc?.[0]?.value ?? "Unknown";
    return {
      temp: parseInt(current.temp_C ?? "0"),
      feelsLike: parseInt(current.FeelsLikeC ?? "0"),
      condition,
      icon: getIcon(condition, new Date().getHours()),
      humidity: parseInt(current.humidity ?? "0"),
      wind: parseInt(current.windspeedKmph ?? "0"),
      location: area?.areaName?.[0]?.value ?? "",
    };
  } catch {
    return null;
  }
}

export function WeatherWidget() {
  const [weather, setWeather] = useState<WeatherData | null>(null);

  useEffect(() => {
    fetchWeather().then(setWeather);
    const timer = setInterval(() => fetchWeather().then(setWeather), 600_000); // 10 min
    return () => clearInterval(timer);
  }, []);

  if (!weather) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "rgba(255,255,255,0.3)", fontSize: 12 }}>
        Loading weather...
      </div>
    );
  }

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      height: "100%",
      gap: 4,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.4)" }}>
          {weather.location || "Weather"}
        </span>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
          {weather.condition}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 32, lineHeight: 1 }}>{weather.icon}</span>
        <div>
          <span style={{ fontSize: 28, fontWeight: 700, color: "rgba(255,255,255,0.9)", lineHeight: 1 }}>
            {weather.temp}°
          </span>
          <span style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", marginLeft: 2 }}>C</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
        <span>Feels {weather.feelsLike}°</span>
        <span>💧 {weather.humidity}%</span>
        <span>💨 {weather.wind}km/h</span>
      </div>
    </div>
  );
}
