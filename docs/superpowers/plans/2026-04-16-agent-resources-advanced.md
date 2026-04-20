# Agent Resources Advanced Collapsible Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Resources wizard step, default memory/CPU to unlimited, and add a hardware-aware collapsible "Advanced" section in the Review step.

**Architecture:** All changes are in `AgentsApp.tsx`. Step 3 (Resources) is removed, shifting Permissions to 3, Failure Policy to 4, Review to 5. Advanced state and a lazy `/api/activity` fetch power the collapsible in the Review step.

**Tech Stack:** React, TypeScript, Tailwind CSS, Lucide icons

---

## File Map

| Action | Path | What changes |
|--------|------|--------------|
| Modify | `desktop/src/apps/AgentsApp.tsx` | All changes — step removal, defaults, deploy payload, Advanced UI |

---

## Task 1: Remove Resources step and update step indices

**Files:**
- Modify: `desktop/src/apps/AgentsApp.tsx`

- [ ] **Step 1: Update the STEPS array and canNext**

Find (around line 562):
```ts
const STEPS = ["Name & Color", "Framework", "Model", "Resources", "Permissions", "Failure Policy", "Review"];

const canNext = () => {
  if (step === 0) return name.trim().length > 0;
  if (step === 1) return selectedFramework.length > 0;
  if (step === 2) return selectedModel.length > 0;
  return true;
};
```

Replace with:
```ts
const STEPS = ["Name & Color", "Framework", "Model", "Permissions", "Failure Policy", "Review"];

const canNext = () => {
  if (step === 0) return name.trim().length > 0;
  if (step === 1) return selectedFramework.length > 0;
  if (step === 2) return selectedModel.length > 0;
  return true;
};
```

- [ ] **Step 2: Remove the Step 3 Resources rendering block**

Find and delete this entire block (around line 826):
```tsx
          {/* Step 3: Resources */}
          {step === 3 && (
            <div className="space-y-4">
              <div>
                <Label htmlFor="agent-memory" className="mb-1.5 block">
                  Memory
                </Label>
                <select
                  id="agent-memory"
                  value={memory}
                  onChange={(e) => setMemory(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                >
                  <option value="256">256 MB</option>
                  <option value="512">512 MB</option>
                  <option value="1024">1 GB</option>
                  <option value="2048">2 GB</option>
                  <option value="4096">4 GB</option>
                </select>
              </div>
              <div>
                <Label htmlFor="agent-cpus" className="mb-1.5 block">
                  CPU Cores
                </Label>
                <select
                  id="agent-cpus"
                  value={cpus}
                  onChange={(e) => setCpus(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                >
                  <option value="1">1 Core</option>
                  <option value="2">2 Cores</option>
                  <option value="4">4 Cores</option>
                </select>
              </div>
            </div>
          )}
```

- [ ] **Step 3: Shift remaining step indices down by 1**

Make these three replacements (exact string match, one at a time):

```tsx
// BEFORE:
          {/* Step 4: Permissions */}
          {step === 4 && (
// AFTER:
          {/* Step 3: Permissions */}
          {step === 3 && (
```

```tsx
// BEFORE:
          {/* Step 5: Failure Policy */}
          {step === 5 && (
// AFTER:
          {/* Step 4: Failure Policy */}
          {step === 4 && (
```

```tsx
// BEFORE:
          {/* Step 6: Review */}
          {step === 6 && (
// AFTER:
          {/* Step 5: Review */}
          {step === 5 && (
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Volumes/NVMe/Users/jay/Development/tinyagentos/desktop && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/apps/AgentsApp.tsx
git commit -m "refactor(agents): remove Resources wizard step, shift step indices"
```

---

## Task 2: Update memory/CPU defaults and deploy payload

**Files:**
- Modify: `desktop/src/apps/AgentsApp.tsx`

- [ ] **Step 1: Change state defaults to empty string (unlimited)**

Find (around line 329):
```ts
  // Step 4
  const [memory, setMemory] = useState("512");
  const [cpus, setCpus] = useState("1");
```

Replace with:
```ts
  // Advanced (formerly Step 4)
  const [memory, setMemory] = useState("");
  const [cpus, setCpus] = useState("");
```

- [ ] **Step 2: Update the deploy payload to send null when unlimited**

Find (around line 578):
```ts
      const memMb = parseInt(memory);
      const memoryLimit = memMb >= 1024 ? `${Math.round(memMb / 1024)}GB` : `${memMb}MB`;
      const res = await fetch("/api/agents/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          framework: selectedFramework,
          model: selectedModel,
          color,
          memory_limit: memoryLimit,
          cpu_limit: parseInt(cpus),
```

Replace with:
```ts
      const memMb = memory ? parseInt(memory) : null;
      const memoryLimit = memMb === null ? null : memMb >= 1024 ? `${Math.round(memMb / 1024)}GB` : `${memMb}MB`;
      const res = await fetch("/api/agents/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          framework: selectedFramework,
          model: selectedModel,
          color,
          memory_limit: memoryLimit,
          cpu_limit: cpus ? parseInt(cpus) : null,
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Volumes/NVMe/Users/jay/Development/tinyagentos/desktop && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/apps/AgentsApp.tsx
git commit -m "feat(agents): default memory/CPU to unlimited, send null to API"
```

---

## Task 3: Add Advanced collapsible in Review step

**Files:**
- Modify: `desktop/src/apps/AgentsApp.tsx`

- [ ] **Step 1: Add the MEMORY_STEPS constant after the existing constants (near COLORS)**

Find (around line 63):
```ts
const COLORS = [
```

Add before it:
```ts
const MEMORY_STEPS_MB = [256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072];

```

- [ ] **Step 2: Add Advanced state variables**

Find (around line 338, after fallbackModelOpen):
```ts
  const [fallbackModelOpen, setFallbackModelOpen] = useState(false);
```

Add after it:
```ts
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedLoaded, setAdvancedLoaded] = useState(false);
  const [systemRamMb, setSystemRamMb] = useState<number | null>(null);
  const [systemCpuCores, setSystemCpuCores] = useState<number | null>(null);
```

- [ ] **Step 3: Replace the Review step rendering block**

Find this block (now at `step === 5`):
```tsx
          {/* Step 5: Review */}
          {step === 5 && (
            <div className="space-y-3">
              <span className="block text-xs text-shell-text-secondary mb-2">Review Configuration</span>
              <div className="rounded-lg bg-shell-bg-deep border border-white/5 divide-y divide-white/5">
                {[
                  ["Name", name],
                  ["Color", color],
                  ["Framework", frameworks.find((f) => f.id === selectedFramework)?.name ?? selectedFramework],
                  ["Model", models.find((m) => m.id === selectedModel)?.name ?? selectedModel],
                  ["Memory", `${memory} MB`],
                  ["CPUs", `${cpus} Core${cpus !== "1" ? "s" : ""}`],
                  ["User Memory", canReadUserMemory ? "Allowed (read-only)" : "Denied"],
                  ["On failure", onWorkerFailure],
                  ["Fallbacks", fallbackModels.filter(Boolean).join(", ") || "none"],
                  // Only include KV quant rows in the review when the cluster
                  // actually offered a choice — avoids surfacing fp16-only
                  // entries that would confuse users who never saw the controls.
                  ...(kvQuantOptions.k.length > 1 ? [["K cache bits", kvCacheQuantK]] : []),
                  ...(kvQuantOptions.v.length > 1 ? [["V cache bits", kvCacheQuantV]] : []),
                  ...(kvQuantOptions.boundary ? [["Boundary layers", String(kvCacheQuantBoundaryLayers)]] : []),
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-xs text-shell-text-secondary">{label}</span>
                    <span className="text-sm font-medium flex items-center gap-1.5">
                      {label === "Color" && (
                        <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: value }} />
                      )}
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
```

Replace with:
```tsx
          {/* Step 5: Review */}
          {step === 5 && (
            <div className="space-y-3">
              <span className="block text-xs text-shell-text-secondary mb-2">Review Configuration</span>
              <div className="rounded-lg bg-shell-bg-deep border border-white/5 divide-y divide-white/5">
                {[
                  ["Name", name],
                  ["Color", color],
                  ["Framework", frameworks.find((f) => f.id === selectedFramework)?.name ?? selectedFramework],
                  ["Model", models.find((m) => m.id === selectedModel)?.name ?? selectedModel],
                  ["Memory", memory ? (parseInt(memory) >= 1024 ? `${Math.round(parseInt(memory) / 1024)} GB` : `${memory} MB`) : "Unlimited"],
                  ["CPUs", cpus ? `${cpus} Core${cpus !== "1" ? "s" : ""}` : "Unlimited"],
                  ["User Memory", canReadUserMemory ? "Allowed (read-only)" : "Denied"],
                  ["On failure", onWorkerFailure],
                  ["Fallbacks", fallbackModels.filter(Boolean).join(", ") || "none"],
                  // Only include KV quant rows in the review when the cluster
                  // actually offered a choice — avoids surfacing fp16-only
                  // entries that would confuse users who never saw the controls.
                  ...(kvQuantOptions.k.length > 1 ? [["K cache bits", kvCacheQuantK]] : []),
                  ...(kvQuantOptions.v.length > 1 ? [["V cache bits", kvCacheQuantV]] : []),
                  ...(kvQuantOptions.boundary ? [["Boundary layers", String(kvCacheQuantBoundaryLayers)]] : []),
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-xs text-shell-text-secondary">{label}</span>
                    <span className="text-sm font-medium flex items-center gap-1.5">
                      {label === "Color" && (
                        <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: value }} />
                      )}
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* Advanced settings collapsible */}
              <div className="mt-1">
                <button
                  onClick={() => {
                    if (!showAdvanced && !advancedLoaded) {
                      fetch("/api/activity", { headers: { Accept: "application/json" } })
                        .then(r => r.json())
                        .then(data => {
                          setSystemRamMb(data?.hardware?.ram_mb ?? null);
                          setSystemCpuCores(data?.hardware?.cpu?.cores ?? null);
                          setAdvancedLoaded(true);
                        })
                        .catch(() => setAdvancedLoaded(true));
                    }
                    setShowAdvanced(v => !v);
                  }}
                  className="flex items-center gap-1.5 text-xs text-shell-text-tertiary hover:text-shell-text transition-colors"
                  aria-expanded={showAdvanced}
                  aria-controls="agent-advanced-settings"
                >
                  <ChevronRight size={14} className={`transition-transform ${showAdvanced ? "rotate-90" : ""}`} />
                  Advanced settings
                </button>
                {showAdvanced && (
                  <div id="agent-advanced-settings" className="mt-3 space-y-3 px-4 py-3 rounded-lg bg-shell-bg-deep border border-white/5">
                    <div>
                      <Label htmlFor="agent-memory-adv" className="mb-1.5 block">Memory</Label>
                      <select
                        id="agent-memory-adv"
                        value={memory}
                        onChange={e => setMemory(e.target.value)}
                        className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                      >
                        <option value="">Unlimited (default)</option>
                        {MEMORY_STEPS_MB
                          .filter(mb => systemRamMb === null || mb <= systemRamMb)
                          .map(mb => (
                            <option key={mb} value={String(mb)}>
                              {mb >= 1024 ? `${Math.round(mb / 1024)} GB` : `${mb} MB`}
                            </option>
                          ))
                        }
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="agent-cpus-adv" className="mb-1.5 block">CPU Cores</Label>
                      <select
                        id="agent-cpus-adv"
                        value={cpus}
                        onChange={e => setCpus(e.target.value)}
                        className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20 transition-colors"
                      >
                        <option value="">Unlimited (default)</option>
                        {Array.from({ length: systemCpuCores ?? 4 }, (_, i) => i + 1).map(n => (
                          <option key={n} value={String(n)}>
                            {n} {n === 1 ? "Core" : "Cores"}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Volumes/NVMe/Users/jay/Development/tinyagentos/desktop && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 5: Run tests**

```bash
cd /Volumes/NVMe/Users/jay/Development/tinyagentos/desktop && npm test 2>&1 | tail -8
```

Expected: same 3 pre-existing snap-zones failures, 181 others pass.

- [ ] **Step 6: Commit**

```bash
git add src/apps/AgentsApp.tsx
git commit -m "feat(agents): advanced resource settings collapsible in review step"
```

---

## Self-Review

**Spec coverage:**
- ✅ Resources step removed (Task 1)
- ✅ Steps shift: Permissions→3, Failure Policy→4, Review→5 (Task 1)
- ✅ Memory/CPU default to `""` = unlimited (Task 2)
- ✅ Deploy payload sends `null` when unlimited (Task 2)
- ✅ `MEMORY_STEPS_MB` powers of 2, filtered to `systemRamMb` (Task 3)
- ✅ CPU options 1 through `systemCpuCores`, fallback 4 (Task 3)
- ✅ Lazy fetch from `/api/activity` on first expand (Task 3)
- ✅ Fallback to static options on fetch failure (Task 3 — `advancedLoaded: true` on catch, `systemRamMb/systemCpuCores` stay null, filter and Array.from use fallback values)
- ✅ Review summary shows "Unlimited" or formatted value (Task 3)
- ✅ `aria-expanded` and `aria-controls` on toggle button (Task 3)
- ✅ No backend changes

**Placeholder scan:** None.

**Type consistency:** `memory` and `cpus` are `string` throughout — `""` is a valid string, `parseInt("")` is NaN so the null guard `cpus ? parseInt(cpus) : null` is correct. `systemRamMb: number | null` and `systemCpuCores: number | null` match their uses in filter and Array.from.
