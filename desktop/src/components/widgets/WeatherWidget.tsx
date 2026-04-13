import { useState, useEffect } from "react";
import { getHomeLocation, getTempUnit, getWindUnit, cToF, kmhToMph, UNIT_CHANGED_EVENT } from "@/apps/WeatherApp";

interface Weather {
  temp: number;
  feelsLike: number;
  condition: string;
  icon: string;
  humidity: number;
  wind: number;
  location: string;
}

const WEATHER_CODES: Record<number, { label: string; icon: string }> = {
  0: { label: "Clear", icon: "☀️" },
  1: { label: "Mainly clear", icon: "🌤" },
  2: { label: "Partly cloudy", icon: "⛅" },
  3: { label: "Overcast", icon: "☁️" },
  45: { label: "Fog", icon: "🌫" },
  48: { label: "Fog", icon: "🌫" },
  51: { label: "Drizzle", icon: "🌦" },
  53: { label: "Drizzle", icon: "🌦" },
  55: { label: "Drizzle", icon: "🌧" },
  61: { label: "Light rain", icon: "🌦" },
  63: { label: "Rain", icon: "🌧" },
  65: { label: "Heavy rain", icon: "🌧" },
  71: { label: "Light snow", icon: "🌨" },
  73: { label: "Snow", icon: "🌨" },
  75: { label: "Heavy snow", icon: "❄️" },
  80: { label: "Showers", icon: "🌦" },
  81: { label: "Showers", icon: "🌧" },
  82: { label: "Heavy showers", icon: "⛈" },
  95: { label: "Thunderstorm", icon: "⛈" },
  96: { label: "Thunderstorm", icon: "⛈" },
  99: { label: "Thunderstorm", icon: "⛈" },
};

function codeInfo(code: number, isDay = true) {
  const info = WEATHER_CODES[code] ?? { label: "Unknown", icon: "🌤" };
  if ((code === 0 || code === 1) && !isDay) return { ...info, icon: "🌙" };
  return info;
}

async function fetchWeather(): Promise<Weather | null> {
  const home = getHomeLocation();
  if (!home) return null;
  try {
    const params = new URLSearchParams({
      latitude: String(home.latitude),
      longitude: String(home.longitude),
      current: "temperature_2m,apparent_temperature,is_day,weather_code,relative_humidity_2m,wind_speed_10m",
      timezone: "auto",
    });
    const resp = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`, { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) return null;
    const data = await resp.json();
    const info = codeInfo(data.current.weather_code, data.current.is_day === 1);
    return {
      temp: Math.round(data.current.temperature_2m),
      feelsLike: Math.round(data.current.apparent_temperature),
      condition: info.label,
      icon: info.icon,
      humidity: data.current.relative_humidity_2m,
      wind: Math.round(data.current.wind_speed_10m),
      location: home.name,
    };
  } catch {
    return null;
  }
}

export function WeatherWidget() {
  const [weather, setWeather] = useState<Weather | null>(null);
  const [noHome, setNoHome] = useState(!getHomeLocation());
  const [tempUnit, setTempUnit] = useState(getTempUnit);
  const [windUnit, setWindUnit] = useState(getWindUnit);

  useEffect(() => {
    const load = () => {
      const home = getHomeLocation();
      setNoHome(!home);
      if (home) fetchWeather().then(setWeather);
    };
    load();
    const timer = setInterval(load, 600_000); // 10 min
    // Refresh when home location changes (from another window) or when
    // the user toggles units in the Weather app (same window).
    const onStorage = () => load();
    const onUnits = () => { setTempUnit(getTempUnit()); setWindUnit(getWindUnit()); };
    window.addEventListener("storage", onStorage);
    window.addEventListener(UNIT_CHANGED_EVENT, onUnits);
    return () => {
      clearInterval(timer);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(UNIT_CHANGED_EVENT, onUnits);
    };
  }, []);

  if (noHome) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 4, padding: 8, textAlign: "center" }}>
        <span style={{ fontSize: 24 }}>🌤</span>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>Tap to set location</span>
      </div>
    );
  }

  if (!weather) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "rgba(255,255,255,0.3)", fontSize: 12 }}>
        Loading...
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", height: "100%", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.4)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "65%" }}>
          {weather.location}
        </span>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>{weather.condition}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 32, lineHeight: 1 }}>{weather.icon}</span>
        <div>
          <span style={{ fontSize: 28, fontWeight: 700, color: "rgba(255,255,255,0.9)", lineHeight: 1 }}>
            {tempUnit === "C" ? weather.temp : cToF(weather.temp)}°
          </span>
          <span style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", marginLeft: 2 }}>{tempUnit}</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
        <span>Feels {tempUnit === "C" ? weather.feelsLike : cToF(weather.feelsLike)}°</span>
        <span>💧 {weather.humidity}%</span>
        <span>💨 {windUnit === "kmh" ? `${weather.wind}km/h` : `${kmhToMph(weather.wind)}mph`}</span>
      </div>
    </div>
  );
}
