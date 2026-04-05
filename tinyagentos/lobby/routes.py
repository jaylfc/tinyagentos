"""Lobby routes — standalone marketing demo pages."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from tinyagentos.lobby.agents import AGENTS
from tinyagentos.lobby.avatars import generate_avatar_svg
from tinyagentos.lobby.chat import ChatRoom

router = APIRouter(prefix="/lobby", tags=["lobby"])

_room: ChatRoom | None = None

# ---------------------------------------------------------------------------
# Config page
# ---------------------------------------------------------------------------

_CONFIG_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Lobby — TinyAgentOS</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #c9d1d9; font-family: system-ui, -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 2.5rem; max-width: 520px; width: 100%; }
  h1 { font-size: 1.6rem; margin-bottom: 0.3rem; color: #f0f6fc; }
  .subtitle { color: #8b949e; margin-bottom: 2rem; font-size: 0.95rem; }
  label { display: block; font-size: 0.85rem; color: #8b949e; margin-bottom: 0.3rem; margin-top: 1rem; }
  input, select { width: 100%; padding: 0.6rem 0.8rem; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; font-size: 0.95rem; }
  input:focus { outline: none; border-color: #58a6ff; }
  .slider-row { display: flex; align-items: center; gap: 1rem; }
  .slider-row input[type=range] { flex: 1; }
  .slider-val { min-width: 2.5rem; text-align: center; font-weight: 600; color: #58a6ff; }
  button { margin-top: 2rem; width: 100%; padding: 0.8rem; background: #238636; border: none; border-radius: 6px; color: #fff; font-size: 1rem; font-weight: 600; cursor: pointer; }
  button:hover { background: #2ea043; }
  .stats { margin-top: 1.5rem; padding: 1rem; background: #0d1117; border-radius: 6px; font-size: 0.85rem; color: #8b949e; }
  .stats span { color: #58a6ff; font-weight: 600; }
  a { color: #58a6ff; text-decoration: none; }
  .back { display: inline-block; margin-bottom: 1rem; font-size: 0.85rem; }
</style>
</head>
<body>
<div class="card">
  <a class="back" href="/">&larr; Back to Dashboard</a>
  <h1>Agent Lobby</h1>
  <p class="subtitle">Launch a live chat room with AI agents discussing TinyAgentOS</p>

  <label for="topic">Discussion Topic</label>
  <input id="topic" type="text" value="The potential of TinyAgentOS for edge AI" placeholder="Enter a topic...">

  <label for="count">Number of Agents</label>
  <div class="slider-row">
    <input id="count" type="range" min="10" max="AGENT_MAX" value="AGENT_DEFAULT">
    <span class="slider-val" id="count-val">AGENT_DEFAULT</span>
  </div>

  <label for="per_round">Agents per Round</label>
  <div class="slider-row">
    <input id="per_round" type="range" min="1" max="10" value="4">
    <span class="slider-val" id="pr-val">4</span>
  </div>

  <label for="backend">Inference Backend URL</label>
  <input id="backend" type="text" value="http://localhost:11434" placeholder="http://host:port">

  <label for="model">Model Name</label>
  <input id="model" type="text" value="qwen3.5:9b" placeholder="model name">

  <label for="backend_type">Backend Type</label>
  <select id="backend_type">
    <option value="ollama">Ollama (/api/generate)</option>
    <option value="openai">OpenAI-compatible (/v1/chat/completions)</option>
  </select>

  <button onclick="launch()">Launch Chat Room</button>

  <div class="stats">
    <span>AGENT_TOTAL</span> agents available &middot; Each with a unique personality, role, and avatar.
  </div>
</div>
<script>
const countEl = document.getElementById('count');
const countVal = document.getElementById('count-val');
countEl.addEventListener('input', () => countVal.textContent = countEl.value);
const prEl = document.getElementById('per_round');
const prVal = document.getElementById('pr-val');
prEl.addEventListener('input', () => prVal.textContent = prEl.value);

async function launch() {
  const body = {
    topic: document.getElementById('topic').value,
    count: parseInt(countEl.value),
    per_round: parseInt(prEl.value),
    backend_url: document.getElementById('backend').value,
    model: document.getElementById('model').value,
    backend_type: document.getElementById('backend_type').value,
  };
  const resp = await fetch('/lobby/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (resp.ok) {
    const data = await resp.json();
    window.location.href = '/lobby/chat?agents=' + data.agents + '&topic=' + encodeURIComponent(body.topic);
  } else {
    alert('Failed to start chat room');
  }
}
</script>
</body>
</html>
"""


def _render_config_html() -> str:
    total = len(AGENTS)
    default = min(100, total)
    html = _CONFIG_HTML
    html = html.replace("AGENT_MAX", str(total))
    html = html.replace("AGENT_DEFAULT", str(default))
    html = html.replace("AGENT_TOTAL", str(total))
    return html


# ---------------------------------------------------------------------------
# Chat page
# ---------------------------------------------------------------------------

_CHAT_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Lobby Chat — TinyAgentOS</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #c9d1d9; font-family: system-ui, -apple-system, sans-serif; height: 100vh; display: flex; flex-direction: column; }
  header { background: #161b22; border-bottom: 1px solid #30363d; padding: 0.8rem 1.5rem; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
  header h1 { font-size: 1.1rem; color: #f0f6fc; }
  header .info { font-size: 0.85rem; color: #8b949e; }
  header .info span { color: #58a6ff; font-weight: 600; }
  .stop-btn { background: #da3633; border: none; color: #fff; padding: 0.4rem 1rem; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem; }
  .stop-btn:hover { background: #f85149; }
  .stats-bar { background: #161b22; border-bottom: 1px solid #30363d; padding: 0.5rem 1.5rem; font-size: 0.8rem; color: #8b949e; display: flex; gap: 2rem; flex-shrink: 0; }
  .stats-bar span { color: #58a6ff; font-weight: 600; }
  #chat { flex: 1; overflow-y: auto; padding: 1rem 1.5rem; }
  .msg { display: flex; gap: 0.75rem; margin-bottom: 0.75rem; align-items: flex-start; animation: fadeIn 0.3s ease; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  .avatar { flex-shrink: 0; width: 40px; height: 40px; border-radius: 50%; overflow: hidden; }
  .avatar svg { display: block; }
  .content { min-width: 0; }
  .name { font-weight: 700; color: #f0f6fc; margin-right: 0.5rem; }
  .role { display: inline-block; font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 10px; color: #fff; font-weight: 600; vertical-align: middle; }
  .content p { margin-top: 0.25rem; line-height: 1.5; }
  .system-msg { text-align: center; color: #8b949e; font-style: italic; padding: 0.5rem 0; }
</style>
</head>
<body>
<header>
  <div>
    <h1>TinyAgentOS Agent Lobby</h1>
    <div class="info"><span id="h-agents">AGENT_COUNT</span> agents &middot; TOPIC</div>
  </div>
  <button class="stop-btn" onclick="stopChat()">Stop</button>
</header>
<div class="stats-bar">
  <div>Active agents: <span id="s-agents">AGENT_COUNT</span></div>
  <div>Messages: <span id="s-msgs">0</span></div>
  <div>Elapsed: <span id="s-time">0s</span></div>
</div>
<div id="chat"></div>
<script>
const chatEl = document.getElementById('chat');
const sMsgs = document.getElementById('s-msgs');
const sTime = document.getElementById('s-time');
let msgCount = 0;
const startTime = Date.now();

// Role colour from name hash
function roleColour(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) & 0xFFFFFFFF;
  return 'hsl(' + (Math.abs(h) % 360) + ', 55%, 40%)';
}

// Timer
setInterval(() => {
  const s = Math.floor((Date.now() - startTime) / 1000);
  const m = Math.floor(s / 60);
  sTime.textContent = m > 0 ? m + 'm ' + (s % 60) + 's' : s + 's';
}, 1000);

const es = new EventSource('/lobby/stream');
es.onmessage = function(e) {
  const msg = JSON.parse(e.data);
  msgCount++;
  sMsgs.textContent = msgCount;

  if (msg.role === 'System') {
    chatEl.innerHTML += '<div class="system-msg">' + escHtml(msg.text) + '</div>';
  } else {
    const avatarSvg = generateAvatar(msg.name, 40);
    chatEl.innerHTML +=
      '<div class="msg">' +
        '<div class="avatar">' + avatarSvg + '</div>' +
        '<div class="content">' +
          '<span class="name">' + escHtml(msg.name) + '</span>' +
          '<span class="role" style="background:' + roleColour(msg.role) + '">' + escHtml(msg.role) + '</span>' +
          '<p>' + escHtml(msg.text) + '</p>' +
        '</div>' +
      '</div>';
  }
  chatEl.scrollTop = chatEl.scrollHeight;
};

es.onerror = function() { es.close(); };

function escHtml(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML;
}

function generateAvatar(name, size) {
  const parts = name.split(' ');
  const initials = parts.length >= 2 ? (parts[0][0] + parts[parts.length-1][0]).toUpperCase() : name.substring(0,2).toUpperCase();
  // Simple hash for colour
  let h = 0;
  for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) & 0xFFFFFFFF;
  const hue = Math.abs(h) % 360;
  const r = size / 2;
  const fs = size * 0.42;
  return '<svg xmlns="http://www.w3.org/2000/svg" width="'+size+'" height="'+size+'">' +
    '<circle cx="'+r+'" cy="'+r+'" r="'+r+'" fill="hsl('+hue+', 55%, 45%)"/>' +
    '<text x="50%" y="50%" dy=".35em" text-anchor="middle" fill="white" font-family="system-ui,sans-serif" font-size="'+fs+'" font-weight="600">'+initials+'</text></svg>';
}

async function stopChat() {
  await fetch('/lobby/stop', {method:'POST'});
  es.close();
  document.querySelector('.stop-btn').textContent = 'Stopped';
  document.querySelector('.stop-btn').disabled = true;
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def lobby_page(request: Request):
    """Lobby configuration page."""
    return HTMLResponse(_render_config_html())


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Full-screen chat interface."""
    agents = request.query_params.get("agents", "100")
    topic = request.query_params.get("topic", "TinyAgentOS")
    html = _CHAT_HTML.replace("AGENT_COUNT", agents).replace("TOPIC", topic)
    return HTMLResponse(html)


@router.get("/stream")
async def chat_stream(request: Request):
    """SSE endpoint for real-time chat messages."""
    async def event_generator():
        if _room is None:
            yield "data: {}\n\n"
            return
        q = _room.subscribe()
        try:
            while True:
                msg = await q.get()
                yield f"data: {json.dumps(msg)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if _room is not None:
                _room.unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/start")
async def start_chat(request: Request):
    """Start a new chat session."""
    global _room
    if _room is not None:
        await _room.stop()

    body = await request.json()
    topic = body.get("topic", "The potential of TinyAgentOS")
    count = min(body.get("count", 100), len(AGENTS))
    backend = body.get("backend_url", "http://localhost:11434")
    model = body.get("model", "qwen3.5:9b")
    per_round = body.get("per_round", 4)
    backend_type = body.get("backend_type", None)

    _room = ChatRoom(
        AGENTS[:count],
        backend,
        topic,
        agents_per_round=per_round,
        model=model,
        backend_type=backend_type,
    )
    await _room.start()
    return {"status": "started", "agents": count}


@router.post("/stop")
async def stop_chat():
    """Stop the current chat session."""
    global _room
    if _room:
        await _room.stop()
        _room = None
    return {"status": "stopped"}
