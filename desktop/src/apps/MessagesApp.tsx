import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  MessageCircle,
  Hash,
  Users,
  Plus,
  Send,
  Paperclip,
  SmilePlus,
  Bot,
  X,
  AtSign,
  Wifi,
  WifiOff,
  ChevronRight,
  PanelRight,
} from "lucide-react";
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Input,
  Textarea,
  Label,
} from "@/components/ui";
import { MobileSplitView } from "@/components/mobile/MobileSplitView";
import { useIsMobile } from "@/hooks/use-is-mobile";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Channel {
  id: string;
  name: string;
  type: "dm" | "topic" | "group";
  description?: string;
  members?: string[];
  created_at?: string;
  last_message_at?: string;
  lastPreview?: string;
}

interface Message {
  id: string;
  channel_id: string;
  author_id: string;
  author_type: "user" | "agent";
  content: string;
  content_type?: "text" | "canvas" | string;
  metadata?: {
    canvas_id?: string;
    canvas_url?: string;
    canvas_title?: string;
    [key: string]: unknown;
  };
  state?: "pending" | "streaming" | "complete" | "error";
  created_at: string;
  reactions?: Record<string, string[]>;
  edited_at?: string;
}

type WsStatus = "connecting" | "connected" | "disconnected";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function renderContent(text: string) {
  // basic markdown: bold, italic, inline code
  const parts: (string | React.ReactElement)[] = [];
  const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    if (match[2]) parts.push(<strong key={key++} className="font-semibold">{match[2]}</strong>);
    else if (match[3]) parts.push(<em key={key++} className="italic">{match[3]}</em>);
    else if (match[4]) parts.push(<code key={key++} className="bg-white/10 px-1.5 py-0.5 rounded text-[13px] font-mono">{match[4]}</code>);
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

const EMOJI_PICKER = ["👍", "❤️", "😂", "🎉", "🤔", "👀", "🚀", "✅"];

/* ------------------------------------------------------------------ */
/*  MessagesApp                                                        */
/* ------------------------------------------------------------------ */

export function MessagesApp({ windowId: _windowId, title }: { windowId: string; title?: string }) {
  const isMobile = useIsMobile();

  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [typingUsers, setTypingUsers] = useState<{ user: string; type: string }[]>([]);
  const [input, setInput] = useState("");
  const [wsStatus, setWsStatus] = useState<WsStatus>("disconnected");
  const [showCreate, setShowCreate] = useState(false);
  const [showEmoji, setShowEmoji] = useState<string | null>(null); // message id
  const [viewingCanvas, setViewingCanvas] = useState<{ url: string; title?: string } | null>(null);
  const [newChannel, setNewChannel] = useState({ name: "", type: "topic" as "topic" | "group", description: "" });

  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTypingSentRef = useRef(0);
  const autoScrollRef = useRef(true);
  const reconnectDelayRef = useRef(1000);
  const prevChannelRef = useRef<string | null>(null);

  /* ---- fetch channels + unread ---- */
  const fetchChannels = useCallback(async () => {
    try {
      const [chRes, unRes] = await Promise.all([
        fetch("/api/chat/channels"),
        fetch("/api/chat/unread"),
      ]);
      if (chRes.ok) {
        const data = await chRes.json();
        setChannels(data.channels ?? []);
      }
      if (unRes.ok) {
        const data = await unRes.json();
        setUnread(data.unread ?? {});
      }
    } catch {
      /* offline */
    }
  }, []);

  /* ---- fetch messages for a channel ---- */
  const fetchMessages = useCallback(async (channelId: string) => {
    try {
      const res = await fetch(`/api/chat/channels/${channelId}/messages?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages ?? []);
        autoScrollRef.current = true;
      }
    } catch {
      /* offline */
    }
  }, []);

  /* ---- mark channel read ---- */
  const markRead = useCallback(async (channelId: string) => {
    try {
      await fetch(`/api/chat/channels/${channelId}/mark-read`, { method: "POST" });
      setUnread((u) => { const next = { ...u }; delete next[channelId]; return next; });
    } catch {
      /* ignore */
    }
  }, []);

  /* ---- WebSocket ---- */
  const connectWs = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return;
    setWsStatus("connecting");
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/chat`);

    ws.onopen = () => {
      setWsStatus("connected");
      reconnectDelayRef.current = 1000;
      // rejoin current channel
      if (prevChannelRef.current) {
        ws.send(JSON.stringify({ type: "join", channel_id: prevChannelRef.current }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "message":
            setMessages((prev) => {
              if (prev.some((m) => m.id === data.id)) return prev;
              return [...prev, data as Message];
            });
            // bump unread if not the selected channel
            if (data.channel_id !== prevChannelRef.current) {
              setUnread((u) => ({ ...u, [data.channel_id]: (u[data.channel_id] ?? 0) + 1 }));
            }
            break;

          case "message_delta":
            setMessages((prev) =>
              prev.map((m) =>
                m.id === data.message_id
                  ? { ...m, content: m.content + (data.delta ?? ""), state: "streaming" }
                  : m,
              ),
            );
            break;

          case "message_state":
            setMessages((prev) =>
              prev.map((m) =>
                m.id === data.message_id ? { ...m, state: data.state } : m,
              ),
            );
            break;

          case "typing":
            setTypingUsers((prev) => {
              const exists = prev.some((t) => t.user === data.user_id);
              if (exists) return prev;
              return [...prev, { user: data.user_id, type: data.user_type ?? "user" }];
            });
            // expire after 5s
            setTimeout(() => {
              setTypingUsers((prev) => prev.filter((t) => t.user !== data.user_id));
            }, 5000);
            break;

          case "reaction_update":
            setMessages((prev) =>
              prev.map((m) =>
                m.id === data.message_id ? { ...m, reactions: data.reactions } : m,
              ),
            );
            break;

          case "message_edit":
            setMessages((prev) =>
              prev.map((m) =>
                m.id === data.message_id
                  ? { ...m, content: data.content, edited_at: data.edited_at }
                  : m,
              ),
            );
            break;

          case "message_delete":
            setMessages((prev) => prev.filter((m) => m.id !== data.message_id));
            break;
        }
      } catch {
        /* bad json */
      }
    };

    ws.onclose = () => {
      setWsStatus("disconnected");
      wsRef.current = null;
      // reconnect with backoff
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, 30000);
      setTimeout(connectWs, delay);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  /* ---- init ---- */
  useEffect(() => {
    fetchChannels();
    connectWs();
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [fetchChannels, connectWs]);

  /* ---- channel selection ---- */
  useEffect(() => {
    if (!selectedChannel) return;
    // leave previous channel
    if (prevChannelRef.current && prevChannelRef.current !== selectedChannel && wsRef.current?.readyState === 1) {
      wsRef.current.send(JSON.stringify({ type: "leave", channel_id: prevChannelRef.current }));
    }
    prevChannelRef.current = selectedChannel;
    // join new
    if (wsRef.current?.readyState === 1) {
      wsRef.current.send(JSON.stringify({ type: "join", channel_id: selectedChannel }));
    }
    fetchMessages(selectedChannel);
    markRead(selectedChannel);
    setTypingUsers([]);
  }, [selectedChannel, fetchMessages, markRead]);

  /* ---- auto-scroll ---- */
  useEffect(() => {
    if (autoScrollRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const handleScroll = () => {
    const el = messageListRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    autoScrollRef.current = atBottom;
  };

  /* ---- send message ---- */
  const sendMessage = () => {
    const text = input.trim();
    if (!text || !selectedChannel || !wsRef.current || wsRef.current.readyState !== 1) return;
    wsRef.current.send(JSON.stringify({ type: "message", channel_id: selectedChannel, content: text }));
    setInput("");
    autoScrollRef.current = true;
    if (inputRef.current) inputRef.current.style.height = "auto";
  };

  /* ---- typing indicator ---- */
  const handleInputChange = (val: string) => {
    setInput(val);
    // auto-resize textarea
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + "px";
    }
    // send typing indicator throttled (every 3s)
    const now = Date.now();
    if (selectedChannel && wsRef.current?.readyState === 1 && now - lastTypingSentRef.current > 3000) {
      wsRef.current.send(JSON.stringify({ type: "typing", channel_id: selectedChannel }));
      lastTypingSentRef.current = now;
    }
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
    typingTimerRef.current = setTimeout(() => { lastTypingSentRef.current = 0; }, 4000);
  };

  /* ---- key handler ---- */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  /* ---- file upload ---- */
  const handleFileUpload = () => {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.onchange = async () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      const form = new FormData();
      form.append("file", file);
      try {
        const res = await fetch("/api/chat/upload", { method: "POST", body: form });
        if (res.ok) {
          const data = await res.json();
          setInput((prev) => prev + (prev ? "\n" : "") + `[${data.filename}](${data.url})`);
          inputRef.current?.focus();
        }
      } catch {
        /* ignore */
      }
    };
    fileInput.click();
  };

  /* ---- reaction toggle ---- */
  const toggleReaction = (messageId: string, emoji: string) => {
    if (wsRef.current?.readyState === 1) {
      wsRef.current.send(JSON.stringify({ type: "reaction", message_id: messageId, emoji }));
    }
    setShowEmoji(null);
  };

  /* ---- create channel ---- */
  const createChannel = async () => {
    if (!newChannel.name.trim()) return;
    try {
      const res = await fetch("/api/chat/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newChannel.name.trim(),
          type: newChannel.type,
          description: newChannel.description.trim() || undefined,
        }),
      });
      if (res.ok) {
        const ch = await res.json();
        setChannels((prev) => [...prev, ch]);
        setSelectedChannel(ch.id);
        setShowCreate(false);
        setNewChannel({ name: "", type: "topic", description: "" });
      }
    } catch {
      /* ignore */
    }
  };

  /* ---- group channels by type ---- */
  const grouped = {
    dm: channels.filter((c) => c.type === "dm"),
    topic: channels.filter((c) => c.type === "topic"),
    group: channels.filter((c) => c.type === "group"),
  };

  const currentChannel = channels.find((c) => c.id === selectedChannel);

  /* ---------------------------------------------------------------- */
  /*  Sections definition (shared between mobile + desktop lists)     */
  /* ---------------------------------------------------------------- */

  const SECTIONS = [
    { label: "Direct Messages", icon: <AtSign size={13} />, items: grouped.dm },
    { label: "Topics", icon: <Hash size={13} />, items: grouped.topic },
    { label: "Groups", icon: <Users size={13} />, items: grouped.group },
  ];

  /* ---------------------------------------------------------------- */
  /*  Channel list — iOS 26 grouped on mobile, flat sidebar on desktop */
  /* ---------------------------------------------------------------- */

  const channelListUI = isMobile ? (
    /* Mobile: iOS 26 grouped list */
    <div style={{ padding: "8px 0 16px" }}>
      {/* connection status */}
      <div style={{ padding: "0 20px 8px", fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
        {wsStatus === "connected" ? (
          <><Wifi size={11} style={{ color: "#34d399" }} /><span style={{ color: "rgba(52,211,153,0.8)" }}>Connected</span></>
        ) : wsStatus === "connecting" ? (
          <><Wifi size={11} style={{ color: "#fbbf24" }} /><span style={{ color: "rgba(251,191,36,0.8)" }}>Connecting…</span></>
        ) : (
          <><WifiOff size={11} style={{ color: "#f87171" }} /><span style={{ color: "rgba(248,113,113,0.8)" }}>Offline</span></>
        )}
      </div>

      {SECTIONS.map((section) => (
        <div key={section.label} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, color: "rgba(255,255,255,0.45)", padding: "0 20px 6px", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
            {section.icon} {section.label}
          </div>
          {section.items.length === 0 ? (
            <div style={{ padding: "0 20px", fontSize: 12, color: "rgba(255,255,255,0.2)", fontStyle: "italic" }}>None yet</div>
          ) : (
            <div
              style={{
                margin: "0 12px",
                borderRadius: 16,
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.08)",
                overflow: "hidden",
              }}
            >
              {section.items.map((ch, idx, arr) => (
                <button
                  key={ch.id}
                  type="button"
                  onClick={() => setSelectedChannel(ch.id)}
                  aria-label={`Channel ${ch.name}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    width: "100%",
                    padding: "14px 16px",
                    background: selectedChannel === ch.id ? "rgba(59,130,246,0.15)" : "none",
                    border: "none",
                    borderBottom: idx === arr.length - 1 ? "none" : "1px solid rgba(255,255,255,0.06)",
                    cursor: "pointer",
                    color: "inherit",
                    textAlign: "left",
                  }}
                >
                  <span style={{ flex: 1, fontSize: 15, fontWeight: 400, color: "rgba(255,255,255,0.9)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {ch.name}
                  </span>
                  {(unread[ch.id] ?? 0) > 0 && (
                    <span style={{ background: "#3b82f6", color: "#fff", fontSize: 10, fontWeight: 700, borderRadius: 9999, minWidth: 18, height: 18, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 4px" }}>
                      {unread[ch.id]}
                    </span>
                  )}
                  <ChevronRight size={16} style={{ color: "rgba(255,255,255,0.25)", flexShrink: 0 }} />
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  ) : (
    /* Desktop: compact sidebar */
    <div className="w-full flex flex-col h-full">
      {/* connection status */}
      <div className="px-3 py-1.5 text-[11px] flex items-center gap-1.5">
        {wsStatus === "connected" ? (
          <><Wifi size={11} className="text-emerald-400" /><span className="text-emerald-400/80">Connected</span></>
        ) : wsStatus === "connecting" ? (
          <><Wifi size={11} className="text-amber-400 animate-pulse" /><span className="text-amber-400/80">Connecting...</span></>
        ) : (
          <><WifiOff size={11} className="text-red-400" /><span className="text-red-400/80">Offline</span></>
        )}
      </div>

      {/* channel list */}
      <div className="flex-1 overflow-y-auto py-1">
        {SECTIONS.map((section) => (
          <div key={section.label}>
            <div className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-white/30 flex items-center gap-1.5">
              {section.icon} {section.label}
            </div>
            {section.items.length === 0 && (
              <div className="px-3 py-1 text-[11px] text-white/20 italic">None yet</div>
            )}
            {section.items.map((ch) => (
              <Button
                key={ch.id}
                variant={selectedChannel === ch.id ? "secondary" : "ghost"}
                onClick={() => setSelectedChannel(ch.id)}
                className="w-full justify-start h-auto py-1.5 px-3 text-[13px] rounded-none font-normal"
                aria-label={`Channel ${ch.name}`}
              >
                <span className="truncate flex-1 text-left">{ch.name}</span>
                {(unread[ch.id] ?? 0) > 0 && (
                  <span className="shrink-0 bg-blue-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
                    {unread[ch.id]}
                  </span>
                )}
              </Button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );

  /* ---------------------------------------------------------------- */
  /*  Message area                                                     */
  /* ---------------------------------------------------------------- */

  const messageAreaUI = (
    <div className="flex-1 flex flex-col min-w-0 h-full">
      {!selectedChannel ? (
        /* empty state */
        <div className="flex-1 flex items-center justify-center text-white/20">
          <div className="text-center">
            <MessageCircle size={48} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">Select a channel to start chatting</p>
          </div>
        </div>
      ) : (
        <>
          {/* channel header — MobileSplitView owns back nav on mobile */}
          <div className="px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-3 shrink-0">
            {currentChannel?.type === "topic" ? <Hash size={16} className="text-white/40" /> :
             currentChannel?.type === "group" ? <Users size={16} className="text-white/40" /> :
             <AtSign size={16} className="text-white/40" />}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium truncate">{currentChannel?.name ?? "Unknown"}</div>
              {currentChannel?.description && (
                <div className="text-[11px] text-white/35 truncate">{currentChannel.description}</div>
              )}
            </div>
            {currentChannel?.members && (
              <div className="text-[11px] text-white/30 flex items-center gap-1">
                <Users size={12} /> {currentChannel.members.length}
              </div>
            )}
          </div>

          {/* message list */}
          <div
            ref={messageListRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto px-4 py-3 space-y-0.5"
          >
            {messages.length === 0 && (
              <div className="flex items-center justify-center h-full text-white/20 text-sm">
                No messages yet. Say something!
              </div>
            )}
            {messages.map((msg, i) => {
              const isAgent = msg.author_type === "agent";
              const prev = i > 0 ? messages[i - 1] : undefined;
              const showAuthor = !prev || prev.author_id !== msg.author_id;
              return (
                <div
                  key={msg.id}
                  className={`group relative px-3 py-1 rounded-md transition-colors hover:bg-white/[0.03] ${
                    isAgent ? "bg-blue-500/[0.04]" : ""
                  } ${showAuthor ? "mt-3" : ""}`}
                >
                  {showAuthor && (
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`text-[13px] font-semibold ${isAgent ? "text-blue-400" : "text-white/90"}`}>
                        {msg.author_id}
                      </span>
                      {isAgent && (
                        <span className="text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded font-medium flex items-center gap-0.5">
                          <Bot size={10} /> Agent
                        </span>
                      )}
                      <span className="text-[11px] text-white/25">{relativeTime(msg.created_at)}</span>
                      {msg.edited_at && <span className="text-[10px] text-white/20">(edited)</span>}
                    </div>
                  )}
                  <div className="text-[13px] text-white/80 leading-relaxed whitespace-pre-wrap break-words">
                    {renderContent(msg.content)}
                    {msg.state === "pending" && (
                      <span className="ml-1 text-white/30">...</span>
                    )}
                    {msg.state === "streaming" && (
                      <span className="ml-1 inline-flex gap-0.5">
                        <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:0ms]" />
                        <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:150ms]" />
                        <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:300ms]" />
                      </span>
                    )}
                    {msg.state === "error" && (
                      <span className="ml-1 text-red-400 text-[11px]">(error)</span>
                    )}
                  </div>

                  {/* canvas attachment */}
                  {msg.content_type === "canvas" && (msg.metadata?.canvas_url || msg.metadata?.canvas_id) && (
                    <div className="mt-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          const url = msg.metadata?.canvas_url ?? `/canvas/${msg.metadata?.canvas_id}`;
                          setViewingCanvas({ url, title: msg.metadata?.canvas_title as string | undefined });
                        }}
                        className="h-7 px-2.5 text-[12px] gap-1.5 bg-white/[0.04] border-white/10 hover:bg-white/[0.08]"
                        aria-label="View canvas"
                      >
                        <PanelRight size={13} />
                        View Canvas{msg.metadata?.canvas_title ? `: ${msg.metadata.canvas_title}` : ""}
                      </Button>
                    </div>
                  )}

                  {/* reactions */}
                  {msg.reactions && Object.keys(msg.reactions).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {Object.entries(msg.reactions).map(([emoji, users]) => (
                        <button
                          key={emoji}
                          onClick={() => toggleReaction(msg.id, emoji)}
                          className="text-[12px] bg-white/[0.06] hover:bg-white/10 border border-white/[0.06] rounded-full px-2 py-0.5 flex items-center gap-1 transition-colors"
                        >
                          <span>{emoji}</span>
                          <span className="text-white/40">{users.length}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* hover actions */}
                  <div className="absolute right-2 -top-3 hidden group-hover:flex bg-zinc-800 border border-white/10 rounded-md shadow-lg overflow-hidden">
                    <button
                      onClick={() => setShowEmoji(showEmoji === msg.id ? null : msg.id)}
                      className="p-1.5 hover:bg-white/10 text-white/40 hover:text-white/70 transition-colors"
                      aria-label="Add reaction"
                    >
                      <SmilePlus size={14} />
                    </button>
                  </div>

                  {/* emoji picker */}
                  {showEmoji === msg.id && (
                    <div className="absolute right-2 top-5 bg-zinc-800 border border-white/10 rounded-lg shadow-xl p-2 flex gap-1 z-10">
                      {EMOJI_PICKER.map((em) => (
                        <button
                          key={em}
                          onClick={() => toggleReaction(msg.id, em)}
                          className="text-lg hover:bg-white/10 rounded p-0.5 transition-colors"
                        >
                          {em}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* typing indicator */}
          {typingUsers.length > 0 && (
            <div className="px-4 py-1 text-[11px] text-white/30 flex items-center gap-1.5">
              <span className="inline-flex gap-0.5">
                <span className="w-1 h-1 bg-white/30 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-1 h-1 bg-white/30 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-1 h-1 bg-white/30 rounded-full animate-bounce [animation-delay:300ms]" />
              </span>
              {typingUsers.map((t) => t.user).join(", ")} {typingUsers.length === 1 ? "is" : "are"} typing...
            </div>
          )}

          {/* input area */}
          <div className="px-4 py-3 border-t border-white/[0.06] shrink-0">
            <div className="flex items-end gap-2 bg-white/[0.06] rounded-xl border border-white/[0.08] px-2 py-1.5">
              <Button
                variant="ghost"
                size="icon"
                onClick={handleFileUpload}
                className="h-8 w-8 shrink-0 mb-0.5"
                aria-label="Upload file"
              >
                <Paperclip size={16} />
              </Button>
              <Textarea
                ref={inputRef}
                value={input}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Message #${currentChannel?.name ?? ""}...`}
                rows={1}
                className="flex-1 bg-transparent border-0 px-1 py-1.5 min-h-0 text-[13px] focus-visible:ring-0 focus-visible:border-0 max-h-[120px]"
                aria-label="Message input"
              />
              <Button
                size="icon"
                onClick={sendMessage}
                disabled={!input.trim()}
                className="h-8 w-8 shrink-0 mb-0.5"
                aria-label="Send message"
              >
                <Send size={15} />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );

  /* ---------------------------------------------------------------- */
  /*  Toolbar — hide on mobile when in chat                           */
  /* ---------------------------------------------------------------- */

  const showToolbar = !isMobile || selectedChannel === null;

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="flex flex-col h-full bg-shell-base text-white overflow-hidden">
      {/* Toolbar — hidden on mobile when a channel is selected */}
      {showToolbar && (
        <div className="relative flex items-center px-3 py-2.5 border-b border-white/[0.06] shrink-0">
          {title ? (
            <>
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <span className="text-sm font-semibold text-white/90">{title}</span>
              </div>
              <div className="ml-auto">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowCreate(true)}
                  className="h-7 w-7"
                  aria-label="New channel"
                >
                  <Plus size={15} />
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm font-medium text-white/80">
                <MessageCircle size={15} />
                {!isMobile && "Messages"}
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowCreate(true)}
                className="h-7 w-7 ml-auto"
                aria-label="New channel"
              >
                <Plus size={15} />
              </Button>
            </>
          )}
        </div>
      )}

      {/* Master-detail — MobileSplitView handles mobile single-pane + desktop split */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <MobileSplitView
          selectedId={selectedChannel}
          onBack={() => setSelectedChannel(null)}
          listTitle="Messages"
          detailTitle={currentChannel?.name}
          listWidth={240}
          list={channelListUI}
          detail={messageAreaUI}
        />
      </div>

      {/* ---- Canvas Viewer ---- */}
      {viewingCanvas && (
        <div
          className="fixed inset-0 z-[10002] flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setViewingCanvas(null)}
          role="dialog"
          aria-modal="true"
          aria-label="Canvas viewer"
        >
          <div
            className="w-[90vw] h-[85vh] max-w-5xl rounded-xl border border-white/10 overflow-hidden bg-zinc-900 flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 shrink-0">
              <div className="flex items-center gap-2 text-sm text-white/80">
                <PanelRight size={14} />
                <span>{viewingCanvas.title ?? "Canvas"}</span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setViewingCanvas(null)}
                className="h-7 w-7"
                aria-label="Close canvas viewer"
              >
                <X size={14} />
              </Button>
            </div>
            <iframe
              src={viewingCanvas.url}
              className="flex-1 w-full border-none bg-white"
              title="Canvas"
            />
          </div>
        </div>
      )}

      {/* ---- Create Channel — bottom sheet on mobile, centred modal on desktop ---- */}
      {showCreate && (
        isMobile ? (
          <div
            className="fixed inset-0 z-50"
            onClick={() => setShowCreate(false)}
            role="dialog"
            aria-modal="true"
            aria-label="New channel"
          >
            <div
              className="absolute bottom-0 left-0 right-0 bg-zinc-900 border-t border-white/[0.08] rounded-t-2xl p-4 space-y-3"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-semibold">New Channel</span>
                <Button variant="ghost" size="icon" onClick={() => setShowCreate(false)} className="h-7 w-7" aria-label="Close">
                  <X size={15} />
                </Button>
              </div>
              <div className="space-y-1">
                <Label htmlFor="new-channel-name-mobile" className="block uppercase tracking-wider">Name</Label>
                <Input
                  id="new-channel-name-mobile"
                  value={newChannel.name}
                  onChange={(e) => setNewChannel((s) => ({ ...s, name: e.target.value }))}
                  placeholder="general"
                  aria-label="Channel name"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="new-channel-type-mobile" className="block uppercase tracking-wider">Type</Label>
                <select
                  id="new-channel-type-mobile"
                  value={newChannel.type}
                  onChange={(e) => setNewChannel((s) => ({ ...s, type: e.target.value as "topic" | "group" }))}
                  className="w-full bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
                  aria-label="Channel type"
                >
                  <option value="topic">Topic</option>
                  <option value="group">Group</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="new-channel-description-mobile" className="block uppercase tracking-wider">Description</Label>
                <Input
                  id="new-channel-description-mobile"
                  value={newChannel.description}
                  onChange={(e) => setNewChannel((s) => ({ ...s, description: e.target.value }))}
                  placeholder="What's this channel about?"
                  aria-label="Channel description"
                />
              </div>
              <Button onClick={createChannel} disabled={!newChannel.name.trim()} className="w-full">
                Create Channel
              </Button>
            </div>
          </div>
        ) : (
          <div className="absolute inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
            <Card className="w-full max-w-[380px] max-h-full flex flex-col shadow-2xl bg-zinc-900">
              <CardHeader className="flex flex-row items-center justify-between gap-2 p-0 px-4 py-3 border-b border-white/[0.06]">
                <CardTitle className="text-sm font-medium">New Channel</CardTitle>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowCreate(false)}
                  className="h-7 w-7"
                  aria-label="Close"
                >
                  <X size={15} />
                </Button>
              </CardHeader>
              <CardContent className="p-4 pt-4 space-y-3">
                <div className="space-y-1">
                  <Label htmlFor="new-channel-name" className="block uppercase tracking-wider">Name</Label>
                  <Input
                    id="new-channel-name"
                    value={newChannel.name}
                    onChange={(e) => setNewChannel((s) => ({ ...s, name: e.target.value }))}
                    placeholder="general"
                    aria-label="Channel name"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="new-channel-type" className="block uppercase tracking-wider">Type</Label>
                  <select
                    id="new-channel-type"
                    value={newChannel.type}
                    onChange={(e) => setNewChannel((s) => ({ ...s, type: e.target.value as "topic" | "group" }))}
                    className="w-full bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
                    aria-label="Channel type"
                  >
                    <option value="topic">Topic</option>
                    <option value="group">Group</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="new-channel-description" className="block uppercase tracking-wider">Description</Label>
                  <Input
                    id="new-channel-description"
                    value={newChannel.description}
                    onChange={(e) => setNewChannel((s) => ({ ...s, description: e.target.value }))}
                    placeholder="What's this channel about?"
                    aria-label="Channel description"
                  />
                </div>
                <Button
                  onClick={createChannel}
                  disabled={!newChannel.name.trim()}
                  className="w-full"
                >
                  Create Channel
                </Button>
              </CardContent>
            </Card>
          </div>
        )
      )}
    </div>
  );
}
