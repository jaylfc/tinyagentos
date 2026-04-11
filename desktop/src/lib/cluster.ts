/**
 * Shared types + helpers for the /api/cluster/workers surface.
 * Used by both the Activity app's Cluster panel and the dedicated
 * Cluster management app.
 */

export interface ClusterHardwareCpu {
  arch?: string;
  model?: string;
  cores?: number;
  soc?: string;
}

export interface ClusterHardwareNpu {
  type?: string;
  device?: string;
  tops?: number;
  cores?: number;
}

export interface ClusterHardwareGpu {
  type?: string;
  model?: string;
  vram_mb?: number;
  vulkan?: boolean;
  cuda?: boolean;
  rocm?: boolean;
  metal?: boolean;
  opencl?: boolean;
}

export interface ClusterHardwareDisk {
  total_gb?: number;
  free_gb?: number;
  type?: string;
}

export interface ClusterHardwareOs {
  distro?: string;
  version?: string;
  kernel?: string;
}

export interface ClusterHardware {
  cpu?: ClusterHardwareCpu;
  ram_mb?: number;
  npu?: ClusterHardwareNpu;
  gpu?: ClusterHardwareGpu;
  disk?: ClusterHardwareDisk;
  os?: ClusterHardwareOs;
  board?: string;
}

export interface ClusterBackendModel {
  name?: string;
  id?: string;
  size_mb?: number;
  [k: string]: unknown;
}

export interface ClusterBackend {
  name?: string;
  type?: string;
  runtime?: string;
  runtime_version?: string;
  capabilities?: string[];
  models?: ClusterBackendModel[];
  [k: string]: unknown;
}

export interface ClusterWorker {
  name: string;
  url: string;
  hardware?: ClusterHardware;
  backends?: ClusterBackend[];
  models?: string[];
  capabilities?: string[];
  status?: string;
  last_heartbeat?: number;
  registered_at?: number;
  load?: number;
  platform?: string;
}

export type WorkerStatus = "online" | "stale" | "offline" | "unknown";

/**
 * Compute a client-side status pill:
 *  - online if last_heartbeat is within 60s
 *  - stale if 60s–5min
 *  - offline if >5min
 *  - unknown if missing
 *
 * last_heartbeat from the controller is a unix float (seconds).
 */
export function workerStatus(worker: ClusterWorker, nowSec = Date.now() / 1000): WorkerStatus {
  const hb = worker.last_heartbeat;
  if (!hb || typeof hb !== "number") return "unknown";
  const age = nowSec - hb;
  if (age < 60) return "online";
  if (age < 300) return "stale";
  return "offline";
}

export const STATUS_PILL_CLASS: Record<WorkerStatus, string> = {
  online: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  stale: "bg-amber-500/15 text-amber-300 border-amber-500/25",
  offline: "bg-red-500/15 text-red-300 border-red-500/25",
  unknown: "bg-white/5 text-shell-text-tertiary border-white/10",
};

export const STATUS_LABEL: Record<WorkerStatus, string> = {
  online: "online",
  stale: "stale",
  offline: "offline",
  unknown: "unknown",
};

/** Extract a short IP/host from a url like "http://10.228.114.35". */
export function workerShortIp(worker: ClusterWorker): string {
  try {
    const u = new URL(worker.url);
    return u.host;
  } catch {
    return worker.url || "";
  }
}

/**
 * One-line hardware summary string matching the spec:
 * "{cpu_model_short}  ·  {ram_gb} GB  ·  {gpu_or_npu_summary}  ·  {os.distro} {os.version}"
 */
export function workerHardwareSummary(worker: ClusterWorker): string {
  const hw = worker.hardware ?? {};
  const cpuModel = hw.cpu?.model ?? "";
  const cpuShort = (cpuModel.split("@")[0] ?? "").trim() || "Unknown CPU";

  const ramGb = hw.ram_mb ? `${Math.round(hw.ram_mb / 1024)} GB` : "? GB";

  let accel: string;
  const gpu = hw.gpu;
  const npu = hw.npu;
  if (gpu && gpu.type && gpu.type !== "none" && gpu.type !== "") {
    const vramGb = gpu.vram_mb ? ` (${(gpu.vram_mb / 1024).toFixed(1)} GB)` : "";
    accel = `${gpu.model || gpu.type}${vramGb}`;
  } else if (npu && npu.type && npu.type !== "none" && npu.type !== "") {
    const tops = npu.tops ? ` (${npu.tops} TOPS)` : "";
    accel = `${npu.device || npu.type}${tops}`;
  } else {
    accel = "CPU only";
  }

  const os = hw.os;
  const osStr = os && (os.distro || os.version)
    ? `${os.distro ?? ""} ${os.version ?? ""}`.trim()
    : "";

  const parts = [cpuShort, ramGb, accel];
  if (osStr) parts.push(osStr);
  return parts.join("  \u00b7  ");
}

/** Format a unix-seconds timestamp as a short relative string like "3s ago" / "2m ago". */
export function formatRelativeSeconds(hb: number | undefined, nowSec = Date.now() / 1000): string {
  if (!hb || typeof hb !== "number") return "never";
  const age = Math.max(0, nowSec - hb);
  if (age < 60) return `${age.toFixed(0)}s ago`;
  if (age < 3600) return `${(age / 60).toFixed(0)}m ago`;
  if (age < 86400) return `${(age / 3600).toFixed(1)}h ago`;
  return `${(age / 86400).toFixed(1)}d ago`;
}
