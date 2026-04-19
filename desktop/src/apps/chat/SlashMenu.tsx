import React, { useEffect, useMemo, useState } from "react";

type Cmd = { name: string; description: string };
export type SlashCommandsBySlug = Record<string, Cmd[]>;

type Row =
  | { kind: "header"; slug: string }
  | { kind: "cmd"; slug: string; cmd: Cmd };

export function SlashMenu({
  commands,
  queryAfterSlash,
  members,
  onPick,
  onClose,
}: {
  commands: SlashCommandsBySlug;
  queryAfterSlash: string;
  members: string[]; // agents in current channel (ordered)
  onPick: (slug: string, cmd: string) => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(0);

  const rows = useMemo(() => buildRows(commands, members, queryAfterSlash), [commands, members, queryAfterSlash]);
  const cmdRows = rows.filter((r) => r.kind === "cmd") as Extract<Row, { kind: "cmd" }>[];

  useEffect(() => { setSelected(0); }, [queryAfterSlash]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setSelected((s) => Math.min(cmdRows.length - 1, s + 1)); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSelected((s) => Math.max(0, s - 1)); return; }
      if (e.key === "Enter") {
        e.preventDefault();
        const pick = cmdRows[selected];
        if (pick) onPick(pick.slug, pick.cmd.name);
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [cmdRows, selected, onPick, onClose]);

  if (cmdRows.length === 0 && rows.length === 0) return null;

  return (
    <div
      role="listbox"
      aria-label="Slash commands"
      className="absolute bottom-full left-0 mb-2 w-full max-w-md bg-shell-surface border border-white/10 rounded-lg shadow-xl max-h-60 overflow-y-auto text-sm"
    >
      {rows.length === 0 ? (
        <div className="px-3 py-2 text-xs text-shell-text-tertiary">(no commands available)</div>
      ) : (
        rows.map((row, i) => {
          if (row.kind === "header") {
            return (
              <div key={`h-${row.slug}`} className="px-3 py-1 text-[11px] uppercase tracking-wider text-shell-text-tertiary bg-white/5">
                @{row.slug}
              </div>
            );
          }
          const idx = cmdRows.indexOf(row);
          const isSelected = idx === selected;
          return (
            <button
              key={`${row.slug}-${row.cmd.name}`}
              role="option"
              aria-selected={isSelected}
              onMouseEnter={() => setSelected(idx)}
              onClick={() => onPick(row.slug, row.cmd.name)}
              className={`w-full text-left px-3 py-1.5 flex items-center justify-between gap-3 ${
                isSelected ? "bg-white/10" : "hover:bg-white/5"
              }`}
            >
              <span className="font-mono text-[13px]">/{row.cmd.name}</span>
              <span className="text-xs text-shell-text-tertiary truncate">{row.cmd.description}</span>
            </button>
          );
        })
      )}
    </div>
  );
}

function buildRows(
  commands: SlashCommandsBySlug,
  members: string[],
  query: string,
): Row[] {
  const q = query.toLowerCase();
  const agentMembers = members.filter((m) => m !== "user" && commands[m]);
  const isDm = agentMembers.length === 1;
  const rows: Row[] = [];
  for (const slug of agentMembers) {
    const cmds = (commands[slug] || []).filter((c) => matches(slug, c, q));
    if (cmds.length === 0) continue;
    if (!isDm) rows.push({ kind: "header", slug });
    for (const cmd of cmds) rows.push({ kind: "cmd", slug, cmd });
  }
  return rows;
}

function matches(slug: string, cmd: Cmd, q: string): boolean {
  if (!q) return true;
  const hay = `${slug} ${cmd.name} ${cmd.description}`.toLowerCase();
  // simple subsequence match — "to he" matches "tom help"
  let idx = 0;
  for (const ch of q.split(/\s+/).join("")) {
    const next = hay.indexOf(ch, idx);
    if (next === -1) return false;
    idx = next + 1;
  }
  return true;
}
