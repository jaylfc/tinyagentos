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
  ChevronLeft,
} from "lucide-react";

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

export function MessagesApp({ windowId: _windowId }: { windowId: string }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [typingUsers, setTypingUsers] = useState<{ user: string; type: string }[]>([]);
  const [input, setInput] = useState("");
  const [wsStatus, setWsStatus] = useState<WsStatus>("disconnected");
  const [showCreate, setShowCreate] = useState(false);
  const [showEmoji, setShowEmoji] = useState<string | null>(null); // message id
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
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;

  /* ---- Shared UI fragments ---- */
  const channelListUI = (
    <div className={isMobile ? "w-full flex flex-col h-full" : "w-60 shrink-0 bg-black/30 border-r border-white/[0.06] flex flex-col"}>
      {/* header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 text-sm font-medium text-white/80">
          <MessageCircle size={15} />
          Messages
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="p-1 rounded hover:bg-white/10 text-white/50 hover:text-white/80 transition-colors"
          aria-label="New channel"
        >
          <Plus size={15} />
        </button>
      </div>

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
        {[
          { label: "Direct Messages", icon: <AtSign size={13} />, items: grouped.dm },
          { label: "Topics", icon: <Hash size={13} />, items: grouped.topic },
          { label: "Groups", icon: <Users size={13} />, items: grouped.group },
        ].map((section) => (
          <div key={section.label}>
            <div className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-white/30 flex items-center gap-1.5">
              {section.icon} {section.label}
            </div>
            {section.items.length === 0 && (
              <div className="px-3 py-1 text-[11px] text-white/20 italic">None yet</div>
            )}
            {section.items.map((ch) => (
              <button
                key={ch.id}
                onClick={() => setSelectedChannel(ch.id)}
                className={`w-full text-left px-3 py-1.5 flex items-center gap-2 text-[13px] transition-colors ${
                  selectedChannel === ch.id
                    ? "bg-white/10 text-white"
                    : "text-white/60 hover:bg-white/[0.05] hover:text-white/80"
                }`}
                aria-label={`Channel ${ch.name}`}
              >
                <span className="truncate flex-1">{ch.name}</span>
                {(unread[ch.id] ?? 0) > 0 && (
                  <span className="shrink-0 bg-blue-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
                    {unread[ch.id]}
                  </span>
                )}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );

  const messageAreaUI = (
    <div className="flex-1 flex flex-col min-w-0">
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
          {/* channel header */}
          <div className="px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-3 shrink-0">
            {isMobile && (
              <button onClick={() => setSelectedChannel(null)} className="flex items-center gap-1 text-xs text-white/50 hover:text-white/80 shrink-0">
                <ChevronLeft size={14} /> Back
              </button>
            )}
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
            <div className="flex items-end gap-2 bg-white/[0.06] rounded-xl border border-white/[0.08] px-3 py-2">
              <button
                onClick={handleFileUpload}
                className="p-1 text-white/30 hover:text-white/60 transition-colors shrink-0 mb-0.5"
                aria-label="Upload file"
              >
                <Paperclip size={16} />
              </button>
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Message #${currentChannel?.name ?? ""}...`}
                rows={1}
                className="flex-1 bg-transparent text-[13px] text-white/90 placeholder-white/25 outline-none resize-none max-h-[120px]"
                aria-label="Message input"
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim()}
                className={`p-1.5 rounded-lg transition-colors shrink-0 mb-0.5 ${
                  input.trim()
                    ? "bg-blue-500 text-white hover:bg-blue-400"
                    : "text-white/15"
                }`}
                aria-label="Send message"
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="flex h-full bg-shell-base text-white overflow-hidden">
      {isMobile ? (
        selectedChannel ? messageAreaUI : channelListUI
      ) : (
        <>
          {channelListUI}
          {messageAreaUI}
        </>
      )}

      {/* ---- Create Channel Dialog ---- */}
      {showCreate && (
        <div className="absolute inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-white/10 rounded-xl w-[380px] shadow-2xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
              <span className="text-sm font-medium">New Channel</span>
              <button
                onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-white/10 rounded transition-colors text-white/40"
                aria-label="Close"
              >
                <X size={15} />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div>
                <label className="block text-[11px] text-white/40 mb-1 font-medium uppercase tracking-wider">Name</label>
                <input
                  value={newChannel.name}
                  onChange={(e) => setNewChannel((s) => ({ ...s, name: e.target.value }))}
                  placeholder="general"
                  className="w-full bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 outline-none focus:border-blue-500/50"
                  aria-label="Channel name"
                />
              </div>
              <div>
                <label className="block text-[11px] text-white/40 mb-1 font-medium uppercase tracking-wider">Type</label>
                <select
                  value={newChannel.type}
                  onChange={(e) => setNewChannel((s) => ({ ...s, type: e.target.value as "topic" | "group" }))}
                  className="w-full bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
                  aria-label="Channel type"
                >
                  <option value="topic">Topic</option>
                  <option value="group">Group</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] text-white/40 mb-1 font-medium uppercase tracking-wider">Description</label>
                <input
                  value={newChannel.description}
                  onChange={(e) => setNewChannel((s) => ({ ...s, description: e.target.value }))}
                  placeholder="What's this channel about?"
                  className="w-full bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 outline-none focus:border-blue-500/50"
                  aria-label="Channel description"
                />
              </div>
              <button
                onClick={createChannel}
                disabled={!newChannel.name.trim()}
                className="w-full bg-blue-500 hover:bg-blue-400 disabled:opacity-30 disabled:hover:bg-blue-500 text-white text-sm font-medium py-2 rounded-lg transition-colors"
              >
                Create Channel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
