export type AttachmentRecord = {
  filename: string;
  mime_type: string;
  size: number;
  url: string;
  source: "disk" | "workspace" | "agent-workspace";
};

async function _ensureOk(r: Response): Promise<void> {
  if (r.ok) return;
  let body: { error?: string } | null = null;
  try { body = await r.json(); } catch { /* ignore */ }
  throw new Error(body?.error || `HTTP ${r.status}`);
}

export async function uploadDiskFile(file: File, channelId?: string): Promise<AttachmentRecord> {
  const form = new FormData();
  form.append("file", file);
  if (channelId) form.append("channel_id", channelId);
  const r = await fetch("/api/chat/upload", { method: "POST", body: form });
  await _ensureOk(r);
  return r.json();
}

export async function attachmentFromPath(body: {
  path: string;
  source: "workspace" | "agent-workspace";
  slug?: string;
}): Promise<AttachmentRecord> {
  const r = await fetch("/api/chat/attachments/from-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await _ensureOk(r);
  return r.json();
}
