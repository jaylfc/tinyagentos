/* ------------------------------------------------------------------ */
/*  Memory API client                                                  */
/* ------------------------------------------------------------------ */

const API = '/api';

async function fetchJson<T>(url: string, fallback: T, init?: RequestInit): Promise<T> {
  try {
    const res = await fetch(url, { ...init, headers: { Accept: 'application/json', ...init?.headers } });
    if (!res.ok) return fallback;
    const ct = res.headers.get('content-type') ?? '';
    if (!ct.includes('application/json')) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface BackendCapabilities {
  name: string;
  version: string;
  capabilities: string[];
}

export interface CatalogSession {
  id: number;
  date: string;
  topic: string;
  description?: string;
  start_time?: string;
  end_time?: string;
  category?: string;
  sub_sessions?: CatalogSession[];
  crystal_narrative?: string;
  raw_lines?: string[];
}

/* ------------------------------------------------------------------ */
/*  Stats / capabilities                                               */
/* ------------------------------------------------------------------ */

export async function fetchMemoryStats(): Promise<Record<string, any>> {
  return fetchJson(`${API}/memory/stats`, {});
}

export async function fetchBackendCapabilities(): Promise<BackendCapabilities> {
  return fetchJson(`${API}/memory/backend/capabilities`, { name: 'unknown', version: '0', capabilities: [] });
}

export async function fetchSettingsSchema(): Promise<Record<string, any>> {
  return fetchJson(`${API}/memory/backend/settings-schema`, {});
}

export async function fetchMemorySettings(): Promise<Record<string, any>> {
  return fetchJson(`${API}/memory/settings`, {});
}

export async function updateMemorySettings(settings: Record<string, any>): Promise<Record<string, any>> {
  return fetchJson(`${API}/memory/settings`, {}, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
}

/* ------------------------------------------------------------------ */
/*  Catalog                                                            */
/* ------------------------------------------------------------------ */

export async function fetchCatalogDate(date: string): Promise<any[]> {
  return fetchJson(`${API}/memory/catalog/date/${date}`, []);
}

export async function fetchCatalogSession(id: number): Promise<any> {
  return fetchJson(`${API}/memory/catalog/session/${id}`, null);
}

export async function fetchCatalogSessionContext(id: number): Promise<any> {
  return fetchJson(`${API}/memory/catalog/session/${id}/context`, null);
}

export async function triggerCatalogIndex(body: {
  date?: string;
  start_date?: string;
  end_date?: string;
  force?: boolean;
}): Promise<any> {
  return fetchJson(`${API}/memory/catalog/index`, {}, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function fetchCatalogSearch(query: string): Promise<any[]> {
  return fetchJson(`${API}/memory/catalog/search?q=${encodeURIComponent(query)}`, []);
}

export async function fetchCatalogStats(): Promise<Record<string, any>> {
  return fetchJson(`${API}/memory/catalog/stats`, {});
}

/* ------------------------------------------------------------------ */
/*  Agent memory config                                                */
/* ------------------------------------------------------------------ */

export async function fetchAgentMemoryConfig(name: string): Promise<Record<string, any>> {
  return fetchJson(`${API}/agents/${encodeURIComponent(name)}/memory-config`, {});
}

export async function updateAgentMemoryConfig(name: string, config: Record<string, any>): Promise<Record<string, any>> {
  return fetchJson(`${API}/agents/${encodeURIComponent(name)}/memory-config`, {}, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}
