import { useEffect, useState } from "react";
import { fetchLibrary, fetchPersonaDetail } from "@/lib/personas-api";
import type { PersonaSource, PersonaSummary, PersonaSelection } from "./types";

const SOURCE_OPTIONS: { value: PersonaSource | ""; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "builtin", label: "Built-in" },
  { value: "awesome-openclaw", label: "awesome-openclaw" },
  { value: "prompt-library", label: "prompt-library" },
  { value: "user", label: "My library" },
];

export function PersonaBrowse({ onSelect }: { onSelect: (s: PersonaSelection) => void }) {
  const [source, setSource] = useState<PersonaSource | "">("");
  const [q, setQ] = useState("");
  const [personas, setPersonas] = useState<PersonaSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<PersonaSummary | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detail, setDetail] = useState<{
    soul_md: string;
    agent_md?: string;
    name: string;
    source: string;
    id: string;
  } | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchLibrary({ source: source || undefined, q: q || undefined })
      .then(setPersonas)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [source, q]);

  function handleSelect(persona: PersonaSummary) {
    setSelected(persona);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    fetchPersonaDetail(persona.source, persona.id)
      .then(setDetail)
      .catch((e) => setDetailError(String(e)))
      .finally(() => setDetailLoading(false));
  }

  function handleUse() {
    if (!detail) return;
    onSelect({
      kind: "library",
      source_persona_id: `${detail.source}:${detail.id}`,
      soul_md: detail.soul_md,
      agent_md: detail.agent_md ?? "",
    });
  }

  return (
    <div className="flex gap-3 min-h-0">
      {/* Left: list */}
      <div className="flex flex-col gap-2 w-56 shrink-0">
        <input
          type="search"
          aria-label="Search personas"
          placeholder="Search…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full rounded border border-white/20 bg-white/5 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <select
          aria-label="Filter by source"
          value={source}
          onChange={(e) => setSource(e.target.value as PersonaSource | "")}
          className="w-full rounded border border-white/20 bg-white/5 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        >
          {SOURCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        {error && (
          <div role="alert" className="rounded bg-red-900/40 px-2 py-1 text-xs text-red-300">
            {error}
          </div>
        )}

        <ul
          aria-label="Persona list"
          className="flex flex-col gap-1 overflow-y-auto"
        >
          {loading && (
            <li className="py-4 text-center text-sm opacity-50">Loading…</li>
          )}
          {!loading && personas.length === 0 && !error && (
            <li className="py-4 text-center text-sm opacity-50">No personas found.</li>
          )}
          {personas.map((p) => (
            <li key={`${p.source}:${p.id}`}>
              <button
                onClick={() => handleSelect(p)}
                aria-pressed={selected?.id === p.id && selected?.source === p.source}
                className={`w-full rounded px-2 py-1.5 text-left text-sm transition-colors ${
                  selected?.id === p.id && selected?.source === p.source
                    ? "bg-blue-600/40 text-blue-200"
                    : "hover:bg-white/10"
                }`}
              >
                <div className="font-medium truncate">{p.name}</div>
                <div className="text-xs opacity-50 capitalize">{p.source}</div>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Right: preview panel */}
      <div className="flex flex-1 flex-col gap-2 min-w-0">
        {!selected && (
          <p className="text-sm opacity-40 mt-4">Select a persona to preview it.</p>
        )}

        {selected && (
          <>
            <h3 className="font-semibold text-sm">{selected.name}</h3>
            <span className="text-xs opacity-50 capitalize">{selected.source}</span>

            {detailError && (
              <div role="alert" className="rounded bg-red-900/40 px-2 py-1 text-xs text-red-300">
                {detailError}
              </div>
            )}

            {detailLoading && (
              <p className="text-sm opacity-40">Loading…</p>
            )}

            {detail && (
              <>
                <pre className="flex-1 overflow-y-auto whitespace-pre-wrap rounded bg-black/30 p-2 text-xs leading-relaxed font-mono">
                  {detail.soul_md || "(no persona content)"}
                </pre>
                <button
                  onClick={handleUse}
                  className="self-start rounded bg-blue-600 px-3 py-1.5 text-sm font-medium hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-400"
                >
                  Use this persona
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
