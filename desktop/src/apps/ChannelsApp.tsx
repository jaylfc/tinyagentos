import { useState, useEffect, useCallback } from "react";
import { Radio, Plus, Trash2, MessageSquare } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  Input,
  Label,
} from "@/components/ui";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Channel {
  id: number | string;
  agent_name: string;
  type: string;
  enabled: boolean;
  config: Record<string, string>;
}

type ChannelType = string;

interface ChannelField {
  key: string;
  label: string;
  placeholder: string;
  type?: string;
  required?: boolean;
}

interface ChannelTypeDef {
  id: ChannelType;
  label: string;
  group: "easy" | "advanced";
  description?: string;
  fields: ChannelField[];
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const FALLBACK_CHANNEL_TYPES: ChannelTypeDef[] = [
  {
    id: "telegram",
    label: "Telegram",
    group: "easy",
    fields: [
      { key: "botToken", label: "Bot Token", placeholder: "123456:ABC-DEF..." },
    ],
  },
  {
    id: "discord",
    label: "Discord",
    group: "easy",
    fields: [
      { key: "botToken", label: "Bot Token", placeholder: "MTIz..." },
      { key: "guildId", label: "Guild ID", placeholder: "123456789" },
    ],
  },
  {
    id: "slack",
    label: "Slack",
    group: "easy",
    fields: [
      { key: "botToken", label: "Bot Token", placeholder: "xoxb-..." },
      { key: "signingSecret", label: "Signing Secret", placeholder: "abc123..." },
    ],
  },
  {
    id: "webchat",
    label: "WebChat",
    group: "easy",
    fields: [
      { key: "title", label: "Widget Title", placeholder: "Chat with us" },
      { key: "primaryColor", label: "Primary Color", placeholder: "#3b82f6" },
    ],
  },
  {
    id: "email",
    label: "Email",
    group: "advanced",
    fields: [
      { key: "imapHost", label: "IMAP Host", placeholder: "imap.example.com" },
      { key: "smtpHost", label: "SMTP Host", placeholder: "smtp.example.com" },
      { key: "username", label: "Username", placeholder: "agent@example.com" },
      { key: "password", label: "Password", placeholder: "password", type: "password" },
    ],
  },
  {
    id: "webhook",
    label: "Webhook",
    group: "advanced",
    fields: [
      { key: "url", label: "Webhook URL", placeholder: "https://example.com/hook" },
      { key: "secret", label: "Secret", placeholder: "optional signing secret" },
    ],
  },
];

const STATUS_STYLES: Record<string, string> = {
  enabled: "bg-emerald-500/20 text-emerald-400",
  disabled: "bg-zinc-500/20 text-zinc-400",
  error: "bg-red-500/20 text-red-400",
};

/* ------------------------------------------------------------------ */
/*  ChannelsApp                                                        */
/* ------------------------------------------------------------------ */

export function ChannelsApp({ windowId: _windowId }: { windowId: string }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [agents, setAgents] = useState<string[]>([]);
  const [channelTypes, setChannelTypes] = useState<ChannelTypeDef[]>(FALLBACK_CHANNEL_TYPES);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [formAgent, setFormAgent] = useState("");
  const [formType, setFormType] = useState<ChannelType>("telegram");
  const [formConfig, setFormConfig] = useState<Record<string, string>>({});

  // Fetch channel type schema from backend
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/channels/types", {
          headers: { Accept: "application/json" },
        });
        const ct = res.headers.get("content-type") ?? "";
        if (res.ok && ct.includes("application/json")) {
          const data = await res.json();
          if (data && typeof data === "object" && !Array.isArray(data)) {
            const defs: ChannelTypeDef[] = Object.entries(
              data as Record<string, Record<string, unknown>>
            ).map(([id, def]) => {
              const rawFields = Array.isArray(def.config_fields) ? def.config_fields : [];
              const fields: ChannelField[] = (rawFields as Record<string, unknown>[]).map((f) => ({
                key: String(f.name ?? ""),
                label: String(f.label ?? f.name ?? ""),
                placeholder: String(f.default ?? ""),
                type: typeof f.type === "string" && ["text", "number", "url", "password"].includes(f.type)
                  ? (f.type as string)
                  : "text",
                required: Boolean(f.required),
              }));
              const difficulty = String(def.difficulty ?? "easy");
              return {
                id,
                label: String(def.name ?? id),
                group: (difficulty === "advanced" ? "advanced" : "easy") as "easy" | "advanced",
                description: def.description ? String(def.description) : undefined,
                fields,
              };
            });
            if (defs.length > 0) {
              setChannelTypes(defs);
              // Ensure selected type exists in new list
              if (!defs.find((d) => d.id === formType)) {
                setFormType(defs[0].id);
                setFormConfig({});
              }
            }
          }
        }
      } catch { /* keep fallback */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchChannels = useCallback(async () => {
    try {
      const res = await fetch("/api/channels", {
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const data = await res.json();
          if (Array.isArray(data)) {
            setChannels(
              data.map((c: Record<string, unknown>) => ({
                id: (c.id as number | string) ?? `${c.agent_name}-${c.type}`,
                agent_name: String(c.agent_name ?? ""),
                type: String(c.type ?? "") as ChannelType,
                enabled: Boolean(c.enabled ?? true),
                config: (c.config as Record<string, string>) ?? {},
              }))
            );
            setLoading(false);
            return;
          }
        }
      }
    } catch { /* fall through */ }
    setChannels([]);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/agents", {
          headers: { Accept: "application/json" },
        });
        if (res.ok) {
          const ct = res.headers.get("content-type") ?? "";
          if (ct.includes("application/json")) {
            const data = await res.json();
            if (Array.isArray(data) && data.length > 0) {
              setAgents(data.map((a: Record<string, unknown>) => String(a.name ?? "unknown")));
            }
          }
        }
      } catch { /* use fallback */ }
    })();
  }, []);

  const selectedTypeDef =
    channelTypes.find((t) => t.id === formType) ?? channelTypes[0];

  function resetForm() {
    setFormAgent("");
    setFormType(channelTypes[0]?.id ?? "telegram");
    setFormConfig({});
    setFormError(null);
    setSubmitting(false);
    setShowForm(false);
  }

  async function handleAdd() {
    if (!formAgent) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await fetch("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          agent_name: formAgent,
          type: formType,
          config: { ...formConfig },
        }),
      });
      if (!res.ok) {
        let msg = `Add failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.error) msg = String(err.error);
        } catch { /* ignore */ }
        setFormError(msg);
        setSubmitting(false);
        return;
      }
      resetForm();
      fetchChannels();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Network error");
      setSubmitting(false);
    }
  }

  async function handleDelete(ch: Channel) {
    if (!window.confirm(`Remove ${ch.type} channel for ${ch.agent_name}?`)) return;
    try {
      const res = await fetch(
        `/api/channels/${encodeURIComponent(ch.agent_name)}/${encodeURIComponent(ch.type)}`,
        { method: "DELETE", headers: { Accept: "application/json" } }
      );
      if (!res.ok) {
        let msg = `Delete failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.error) msg = String(err.error);
        } catch { /* ignore */ }
        window.alert(msg);
        return;
      }
      fetchChannels();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Network error");
    }
  }

  const easyTypes = channelTypes.filter((t) => t.group === "easy");
  const advancedTypes = channelTypes.filter((t) => t.group === "advanced");

  return (
    <div className="flex flex-col h-full bg-shell-bg text-shell-text select-none">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Radio size={18} className="text-accent" />
          <h1 className="text-sm font-semibold">Channels</h1>
          <span className="text-xs text-shell-text-tertiary">
            {channels.length} configured
          </span>
        </div>
        <Button
          size="sm"
          onClick={() => setShowForm(true)}
          aria-label="Add channel"
        >
          <Plus size={14} />
          Add Channel
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {loading ? (
          <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
            Loading channels...
          </div>
        ) : showForm ? (
          /* Add Channel Form */
          <Card className="max-w-lg mx-auto">
            <CardContent className="p-5 space-y-4">
              <h2 className="text-sm font-semibold">Add Channel</h2>

              {/* Agent select */}
              <div className="space-y-1.5">
                <Label htmlFor="channel-agent">Agent</Label>
                <select
                  id="channel-agent"
                  value={formAgent}
                  onChange={(e) => setFormAgent(e.target.value)}
                  className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20"
                >
                  <option value="">Select an agent...</option>
                  {agents.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>

              {/* Channel type select */}
              <div className="space-y-1.5">
                <Label htmlFor="channel-type">Channel Type</Label>
                <select
                  id="channel-type"
                  value={formType}
                  onChange={(e) => {
                    setFormType(e.target.value as ChannelType);
                    setFormConfig({});
                  }}
                  className="flex h-9 w-full rounded-lg border border-white/10 bg-shell-bg-deep px-3 py-1 text-sm text-shell-text focus-visible:outline-none focus-visible:border-accent/40 focus-visible:ring-2 focus-visible:ring-accent/20"
                >
                  <optgroup label="Easy Setup">
                    {easyTypes.map((t) => (
                      <option key={t.id} value={t.id}>{t.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Advanced">
                    {advancedTypes.map((t) => (
                      <option key={t.id} value={t.id}>{t.label}</option>
                    ))}
                  </optgroup>
                </select>
              </div>

              {/* Dynamic config fields */}
              {(selectedTypeDef?.fields ?? []).map((field) => (
                <div key={field.key} className="space-y-1.5">
                  <Label htmlFor={`channel-${field.key}`}>{field.label}</Label>
                  <Input
                    id={`channel-${field.key}`}
                    type={field.type ?? "text"}
                    value={formConfig[field.key] ?? ""}
                    onChange={(e) =>
                      setFormConfig((prev) => ({ ...prev, [field.key]: e.target.value }))
                    }
                    placeholder={field.placeholder}
                  />
                </div>
              ))}

              {formError && (
                <div role="alert" className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded px-2 py-1.5">
                  {formError}
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2 pt-2">
                <Button
                  onClick={handleAdd}
                  disabled={!formAgent || submitting}
                >
                  <Plus size={14} />
                  {submitting ? "Adding..." : "Add Channel"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={resetForm}
                >
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : channels.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-shell-text-tertiary">
            <MessageSquare size={40} className="opacity-30" />
            <p className="text-sm">No channels configured</p>
            <Button
              size="sm"
              onClick={() => setShowForm(true)}
              className="mt-1"
            >
              <Plus size={13} />
              Connect your first channel
            </Button>
          </div>
        ) : (
          /* Channel list */
          <div className="space-y-2">
            {channels.map((ch) => {
              const statusKey = ch.enabled ? "enabled" : "disabled";
              return (
                <Card key={String(ch.id)}>
                  <CardContent className="flex items-center gap-3 p-3.5">
                    <MessageSquare size={16} className="text-shell-text-tertiary shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium truncate">{ch.agent_name}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-white/5 text-shell-text-secondary">
                          {ch.type}
                        </span>
                      </div>
                      <p className="text-xs text-shell-text-tertiary mt-0.5">
                        {Object.values(ch.config).filter(Boolean).join(" / ") || "No config"}
                      </p>
                    </div>
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_STYLES[statusKey]}`}
                    >
                      {statusKey}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(ch)}
                      className="h-7 w-7 hover:text-red-400 hover:bg-red-500/15"
                      aria-label={`Delete ${ch.type} channel for ${ch.agent_name}`}
                      title="Delete"
                    >
                      <Trash2 size={15} />
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
