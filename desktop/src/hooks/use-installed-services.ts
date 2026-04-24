import { useState, useEffect } from "react";

export interface InstalledService {
  app_id: string;
  display_name: string;
  icon: string | null;
  url: string;
  category: string;
  backend: string;
  status: "running" | "stopped" | "unknown";
}

/**
 * Fetches the list of installed services from /api/apps/installed.
 * Returns the list (empty while loading or on error).
 */
export function useInstalledServices(): InstalledService[] {
  const [services, setServices] = useState<InstalledService[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/apps/installed")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: InstalledService[]) => {
        if (!cancelled) setServices(data);
      })
      .catch(() => {
        // Silently ignore — services section just won't appear
      });
    return () => { cancelled = true; };
  }, []);

  return services;
}
