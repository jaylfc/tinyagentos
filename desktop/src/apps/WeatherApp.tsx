import { useState, useEffect, useCallback } from "react";
import { Search, MapPin, Home, Check } from "lucide-react";

interface Location {
  name: string;
  country: string;
  admin1?: string;
  latitude: number;
  longitude: number;
}

interface CurrentWeather {
  temperature: number;
  feelsLike: number;
  weatherCode: number;
  humidity: number;
  windSpeed: number;
  windDirection: number;
  isDay: boolean;
}

interface DailyForecast {
  date: string;
  tempMax: number;
  tempMin: number;
  weatherCode: number;
  precipitation: number;
}

const WEATHER_CODES: Record<number, { label: string; icon: string }> = {
  0: { label: "Clear sky", icon: "☀️" },
  1: { label: "Mainly clear", icon: "🌤" },
  2: { label: "Partly cloudy", icon: "⛅" },
  3: { label: "Overcast", icon: "☁️" },
  45: { label: "Fog", icon: "🌫" },
  48: { label: "Rime fog", icon: "🌫" },
  51: { label: "Light drizzle", icon: "🌦" },
  53: { label: "Drizzle", icon: "🌦" },
  55: { label: "Heavy drizzle", icon: "🌧" },
  61: { label: "Light rain", icon: "🌦" },
  63: { label: "Rain", icon: "🌧" },
  65: { label: "Heavy rain", icon: "🌧" },
  71: { label: "Light snow", icon: "🌨" },
  73: { label: "Snow", icon: "🌨" },
  75: { label: "Heavy snow", icon: "❄️" },
  77: { label: "Snow grains", icon: "🌨" },
  80: { label: "Rain showers", icon: "🌦" },
  81: { label: "Rain showers", icon: "🌧" },
  82: { label: "Heavy showers", icon: "⛈" },
  85: { label: "Snow showers", icon: "🌨" },
  86: { label: "Heavy snow showers", icon: "❄️" },
  95: { label: "Thunderstorm", icon: "⛈" },
  96: { label: "Thunderstorm + hail", icon: "⛈" },
  99: { label: "Severe thunderstorm", icon: "⛈" },
};

function codeInfo(code: number, isDay = true) {
  const info = WEATHER_CODES[code] ?? { label: "Unknown", icon: "🌤" };
  if ((code === 0 || code === 1) && !isDay) return { ...info, icon: "🌙" };
  return info;
}

// Weather preferences live under /api/preferences/weather so they
// follow the user across devices. The local-cache keys below are only
// used to avoid a flash of empty weather on first paint before the
// server fetch completes; the server is authoritative.
const WEATHER_PREF_NAMESPACE = "weather";
const WEATHER_PREF_CACHE = "taos-pref:weather";

export type TempUnit = "C" | "F";
export type WindUnit = "kmh" | "mph";

interface WeatherPrefs {
  home?: Location | null;
  tempUnit?: TempUnit;
  windUnit?: WindUnit;
}

function readCachedPrefs(): WeatherPrefs {
  try {
    const raw = localStorage.getItem(WEATHER_PREF_CACHE);
    return raw ? (JSON.parse(raw) as WeatherPrefs) : {};
  } catch {
    return {};
  }
}

export function getHomeLocation(): Location | null {
  return readCachedPrefs().home ?? null;
}

export function getTempUnit(): TempUnit {
  return readCachedPrefs().tempUnit === "F" ? "F" : "C";
}

export function getWindUnit(): WindUnit {
  return readCachedPrefs().windUnit === "mph" ? "mph" : "kmh";
}

export function cToF(c: number): number {
  return Math.round(c * 9 / 5 + 32);
}

export function kmhToMph(kmh: number): number {
  return Math.round(kmh * 0.621371);
}

// Fire a custom event so widgets on the same page can refresh without
// waiting for a full window reload. localStorage 'storage' events don't
// fire in the same window that made the change.
const UNIT_CHANGED_EVENT = "taos-weather-units-changed";
function emitUnitChange() {
  window.dispatchEvent(new Event(UNIT_CHANGED_EVENT));
}
export { UNIT_CHANGED_EVENT };

async function searchLocations(query: string): Promise<Location[]> {
  if (!query.trim()) return [];
  try {
    const resp = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=10&language=en&format=json`);
    if (!resp.ok) return [];
    const data = await resp.json();
    return (data.results ?? []).map((r: Record<string, unknown>) => ({
      name: r.name as string,
      country: r.country as string,
      admin1: r.admin1 as string | undefined,
      latitude: r.latitude as number,
      longitude: r.longitude as number,
    }));
  } catch {
    return [];
  }
}

async function fetchForecast(loc: Location) {
  const params = new URLSearchParams({
    latitude: String(loc.latitude),
    longitude: String(loc.longitude),
    current: "temperature_2m,apparent_temperature,is_day,weather_code,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
    daily: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
    timezone: "auto",
    forecast_days: "7",
  });
  const resp = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`);
  if (!resp.ok) return null;
  const data = await resp.json();
  const current: CurrentWeather = {
    temperature: Math.round(data.current.temperature_2m),
    feelsLike: Math.round(data.current.apparent_temperature),
    weatherCode: data.current.weather_code,
    humidity: data.current.relative_humidity_2m,
    windSpeed: Math.round(data.current.wind_speed_10m),
    windDirection: data.current.wind_direction_10m,
    isDay: data.current.is_day === 1,
  };
  const daily: DailyForecast[] = data.daily.time.map((date: string, i: number) => ({
    date,
    tempMax: Math.round(data.daily.temperature_2m_max[i]),
    tempMin: Math.round(data.daily.temperature_2m_min[i]),
    weatherCode: data.daily.weather_code[i],
    precipitation: data.daily.precipitation_sum[i],
  }));
  return { current, daily };
}

// Sync preferences to the server so the same location / units follow the
// user across devices. localStorage is only an immediate-paint cache.
async function saveWeatherPrefs(prefs: WeatherPrefs): Promise<void> {
  try {
    localStorage.setItem(WEATHER_PREF_CACHE, JSON.stringify(prefs));
  } catch {
    // quota or disabled — fine, server is still authoritative
  }
  try {
    await fetch(`/api/preferences/${WEATHER_PREF_NAMESPACE}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    });
  } catch {
    // network error — cached locally, will sync when next mutation runs
  }
}

export function WeatherApp() {
  const [home, setHome] = useState<Location | null>(getHomeLocation);
  const [viewing, setViewing] = useState<Location | null>(home);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Location[]>([]);
  const [searching, setSearching] = useState(false);
  const [forecast, setForecast] = useState<{ current: CurrentWeather; daily: DailyForecast[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [tempUnit, setTempUnit] = useState<TempUnit>(getTempUnit);
  const [windUnit, setWindUnit] = useState<WindUnit>(getWindUnit);

  // Hydrate from server on mount — overrides any stale local cache so a
  // fresh device shows the location the user set on their phone.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(`/api/preferences/${WEATHER_PREF_NAMESPACE}`);
        if (!resp.ok) return;
        const data = (await resp.json()) as WeatherPrefs;
        if (cancelled || !data || Object.keys(data).length === 0) return;
        if (data.home) {
          setHome(data.home);
          setViewing((cur) => cur ?? data.home ?? null);
        }
        if (data.tempUnit === "C" || data.tempUnit === "F") setTempUnit(data.tempUnit);
        if (data.windUnit === "kmh" || data.windUnit === "mph") setWindUnit(data.windUnit);
        localStorage.setItem(WEATHER_PREF_CACHE, JSON.stringify(data));
        emitUnitChange();
      } catch {
        // ignore — local cache is already loaded
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const toggleTempUnit = useCallback(() => {
    const next: TempUnit = tempUnit === "C" ? "F" : "C";
    setTempUnit(next);
    saveWeatherPrefs({ home, tempUnit: next, windUnit });
    emitUnitChange();
  }, [tempUnit, home, windUnit]);

  const toggleWindUnit = useCallback(() => {
    const next: WindUnit = windUnit === "kmh" ? "mph" : "kmh";
    setWindUnit(next);
    saveWeatherPrefs({ home, tempUnit, windUnit: next });
    emitUnitChange();
  }, [windUnit, home, tempUnit]);


  const loadForecast = useCallback(async (loc: Location) => {
    setLoading(true);
    const data = await fetchForecast(loc);
    setForecast(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (viewing) loadForecast(viewing);
  }, [viewing, loadForecast]);

  useEffect(() => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const handle = setTimeout(async () => {
      const results = await searchLocations(query);
      if (!cancelled) {
        setSearchResults(results);
        setSearching(false);
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [query]);

  const selectLocation = (loc: Location) => {
    setViewing(loc);
    setQuery("");
    setSearchResults([]);
  };

  const setAsHome = (loc: Location) => {
    setHome(loc);
    saveWeatherPrefs({ home: loc, tempUnit, windUnit });
  };

  const info = forecast ? codeInfo(forecast.current.weatherCode, forecast.current.isDay) : null;
  const isHome = viewing && home && viewing.latitude === home.latitude && viewing.longitude === home.longitude;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: "linear-gradient(160deg, #1a2a4a 0%, #0e1a36 100%)", color: "white", overflow: "hidden" }}>
      {/* Search bar */}
      <div style={{ padding: 16, flexShrink: 0, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ position: "relative" }}>
          <Search size={16} style={{ position: "absolute", left: 12, top: 12, color: "rgba(255,255,255,0.4)" }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for a town or city..."
            style={{
              width: "100%",
              padding: "10px 12px 10px 36px",
              background: "rgba(255,255,255,0.08)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 10,
              color: "white",
              fontSize: 14,
              outline: "none",
            }}
          />
          {searchResults.length > 0 && (
            <div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, background: "rgba(15,20,40,0.98)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, maxHeight: 280, overflowY: "auto", zIndex: 10 }}>
              {searchResults.map((loc, i) => (
                <button
                  key={`${loc.latitude}-${loc.longitude}-${i}`}
                  onClick={() => selectLocation(loc)}
                  style={{ width: "100%", padding: "10px 14px", textAlign: "left", background: "none", border: "none", color: "white", fontSize: 13, display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.06)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
                >
                  <MapPin size={14} style={{ color: "rgba(255,255,255,0.4)" }} />
                  <span style={{ flex: 1 }}>
                    <span style={{ color: "rgba(255,255,255,0.9)" }}>{loc.name}</span>
                    <span style={{ color: "rgba(255,255,255,0.4)", marginLeft: 6 }}>{loc.admin1 ? `${loc.admin1}, ` : ""}{loc.country}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
          {searching && query && searchResults.length === 0 && (
            <div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, padding: "12px 14px", background: "rgba(15,20,40,0.98)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, fontSize: 13, color: "rgba(255,255,255,0.5)" }}>
              Searching...
            </div>
          )}
        </div>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
        {!viewing && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 12, color: "rgba(255,255,255,0.5)" }}>
            <MapPin size={48} style={{ color: "rgba(255,255,255,0.2)" }} />
            <p style={{ fontSize: 15 }}>Search for a location to see its weather</p>
          </div>
        )}

        {viewing && loading && !forecast && (
          <div style={{ textAlign: "center", color: "rgba(255,255,255,0.5)", marginTop: 40 }}>Loading forecast...</div>
        )}

        {viewing && forecast && info && (
          <>
            {/* Location header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div>
                <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0, color: "rgba(255,255,255,0.95)" }}>{viewing.name}</h1>
                <p style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", margin: "2px 0 0" }}>{viewing.admin1 ? `${viewing.admin1}, ` : ""}{viewing.country}</p>
              </div>
              <button
                onClick={() => setAsHome(viewing)}
                disabled={!!isHome}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "8px 14px",
                  background: isHome ? "rgba(80,200,120,0.2)" : "rgba(255,255,255,0.08)",
                  border: `1px solid ${isHome ? "rgba(80,200,120,0.3)" : "rgba(255,255,255,0.12)"}`,
                  borderRadius: 8, color: isHome ? "rgb(150,220,170)" : "rgba(255,255,255,0.85)",
                  fontSize: 12, fontWeight: 500, cursor: isHome ? "default" : "pointer",
                }}
              >
                {isHome ? <><Check size={14} /> Home</> : <><Home size={14} /> Set as home</>}
              </button>
            </div>

            {/* Current */}
            <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 28, padding: "16px 20px", background: "rgba(255,255,255,0.05)", borderRadius: 16, border: "1px solid rgba(255,255,255,0.08)" }}>
              <div style={{ fontSize: 72, lineHeight: 1 }}>{info.icon}</div>
              <div style={{ flex: 1 }}>
                <button
                  onClick={toggleTempUnit}
                  title="Tap to toggle °C / °F"
                  style={{ display: "flex", alignItems: "baseline", gap: 8, background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit" }}
                >
                  <span style={{ fontSize: 56, fontWeight: 300, lineHeight: 1, color: "rgba(255,255,255,0.95)" }}>
                    {tempUnit === "C" ? forecast.current.temperature : cToF(forecast.current.temperature)}°
                  </span>
                  <span style={{ fontSize: 18, color: "rgba(255,255,255,0.5)" }}>{tempUnit}</span>
                </button>
                <p style={{ fontSize: 14, color: "rgba(255,255,255,0.7)", margin: "4px 0 0" }}>{info.label}</p>
                <p style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", margin: "2px 0 0" }}>Feels like {tempUnit === "C" ? forecast.current.feelsLike : cToF(forecast.current.feelsLike)}°</p>
              </div>
            </div>

            {/* Stats */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10, marginBottom: 28 }}>
              <div style={{ padding: 14, background: "rgba(255,255,255,0.05)", borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)" }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.4)" }}>Humidity</div>
                <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4 }}>{forecast.current.humidity}%</div>
              </div>
              <button
                onClick={toggleWindUnit}
                title="Tap to toggle km/h / mph"
                style={{ padding: 14, background: "rgba(255,255,255,0.05)", borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)", textAlign: "left", cursor: "pointer", color: "inherit" }}
              >
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.4)" }}>Wind</div>
                <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4 }}>
                  {windUnit === "kmh" ? forecast.current.windSpeed : kmhToMph(forecast.current.windSpeed)}
                  <span style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", marginLeft: 4, fontWeight: 400 }}>{windUnit === "kmh" ? "km/h" : "mph"}</span>
                </div>
              </button>
            </div>

            {/* 7-day forecast */}
            <div>
              <h2 style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.8, color: "rgba(255,255,255,0.45)", margin: "0 0 10px", fontWeight: 600 }}>7-Day Forecast</h2>
              <div style={{ background: "rgba(255,255,255,0.04)", borderRadius: 14, border: "1px solid rgba(255,255,255,0.06)", overflow: "hidden" }}>
                {forecast.daily.map((day, i) => {
                  const dayInfo = codeInfo(day.weatherCode);
                  const dateObj = new Date(day.date);
                  const label = i === 0 ? "Today" : dateObj.toLocaleDateString("en", { weekday: "short" });
                  return (
                    <div key={day.date} style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", borderTop: i === 0 ? "none" : "1px solid rgba(255,255,255,0.05)" }}>
                      <span style={{ width: 52, fontSize: 13, color: "rgba(255,255,255,0.8)", fontWeight: 500 }}>{label}</span>
                      <span style={{ fontSize: 22, width: 32, textAlign: "center" }}>{dayInfo.icon}</span>
                      <span style={{ flex: 1, fontSize: 12, color: "rgba(255,255,255,0.55)" }}>{dayInfo.label}</span>
                      <span style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", width: 36, textAlign: "right" }}>{tempUnit === "C" ? day.tempMin : cToF(day.tempMin)}°</span>
                      <span style={{ fontSize: 13, color: "rgba(255,255,255,0.9)", width: 36, textAlign: "right", fontWeight: 500 }}>{tempUnit === "C" ? day.tempMax : cToF(day.tempMax)}°</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
