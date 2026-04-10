import { useState, useEffect, useCallback } from "react";
import { Radio, Plus, Trash2, MessageSquare } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Channel {
  id: string;
  agentName: string;
  type: ChannelType;
  status: "connected" | "disconnected" | "error";
  config: Record<string, string>;
}

type ChannelType =
  | "telegram"
  | "discord"
  | "slack"
  | "webchat"
  | "email"
  | "webhook";

interface ChannelTypeDef {
  id: ChannelType;
  label: string;
  group: "easy" | "advanced";
  fields: { key: string; label: string; placeholder: string; type?: string }[];
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const CHANNEL_TYPES: ChannelTypeDef[] = [
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
  connected: "bg-emerald-500/20 text-emerald-400",
  disconnected: "bg-zinc-500/20 text-zinc-400",
  error: "bg-red-500/20 text-red-400",
};

/* ------------------------------------------------------------------ */
/*  ChannelsApp                                                        */
/* ------------------------------------------------------------------ */

export function ChannelsApp({ windowId: _windowId }: { windowId: string }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [agents, setAgents] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [formAgent, setFormAgent] = useState("");
  const [formType, setFormType] = useState<ChannelType>("telegram");
  const [formConfig, setFormConfig] = useState<Record<string, string>>({});

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
            setChannels(data);
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

  const selectedTypeDef = CHANNEL_TYPES.find((t) => t.id === formType)!;

  function resetForm() {
    setFormAgent("");
    setFormType("telegram");
    setFormConfig({});
    setShowForm(false);
  }

  async function handleAdd() {
    if (!formAgent) return;
    const newChannel: Channel = {
      id: `${formType}-${Date.now()}`,
      agentName: formAgent,
      type: formType,
      status: "disconnected",
      config: { ...formConfig },
    };

    try {
      await fetch("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newChannel),
      });
    } catch { /* ignore */ }

    setChannels((prev) => [...prev, newChannel]);
    resetForm();
  }

  function handleDelete(id: string) {
    setChannels((prev) => prev.filter((c) => c.id !== id));
    fetch(`/api/channels/${id}`, { method: "DELETE" }).catch(() => {});
  }

  const easyTypes = CHANNEL_TYPES.filter((t) => t.group === "easy");
  const advancedTypes = CHANNEL_TYPES.filter((t) => t.group === "advanced");

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
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent text-white hover:bg-accent/90 transition-colors"
          aria-label="Add channel"
        >
          <Plus size={14} />
          Add Channel
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {loading ? (
          <div className="flex items-center justify-center h-full text-shell-text-tertiary text-sm">
            Loading channels...
          </div>
        ) : showForm ? (
          /* Add Channel Form */
          <div className="max-w-lg mx-auto space-y-4">
            <h2 className="text-sm font-semibold">Add Channel</h2>

            {/* Agent select */}
            <div>
              <label htmlFor="channel-agent" className="block text-xs text-shell-text-secondary mb-1.5">
                Agent
              </label>
              <select
                id="channel-agent"
                value={formAgent}
                onChange={(e) => setFormAgent(e.target.value)}
                className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value="">Select an agent...</option>
                {agents.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>

            {/* Channel type select */}
            <div>
              <label htmlFor="channel-type" className="block text-xs text-shell-text-secondary mb-1.5">
                Channel Type
              </label>
              <select
                id="channel-type"
                value={formType}
                onChange={(e) => {
                  setFormType(e.target.value as ChannelType);
                  setFormConfig({});
                }}
                className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
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
            {selectedTypeDef.fields.map((field) => (
              <div key={field.key}>
                <label htmlFor={`channel-${field.key}`} className="block text-xs text-shell-text-secondary mb-1.5">
                  {field.label}
                </label>
                <input
                  id={`channel-${field.key}`}
                  type={field.type ?? "text"}
                  value={formConfig[field.key] ?? ""}
                  onChange={(e) =>
                    setFormConfig((prev) => ({ ...prev, [field.key]: e.target.value }))
                  }
                  placeholder={field.placeholder}
                  className="w-full rounded-lg bg-shell-bg-deep px-3 py-2 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
            ))}

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <button
                onClick={handleAdd}
                disabled={!formAgent}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Plus size={14} />
                Add Channel
              </button>
              <button
                onClick={resetForm}
                className="px-4 py-1.5 rounded-lg text-sm bg-white/5 hover:bg-white/10 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : channels.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-shell-text-tertiary">
            <MessageSquare size={40} className="opacity-30" />
            <p className="text-sm">No channels configured</p>
            <button
              onClick={() => setShowForm(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-accent text-white hover:bg-accent/90 transition-colors mt-1"
            >
              <Plus size={13} />
              Connect your first channel
            </button>
          </div>
        ) : (
          /* Channel list */
          <div className="space-y-2">
            {channels.map((ch) => (
              <div
                key={ch.id}
                className="flex items-center gap-3 p-3.5 rounded-xl bg-shell-surface/60 border border-white/5"
              >
                <MessageSquare size={16} className="text-shell-text-tertiary shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{ch.agentName}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide bg-white/5 text-shell-text-secondary">
                      {ch.type}
                    </span>
                  </div>
                  <p className="text-xs text-shell-text-tertiary mt-0.5">
                    {Object.values(ch.config).filter(Boolean).join(" / ") || "No config"}
                  </p>
                </div>
                <span
                  className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_STYLES[ch.status] ?? STATUS_STYLES.disconnected}`}
                >
                  {ch.status}
                </span>
                <button
                  onClick={() => handleDelete(ch.id)}
                  className="p-1.5 rounded-md hover:bg-red-500/15 transition-colors text-shell-text-secondary hover:text-red-400"
                  aria-label={`Delete ${ch.type} channel for ${ch.agentName}`}
                  title="Delete"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
