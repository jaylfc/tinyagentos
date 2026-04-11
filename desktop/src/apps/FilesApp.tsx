import { useState, useEffect, useCallback, useRef } from "react";
import {
  Folder,
  File,
  FileText,
  FileImage,
  FileVideo,
  FileAudio,
  FileCode,
  FileArchive,
  ChevronRight,
  ChevronLeft,
  FolderPlus,
  Upload,
  LayoutGrid,
  List,
  Trash2,
  ArrowLeft,
  HardDrive,
  Share2,
  RefreshCw,
  AlertCircle,
  Download,
} from "lucide-react";
import { Button, Card, Toolbar, ToolbarGroup, ToolbarSpacer } from "@/components/ui";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified: number;
}

interface SharedFolder {
  id: number;
  name: string;
  description: string;
  agents: { name: string; permission: string }[];
  created_at?: string;
}

interface WorkspaceStats {
  total_files: number;
  total_size: number;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const val = bytes / Math.pow(1024, i);
  return `${val < 10 ? val.toFixed(1) : Math.round(val)} ${units[i]}`;
}

function formatDate(timestamp: number): string {
  if (!timestamp) return "—";
  const date = new Date(timestamp * 1000);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

const EXT_ICONS: Record<string, typeof File> = {
  // Images
  png: FileImage, jpg: FileImage, jpeg: FileImage, gif: FileImage, svg: FileImage, webp: FileImage, bmp: FileImage,
  // Video
  mp4: FileVideo, mkv: FileVideo, avi: FileVideo, mov: FileVideo, webm: FileVideo,
  // Audio
  mp3: FileAudio, wav: FileAudio, ogg: FileAudio, flac: FileAudio, aac: FileAudio,
  // Code
  ts: FileCode, tsx: FileCode, js: FileCode, jsx: FileCode, py: FileCode, rs: FileCode, go: FileCode,
  c: FileCode, cpp: FileCode, h: FileCode, java: FileCode, rb: FileCode, sh: FileCode, json: FileCode,
  yaml: FileCode, yml: FileCode, toml: FileCode, xml: FileCode, html: FileCode, css: FileCode,
  // Text
  txt: FileText, md: FileText, log: FileText, csv: FileText, pdf: FileText, doc: FileText, docx: FileText,
  // Archive
  zip: FileArchive, tar: FileArchive, gz: FileArchive, bz2: FileArchive, "7z": FileArchive, rar: FileArchive,
};

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"]);

function isImage(name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return IMAGE_EXTS.has(ext);
}

function fileUrl(location: "workspace" | string, path: string): string {
  const encoded = encodeURIComponent(path);
  return location === "workspace"
    ? `/api/workspace/files/${encoded}`
    : `/api/shared-folders/${encodeURIComponent(location)}/files/${encoded}`;
}

function getFileIcon(name: string, isDir: boolean) {
  if (isDir) return Folder;
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return EXT_ICONS[ext] ?? File;
}

/* ------------------------------------------------------------------ */
/*  API helpers                                                        */
/* ------------------------------------------------------------------ */

async function apiFetch<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts);
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("text/html")) {
    throw new Error("API returned HTML — endpoint may not support JSON mode");
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function FilesApp({ windowId: _windowId }: { windowId: string }) {
  const [currentPath, setCurrentPath] = useState("");
  const [location, setLocation] = useState<"workspace" | string>("workspace");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [sharedFolders, setSharedFolders] = useState<SharedFolder[]>([]);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sharedExpanded, setSharedExpanded] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  /* ---- Fetch files ---- */
  const fetchFiles = useCallback(async (path = "") => {
    setLoading(true);
    setError(null);
    try {
      if (location === "workspace") {
        const qs = path ? `?path=${encodeURIComponent(path)}` : "";
        const data = await apiFetch<FileEntry[]>(`/api/workspace/files${qs}`);
        setFiles(Array.isArray(data) ? data : []);
      } else {
        const data = await apiFetch<FileEntry[]>(`/api/shared-folders/${encodeURIComponent(location)}/files`);
        setFiles(Array.isArray(data) ? data.map((f) => ({ ...f, is_dir: f.is_dir ?? false, path: f.path ?? f.name })) : []);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load files";
      setError(msg);
      setFiles([]);
    } finally {
      setLoading(false);
    }
  }, [location]);

  const navigateTo = useCallback((path: string) => {
    setCurrentPath(path);
    setDeleteConfirm(null);
  }, []);

  const goUp = useCallback(() => {
    if (!currentPath) return;
    const parts = currentPath.split("/").filter(Boolean);
    parts.pop();
    navigateTo(parts.join("/"));
  }, [currentPath, navigateTo]);

  /* ---- Effects ---- */
  useEffect(() => {
    fetchFiles(currentPath);
  }, [currentPath, fetchFiles]);

  // Live updates — SSE stream patches the file list in place when
  // anything changes in the current workspace directory. Only active
  // for the workspace location (shared folders would need their own
  // watch endpoint). Closes automatically when the effect tears down
  // on path / location change or unmount.
  useEffect(() => {
    if (location !== "workspace") return;
    const qs = currentPath ? `?path=${encodeURIComponent(currentPath)}` : "";
    const url = `/api/workspace/files/watch${qs}`;
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource(url);
    } catch {
      return;
    }
    const es = eventSource;
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (Array.isArray(data)) {
          setFiles(data);
        }
      } catch {
        // Ignore malformed events — the next one will come through
      }
    };
    es.onerror = () => {
      // Silently let the browser retry. EventSource auto-reconnects
      // on transient errors; we only explicitly close on effect
      // teardown below.
    };
    return () => {
      es.close();
    };
  }, [currentPath, location]);

  useEffect(() => {
    apiFetch<SharedFolder[]>("/api/shared-folders")
      .then((d) => setSharedFolders(Array.isArray(d) ? d : []))
      .catch(() => setSharedFolders([]));
  }, []);

  useEffect(() => {
    if (location === "workspace") {
      apiFetch<WorkspaceStats>("/api/workspace/stats")
        .then(setStats)
        .catch(() => setStats(null));
    }
  }, [location]);

  /* ---- Actions ---- */
  const handleNewFolder = useCallback(async () => {
    const name = prompt("New folder name:");
    if (!name?.trim()) return;
    const fullPath = currentPath ? `${currentPath}/${name.trim()}` : name.trim();
    try {
      await apiFetch("/api/workspace/mkdir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: fullPath }),
      });
      fetchFiles(currentPath);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to create folder";
      setError(msg);
    }
  }, [currentPath, fetchFiles]);

  const handleUpload = useCallback(async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      for (let i = 0; i < fileList.length; i++) {
        const file = fileList.item(i);
        if (!file) continue;
        const form = new FormData();
        form.append("file", file);

        if (location === "workspace") {
          const qs = currentPath ? `?path=${encodeURIComponent(currentPath)}` : "";
          await apiFetch(`/api/workspace/files/upload${qs}`, { method: "POST", body: form });
        } else {
          await apiFetch(`/api/shared-folders/${encodeURIComponent(location)}/upload`, { method: "POST", body: form });
        }
      }
      fetchFiles(currentPath);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Upload failed";
      setError(msg);
    } finally {
      setUploading(false);
    }
  }, [currentPath, location, fetchFiles]);

  const handleDelete = useCallback(async (filePath: string) => {
    try {
      await apiFetch(`/api/workspace/files/${encodeURIComponent(filePath)}`, { method: "DELETE" });
      setDeleteConfirm(null);
      fetchFiles(currentPath);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Delete failed";
      setError(msg);
    }
  }, [currentPath, fetchFiles]);

  /* ---- Drag and drop ---- */
  const onDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current++;
    setDragging(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setDragging(false);
    }
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current = 0;
    setDragging(false);
    handleUpload(e.dataTransfer.files);
  }, [handleUpload]);

  /* ---- Breadcrumbs ---- */
  const pathSegments = currentPath ? currentPath.split("/").filter(Boolean) : [];

  /* ---- Sort: folders first, then alphabetical ---- */
  const sortedFiles = [...files].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;
  const [mobileShowFiles, setMobileShowFiles] = useState(false);

  /* ---- Render ---- */
  const sidebarUI = (
    <aside className={isMobile ? "w-full flex flex-col h-full bg-shell-bg-deep" : "w-52 shrink-0 border-r border-white/5 bg-shell-bg-deep flex flex-col"}>
        <div className="px-3 pt-3 pb-2 text-xs font-semibold text-shell-text-tertiary uppercase tracking-wider">
          Locations
        </div>

        {/* Workspace */}
        <Button
          variant={location === "workspace" ? "secondary" : "ghost"}
          onClick={() => { setLocation("workspace"); setCurrentPath(""); if (isMobile) setMobileShowFiles(true); }}
          className="w-full justify-start mx-1.5 px-3"
          aria-label="My Workspace"
        >
          <HardDrive size={16} />
          <span className="truncate">My Workspace</span>
        </Button>

        {/* Shared Folders */}
        <Button
          variant="ghost"
          onClick={() => setSharedExpanded(!sharedExpanded)}
          className="w-full justify-start mx-1.5 mt-1 px-3"
          aria-label="Toggle shared folders"
        >
          <Share2 size={16} />
          <span className="flex-1 truncate text-left">Shared Folders</span>
          <ChevronRight size={14} className={`transition-transform ${sharedExpanded ? "rotate-90" : ""}`} />
        </Button>

        {sharedExpanded && (
          <div className="ml-5 mr-1.5">
            {sharedFolders.length === 0 && (
              <div className="px-3 py-2 text-xs text-shell-text-tertiary">No shared folders</div>
            )}
            {sharedFolders.map((sf) => (
              <Button
                key={sf.id}
                variant={location === sf.name ? "secondary" : "ghost"}
                onClick={() => { setLocation(sf.name); setCurrentPath(""); if (isMobile) setMobileShowFiles(true); }}
                className="w-full justify-start px-3 py-1.5 h-auto text-xs font-normal"
                aria-label={`Shared folder: ${sf.name}`}
                title={sf.description}
              >
                <Folder size={14} />
                <span className="truncate">{sf.name}</span>
              </Button>
            ))}
          </div>
        )}

        <div className="flex-1" />

        {/* Stats */}
        {stats && location === "workspace" && (
          <div className="px-3 py-3 border-t border-white/5 text-xs text-shell-text-tertiary space-y-1">
            <div>{stats.total_files} files</div>
            <div>{formatSize(stats.total_size)} used</div>
          </div>
        )}
    </aside>
  );

  const mainContentUI = (
    <div className="flex-1 flex flex-col min-w-0">
      {/* ---- Toolbar ---- */}
      <Toolbar className="shrink-0">
        <ToolbarGroup>
          {/* Mobile back button */}
          {isMobile && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setMobileShowFiles(false)}
              className="text-xs"
            >
              <ChevronLeft size={14} /> Back
            </Button>
          )}
          {/* Back button */}
          {currentPath && (
            <Button
              variant="ghost"
              size="icon"
              onClick={goUp}
              className="h-8 w-8"
              aria-label="Go up one directory"
            >
              <ArrowLeft size={16} />
            </Button>
          )}
        </ToolbarGroup>

        {/* Breadcrumbs */}
        <nav className="flex items-center gap-1 text-xs min-w-0 flex-1" aria-label="File path">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigateTo("")}
            className={`h-7 px-1.5 truncate ${!currentPath ? "text-shell-text font-medium" : ""}`}
          >
            {location === "workspace" ? "Workspace" : location}
          </Button>
          {pathSegments.map((seg, i) => {
            const segPath = pathSegments.slice(0, i + 1).join("/");
            const isLast = i === pathSegments.length - 1;
            return (
              <span key={segPath} className="flex items-center gap-1 min-w-0">
                <ChevronRight size={12} className="text-shell-text-tertiary shrink-0" />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigateTo(segPath)}
                  className={`h-7 px-1.5 truncate ${isLast ? "text-shell-text font-medium" : ""}`}
                >
                  {seg}
                </Button>
              </span>
            );
          })}
        </nav>

        <ToolbarSpacer />

        <ToolbarGroup>
          {/* Actions */}
          {location === "workspace" && (
            <Button
              variant="ghost"
              size="icon"
              onClick={handleNewFolder}
              className="h-8 w-8"
              aria-label="New folder"
              title="New folder"
            >
              <FolderPlus size={14} />
            </Button>
          )}

          <Button
            variant="default"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            aria-label="Upload file"
          >
            <Upload size={14} />
            <span className="hidden sm:inline">Upload</span>
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleUpload(e.target.files)}
            aria-label="File upload input"
          />

          <Button
            variant="ghost"
            size="icon"
            onClick={() => fetchFiles(currentPath)}
            className="h-8 w-8"
            aria-label="Refresh file list"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </Button>

          <div className="flex items-center rounded-lg bg-shell-surface overflow-hidden">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setViewMode("grid")}
              className={`h-8 w-8 rounded-none ${viewMode === "grid" ? "bg-accent/20 text-accent hover:bg-accent/25" : ""}`}
              aria-label="Grid view"
            >
              <LayoutGrid size={14} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setViewMode("list")}
              className={`h-8 w-8 rounded-none ${viewMode === "list" ? "bg-accent/20 text-accent hover:bg-accent/25" : ""}`}
              aria-label="List view"
            >
              <List size={14} />
            </Button>
          </div>
        </ToolbarGroup>
      </Toolbar>

        {/* ---- Error banner ---- */}
        {error && (
          <div className="mx-3 mt-2 flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 text-red-400 text-xs">
            <AlertCircle size={14} className="shrink-0" />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="hover:text-red-300">&times;</button>
          </div>
        )}

        {/* ---- Drop zone / file area ---- */}
        <div
          className={`flex-1 overflow-auto p-3 relative ${dragging ? "ring-2 ring-accent ring-inset bg-accent/5" : ""}`}
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          {/* Drop overlay */}
          {dragging && (
            <div className="absolute inset-0 flex items-center justify-center bg-shell-bg/80 z-10 pointer-events-none">
              <div className="flex flex-col items-center gap-2 text-accent">
                <Upload size={40} />
                <span className="text-sm font-medium">Drop files to upload</span>
              </div>
            </div>
          )}

          {/* Upload progress */}
          {uploading && (
            <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-accent/10 text-accent text-xs">
              <RefreshCw size={14} className="animate-spin" />
              <span>Uploading...</span>
            </div>
          )}

          {/* Loading */}
          {loading && !uploading && (
            <div className="flex items-center justify-center h-full text-shell-text-tertiary">
              <RefreshCw size={20} className="animate-spin" />
            </div>
          )}

          {/* Empty state */}
          {!loading && sortedFiles.length === 0 && !error && (
            <div className="flex flex-col items-center justify-center h-full text-shell-text-tertiary gap-2">
              <Folder size={40} className="opacity-30" />
              <span className="text-sm">This folder is empty</span>
              <span className="text-xs">Drag files here or click Upload</span>
            </div>
          )}

          {/* ---- Grid view ---- */}
          {!loading && sortedFiles.length > 0 && viewMode === "grid" && (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-2">
              {sortedFiles.map((f) => {
                const Icon = getFileIcon(f.name, f.is_dir);
                return (
                  <Card
                    key={f.path || f.name}
                    className="group relative bg-transparent border-transparent hover:bg-shell-surface hover:border-white/[0.06] transition-colors"
                  >
                  <button
                    onClick={() => {
                      if (f.is_dir) {
                        navigateTo(f.path || (currentPath ? `${currentPath}/${f.name}` : f.name));
                      }
                    }}
                    onDoubleClick={() => {
                      if (!f.is_dir && location === "workspace") {
                        window.open(`/api/workspace/files/${encodeURIComponent(f.path || f.name)}`, "_blank");
                      }
                    }}
                    className="flex flex-col items-center gap-2 p-3 text-center w-full rounded-xl"
                    aria-label={f.is_dir ? `Open folder ${f.name}` : `File ${f.name}`}
                  >
                    {!f.is_dir && isImage(f.name) ? (
                      <div className="w-16 h-16 rounded-lg overflow-hidden bg-black/20 border border-white/[0.04] flex items-center justify-center">
                        <img
                          src={fileUrl(location, f.path || f.name)}
                          alt={f.name}
                          loading="lazy"
                          decoding="async"
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            const target = e.currentTarget;
                            target.style.display = "none";
                            const fallback = target.nextElementSibling as HTMLElement | null;
                            if (fallback) fallback.style.display = "block";
                          }}
                        />
                        <Icon
                          size={36}
                          className="text-shell-text-secondary hidden"
                        />
                      </div>
                    ) : (
                      <Icon
                        size={36}
                        className={f.is_dir ? "text-accent" : "text-shell-text-secondary"}
                      />
                    )}
                    <span className="text-xs truncate w-full leading-tight" title={f.name}>
                      {f.name}
                    </span>
                    {!f.is_dir && (
                      <span className="text-[10px] text-shell-text-tertiary">{formatSize(f.size)}</span>
                    )}

                    {/* Delete button overlay */}
                    {location === "workspace" && (
                      <span
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (deleteConfirm === f.path) {
                            handleDelete(f.path);
                          } else {
                            setDeleteConfirm(f.path);
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.stopPropagation();
                            if (deleteConfirm === f.path) {
                              handleDelete(f.path);
                            } else {
                              setDeleteConfirm(f.path);
                            }
                          }
                        }}
                        className={`absolute top-1.5 right-1.5 p-1 rounded-md transition-all ${
                          deleteConfirm === f.path
                            ? "bg-red-500/20 text-red-400 opacity-100"
                            : "opacity-0 group-hover:opacity-100 hover:bg-red-500/20 text-shell-text-tertiary hover:text-red-400"
                        }`}
                        aria-label={deleteConfirm === f.path ? `Confirm delete ${f.name}` : `Delete ${f.name}`}
                        title={deleteConfirm === f.path ? "Click again to confirm" : "Delete"}
                      >
                        <Trash2 size={12} />
                      </span>
                    )}
                  </button>
                  </Card>
                );
              })}
            </div>
          )}

          {/* ---- List view ---- */}
          {!loading && sortedFiles.length > 0 && viewMode === "list" && (
            <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[520px]" aria-label="File list">
              <thead>
                <tr className="text-left text-shell-text-tertiary border-b border-white/5">
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium w-24">Size</th>
                  <th className="px-3 py-2 font-medium w-32">Modified</th>
                  <th className="px-3 py-2 font-medium w-16">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedFiles.map((f) => {
                  const Icon = getFileIcon(f.name, f.is_dir);
                  return (
                    <tr
                      key={f.path || f.name}
                      className="border-b border-white/5 hover:bg-shell-surface/50 transition-colors group"
                    >
                      <td className="px-3 py-2">
                        <button
                          onClick={() => {
                            if (f.is_dir) {
                              navigateTo(f.path || (currentPath ? `${currentPath}/${f.name}` : f.name));
                            }
                          }}
                          className="flex items-center gap-2 min-w-0"
                          aria-label={f.is_dir ? `Open folder ${f.name}` : `File ${f.name}`}
                        >
                          {!f.is_dir && isImage(f.name) ? (
                            <img
                              src={fileUrl(location, f.path || f.name)}
                              alt=""
                              loading="lazy"
                              decoding="async"
                              className="w-6 h-6 rounded object-cover border border-white/[0.06] shrink-0"
                              onError={(e) => {
                                e.currentTarget.style.display = "none";
                              }}
                            />
                          ) : (
                            <Icon size={16} className={f.is_dir ? "text-accent shrink-0" : "text-shell-text-secondary shrink-0"} />
                          )}
                          <span className="truncate">{f.name}</span>
                        </button>
                      </td>
                      <td className="px-3 py-2 text-shell-text-tertiary">
                        {f.is_dir ? "—" : formatSize(f.size)}
                      </td>
                      <td className="px-3 py-2 text-shell-text-tertiary">
                        {formatDate(f.modified)}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          {!f.is_dir && location === "workspace" && (
                            <a
                              href={`/api/workspace/files/${encodeURIComponent(f.path || f.name)}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1 rounded-md opacity-0 group-hover:opacity-100 hover:bg-shell-surface transition-all text-shell-text-tertiary hover:text-shell-text"
                              aria-label={`Download ${f.name}`}
                            >
                              <Download size={13} />
                            </a>
                          )}
                          {location === "workspace" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => {
                                if (deleteConfirm === f.path) {
                                  handleDelete(f.path);
                                } else {
                                  setDeleteConfirm(f.path);
                                }
                              }}
                              className={`h-7 w-7 transition-all ${
                                deleteConfirm === f.path
                                  ? "bg-red-500/20 text-red-400 opacity-100 hover:bg-red-500/25 hover:text-red-400"
                                  : "opacity-0 group-hover:opacity-100 hover:bg-red-500/20 hover:text-red-400"
                              }`}
                              aria-label={deleteConfirm === f.path ? `Confirm delete ${f.name}` : `Delete ${f.name}`}
                              title={deleteConfirm === f.path ? "Click again to confirm" : "Delete"}
                            >
                              <Trash2 size={13} />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          )}
        </div>
      </div>
  );

  return (
    <div className="flex h-full bg-shell-bg text-shell-text text-sm">
      {isMobile ? (
        mobileShowFiles ? mainContentUI : sidebarUI
      ) : (
        <>
          {sidebarUI}
          {mainContentUI}
        </>
      )}
    </div>
  );
}
