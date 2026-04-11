# TinyAgentOS

> **⚠️ Early Development** — This project is under active development and has not been tested on clean hardware yet. Do not install in production. Star/watch the repo to follow progress.

Self-hosted AI agent platform that runs on whatever hardware you have. An old laptop, a Raspberry Pi, a gaming PC, an SBC gathering dust — or all of them at once. TinyAgentOS turns your spare hardware into a distributed AI compute cluster.

A full web desktop environment with 26 bundled apps, 87 catalog apps, 43 MCP plugins, 15 agent frameworks, a curated local model catalog of 97 manifests covering LLMs, vision, embeddings, audio, and image generation (including RK3588 NPU variants via c01zaut/happyme531), plus 167k+ searchable models from HuggingFace, agent deployment, training, image/video/audio generation, and full system monitoring — all from a single web dashboard. Supports Apple Silicon (MLX), NVIDIA, AMD, Rockchip NPU, Raspberry Pi, Android phones, and more.

**Framework-agnostic by design** — TinyAgentOS owns everything that matters: your agent's memory, files, communication channels, model access, and configuration. The agent framework is just a replaceable execution engine. Switch from SmolAgents to LangChain to OpenClaw and your agent keeps its entire history, all its Telegram/Discord/Slack connections, its trained LoRA adapters, its files, and its API keys. No migration, no data loss, no reconfiguration. This is possible because TinyAgentOS manages the full agent lifecycle outside the framework.

**Offline-first memory system** — every agent gets a persistent memory store (QMD) running inside its own container. Documents are chunked, embedded, and indexed locally using your own hardware (NPU, GPU, or CPU). Keyword search via FTS5, semantic vector search via sqlite-vec, and hybrid search combining both. Memory survives framework swaps, container restarts, and even full platform reinstalls (backup/restore). No cloud vector database, no API calls, no data leaving your network.

## Quick Start

```bash
pip install -e .
python -m uvicorn tinyagentos.app:create_app --factory --host 0.0.0.0 --port 6969
```

Open `http://your-host:6969` (or `http://tinyagentos.local:6969` with mDNS). The root URL loads the desktop shell directly.

## Web Desktop Experience

TinyAgentOS ships with a full browser-based desktop environment. Open it at `http://your-host:6969/` and you get a window manager, dock, launchpad, notifications, widgets, and 26 bundled apps — no native install required. On phones and tablets it automatically swaps to a Palm webOS-style card switcher with a pill-bar and iOS-style home grid, installable as a fullscreen PWA from the browser's "Add to Home Screen".

- **Window manager** — float, snap zones, drag, resize, minimise, maximise, close
- **Top bar** — global search (Ctrl+Space), clock, notifications, widget toggle
- **Dock** — pinned apps with running indicators, customisable layout
- **Launchpad** — fullscreen app grid with search
- **Right-click desktop menu** — new folder, change wallpaper, widgets, save to memory, settings
- **Wallpaper picker** — 8 built-in gradient wallpapers
- **Widgets** — Clock, Agent Status, Quick Notes, System Stats, Weather (draggable/resizable)
- **Notifications** — toast stack + notification centre dropdown
- **Persistent sessions** — windows, dock layout, and wallpaper restore across devices
- **Login gate** — optional password protection
- **Mobile/tablet mode** — auto-detects touch + screen width (desktop >=1024px, tablet 768-1024px touch, mobile <768px), iOS PWA fullscreen with safe-area support
- **Card switcher** — webOS-style horizontal carousel with flick-to-close
- **Standalone Chat PWA** — Messages available as a dedicated installable app at `/chat-pwa`
- **shadcn/ui primitives** — Button, Card, Input, Tabs, Switch, Toolbar

### 26 Bundled Desktop Apps

**Platform apps (13):** Messages (WebSocket chat), Agents (deploy wizard + logs + skills), Store (43+ apps), Settings (multi-section with Memory capture toggles), Models, Memory (User + Agent sections), Channels, Secrets, Tasks, Import, Images, Dashboard, Files (real VFS with workspace + shared folders).

**OS apps (8):** Calculator (math.js), Calendar (month view), Contacts (CRUD), Browser (URL-rewriting proxy, agent-ready), Media Player (Plyr), Text Editor (CodeMirror 6 with Obsidian-style theme), Image Viewer (zoom/rotate), Terminal (real PTY + SSH client).

**Games (3):** Chess (plays against real agents via LLM), Wordle, Crosswords.

## Key Features

### Web Desktop Shell
Full browser-based desktop OS with window manager (float + snap), dock, launchpad, right-click context menu, wallpaper picker, notifications, widgets, and persistent sessions that follow you across devices. 26 bundled apps — platform tools, OS utilities, and games — plus an optional password login gate. See [Web Desktop Experience](#web-desktop-experience) above.

### Mobile & Tablet Mode
Auto-detects touch devices and swaps the desktop for a Palm webOS-style card switcher with a bottom pill-bar (back, home, app switcher, notifications), iOS-style home grid with gradient-tinted icons, and a mobile top bar with "< Back" + centred app title. Installable as a fullscreen PWA on iOS and Android with safe-area support and native browser chrome hidden. A standalone Chat PWA is available at `/chat-pwa` and installs like a private Discord.

### User Memory System
Personal QMD-style memory for you, the user — think Pieces App but self-hosted. SQLite store with FTS5 full-text search auto-captures conversations from the Message Hub, notes from the Text Editor, file activity, and search queries. Per-category capture toggles live in Settings. Available in global search (Ctrl+Space) alongside apps, with a "Save to Memory" right-click option on the desktop. Agents can optionally read user memory with explicit permission via the `TAOS_USER_MEMORY_URL` environment variable. A "My Memory" section in the Memory app sits alongside agent memories.

### Skills & Plugins Registry
Framework-agnostic skill system with 7 default skills — memory_search, file_read, file_write, web_search, code_exec, image_generation, http_request — categorised by search, files, code, media, browser, data, comms, system. Each skill declares compatibility per framework (native/adapter/unsupported) and works across all 15 supported frameworks via adapter translation. Assign or remove skills per agent from the Skills tab with compatibility badges.

### Distributed Compute Cluster
Combine ANY device into one AI compute mesh — desktops, laptops, SBCs, even phones and tablets. A gaming PC handles large models, a Mac runs MLX inference, a Pi handles embeddings, an old Android phone contributes from a drawer. Cross-platform worker apps connect from the system tray (Windows, macOS, Linux) or via Termux (Android).

```bash
# Desktop — system tray worker app
tinyagentos-worker http://your-server:6969

# Android — one-line Termux setup
curl -sL https://raw.githubusercontent.com/jaylfc/tinyagentos/master/tinyagentos/worker/android_setup.sh | bash
```

### Backend-Driven Discovery (Core Principle)
The source of truth for "what can I run right now?" is the live state of
the backends, never the filesystem or a config file. Every subsystem that
asks "is model X available? which backend serves capability Y? what's
loaded on the NPU?" answers by polling the backends and reading a central
in-memory index. On-disk catalog manifests describe the universe of
known-good models; the live backend catalog describes the intersection of
that universe with what's actually loaded right now. This principle
applies to models, capabilities, skills, workers, and accelerators. It
makes filename conventions irrelevant, makes cross-platform backends a
drop-in (CUDA/Vulkan/ROCm/Metal just register and get discovered), and
lets the scheduler route work only to backends that are genuinely ready.
See [docs/design/resource-scheduler.md](docs/design/resource-scheduler.md).

### Local Model Catalog + Live Model Browser
A curated catalog of 97 vetted model manifests ships in-tree — every download URL is verified against HuggingFace, covering LLMs (Qwen3, Qwen2.5, Llama 3.1/3.3, Gemma 2/3, Phi-4, Mistral, Mixtral, DeepSeek, Granite, Command-R), vision models (Qwen2.5-VL, MiniCPM-V 2.6, Moondream2, Florence-2, LLaVA), embeddings (nomic, bge, mxbai, snowflake-arctic), rerankers (bge-reranker-v2, qwen3-reranker), speech (Whisper tiny→large-v3-turbo, Kokoro TTS, Piper, Parakeet), image generation (SD 1.5 LCM, Dreamshaper 8 LCM, SDXL Turbo/Lightning, Flux schnell/dev, SD3.5, PixArt-Σ, Playground v2.5, Kolors, AuraFlow), and image tools (RMBG-1.4, BiRefNet, Real-ESRGAN, 4x-UltraSharp, GFPGAN, CodeFormer, ControlNet canny/depth/pose). **RK3588 NPU variants** are included via c01zaut (Qwen2.5 1.5B→14B RKLLM) and happyme531 (LCM Dreamshaper SD as multi-file RKNN). The live Model Browser also searches 167k+ GGUF models from HuggingFace and the Ollama library. Hardware-filtered compatibility indicators show what runs on your device (green/yellow/red).

### Agent Templates (1,467 Templates)
Pick from 1,467 agent templates — 12 built-in plus 196 from awesome-openclaw-agents and 1,259 from the System Prompt Library — and deploy in one click. Browse by category (24 categories), filter by source, or search. Each template includes a system prompt, recommended framework, model, and resource limits. All templates vendored locally so nothing depends on external services.

### App Store (87 Catalog Apps + 43 MCP Plugins, including 12 Streaming Apps)
One-click install for agent frameworks, AI models, and services. Hardware-aware — only shows what works on your device.

### Agent Deployment
5-step wizard: pick framework → choose model → configure → deploy into an isolated container (LXC on bare metal, Docker on VPS, auto-detected). Each agent gets its own memory system, its own QMD instance, its own file storage, and its own network identity. The framework runs inside the container but TinyAgentOS manages everything around it: memory, channels, secrets, model access, scheduled tasks, and inter-agent communication. This means the framework is a swappable component, not a lock-in decision.

### Channel Hub (Framework-Agnostic Messaging)
Most agent frameworks force you to wire up Telegram, Discord, or Slack directly into their code. If you switch frameworks, you rebuild all those integrations from scratch. TinyAgentOS flips this: the platform owns the messaging connections and routes messages to whichever framework the agent currently uses. Switch an agent from SmolAgents to LangChain and it keeps every channel, every conversation, every connection. The framework never touches the bot tokens.

- **6 connectors** — Telegram, Discord, Slack, Email (IMAP/SMTP), Web Chat (WebSocket), Webhooks
- **15 framework adapters** — thin HTTP bridges (~25 lines each) that translate the universal message format to framework-specific APIs
- **Rich responses** — buttons, images, cards via universal format with inline hint fallback for any framework
- **Per-agent or shared bots** — each agent gets its own bot, or share one across a group

### LLM Proxy (LiteLLM)
Hidden internal gateway that unifies all inference providers behind a single OpenAI-compatible API. Each agent gets a virtual API key with budget and rate limits. The proxy is auto-configured from your backend list. Switch from a local Ollama backend to a cloud provider (or add both as fallbacks) and no agent config changes. The agent just calls its local API key and TinyAgentOS routes to the best available backend.

### Dynamic Capabilities
Features unlock automatically based on your hardware and cluster. Solo Pi sees core features. Add a GPU worker and image generation, video, and training appear. No configuration — the platform just knows what's possible.

### AI Generation
- **Images** — Stable Diffusion via NPU, GPU, or CPU (multi-backend auto-discovery)
- **Video** — WanGP, LTX Video (unlocks with 6GB+ GPU worker)
- **Audio** — Kokoro TTS, Chatterbox, Piper, Whisper STT, MusicGPT

### Training & Fine-Tuning
- **LoRA Training** — train agent-specific adapters from the web UI (8GB+ GPU)
- **Agent Retrain** — one-click: agent audits itself, finds knowledge gaps, trains improvement
- **Per-agent LoRAs** — each agent gets its own specialisation on a shared base model
- **Smart routing** — GPU workers get instant LoRA hot-swap, NPU uses time-shared merged models
- **Deployment** — auto-converts and deploys to all backends in the cluster

### Agent Memory System
Each agent runs its own QMD (Query Markup Documents) instance inside its container. This is a local, offline-first knowledge base that the agent reads and writes to.

- **Document ingestion** — drag-and-drop files into agent memory via the web UI or API. Supports text, markdown, PDFs, code.
- **Automatic embedding** — documents are chunked and embedded using your local inference backend (NPU, GPU, or CPU). No external API calls.
- **Keyword search** — FTS5 full-text search across all documents with ranking
- **Vector search** — semantic similarity search via sqlite-vec using locally-generated embeddings
- **Hybrid search** — combines keyword + vector results using Reciprocal Rank Fusion for best-of-both accuracy
- **Memory browser** — web UI to search across all agents' knowledge bases from one place
- **Framework-independent** — memory lives in the container, not in the framework. Switch frameworks and the agent's entire knowledge base stays intact.
- **Portable** — export an agent's config, channels, and memory. Import on another TinyAgentOS instance.

The QMD fork adds a remote model server (`qmd serve`) with an Ollama-compatible embedding backend, batch embedding, and retry logic. Each agent's QMD is accessible over HTTP so the platform can query it without touching the container filesystem.

### Agent Workspace
Click on any agent to enter their "virtual computer" — a tablet-like interface with app icons: Messages, Memory, Files, Tasks, Channels, Logs. Browse their conversations, search their knowledge, manage their files. Like logging into their personal device.

### Shared Folders
Create shared file spaces for agents, groups, and departments. The design team shares mockups, the research team shares documents. Per-agent access control.

### Agent Management
- **Communication Channels** — Telegram, Discord, Slack, web chat, email, webhooks (Easy/Advanced setup)
- **Secrets Manager** — encrypted storage with per-agent access control
- **Inter-Agent Relationships** — groups, departments, lead agents, permissions matrix
- **Scheduled Tasks** — cron jobs with presets, per-agent or group assignment
- **Data Import** — drag-and-drop file upload to agent memory
- **Memory Browser** — keyword + semantic vector search across all agents
- **Agent Export/Import** — portable JSON export of agent config, channels, and group memberships

### Authentication
Password-protected dashboard with persistent sessions. Per-agent API keys. Exempt paths for cluster workers and health checks.

### Model Conversion
Convert models between formats (GGUF→RKLLM, HF→GGUF, GGUF→MLX). Capability-gated — "Convert for NPU" button appears when an x86 worker joins the cluster.

### Message Hub (Built-in Chat)
Discord-style messaging built into the platform. Chat with your agents, create topic channels, share files, view rich embeds and interactive components. Available as a standalone PWA (install it like a private Discord app) or within the main dashboard.

- **Channels** -- DMs, groups, topics, threads, agent sessions
- **Rich messages** -- markdown, code blocks, embeds with fields/images, interactive buttons and selects
- **Canvas** -- agents present visual content (charts, mockups, interactive choices) in a split view alongside the chat. Powered by CanvasX with live updates.
- **Real-time** -- WebSocket hub with typing indicators, presence, and token-by-token streaming of agent responses
- **File sharing** -- drag-and-drop upload, inline preview for images/video/audio/PDF
- **Dual PWA** -- install the chat as a separate app from the management dashboard

### Terminal with SSH
Real PTY backend exposed over WebSocket (`/ws/terminal`) in the Terminal app. Pick Local Shell or SSH Connection; the SSH form takes host/port/user/password (key-based auth supported) and recent hosts are saved to localStorage. Built on xterm.js with Nerd Font, 256 colours, FitAddon, and WebLinks.

### Browser App
Built-in browser with a server-side proxy that rewrites HTML URLs and strips `X-Frame-Options` so arbitrary sites render inline. Includes a bookmarks bar, Open in Tab, and Agent Browse button for future browser-use integration. Auto-detects iOS PWAs and defaults to external mode. The Neko streaming browser is also available in the app catalog.

### MCP Plugin Catalog (43 Plugins)
`app-catalog/plugins/` ships 43 MCP servers including the official set (filesystem, git, fetch, memory, sequential-thinking, time), GitHub, Playwright, Docker, Kubernetes, databases (Postgres/MySQL/SQLite dbhub, MongoDB, Redis, Chroma, Supabase), documents (pandoc, office docs, spreadsheet, markdownify, excel), comms (Slack, WhatsApp, email, Notion, Obsidian, Atlassian, Google Workspace), infra (AWS, Cloudflare, Grafana, arXiv, YouTube transcript, Firecrawl), agent-specific (browser-use, Camoufox, context7, supergateway, engram, Exa), Home Assistant, Todoist, and more.

### Global Search
Search across agents, apps, messages, and files from a single endpoint. Finds anything on the platform instantly.

### Monitoring & Management
- **Dashboard** — KPIs, CPU/RAM sparklines, activity feed, quick actions, backend health, cluster stats
- **Health Debug Page** — checks all services, backends, agents, disk, RAM with live status
- **Notifications** — health alerts, backend up/down, worker join/leave, webhook forwarding (Slack/Discord/Telegram)
- **Agent Logs** — real-time log viewer with auto-refresh
- **Backup & Restore** — downloadable config backup, one-click restore, scheduled auto-backup (daily/weekly)
- **System Updates** — pull latest from GitHub via Settings page
- **Provider Management** — add/test/remove inference providers with live connectivity checks

## App Catalog (87 Catalog Apps + 26 Desktop Apps + 43 MCP Plugins)

| Category | Apps |
|----------|------|
| **Agent Frameworks (15)** | SmolAgents, PocketFlow, OpenClaw, nanoclaw, PicoClaw, ZeroClaw, MicroClaw, IronClaw, NullClaw, Moltis, Hermes, Agent Zero, OpenAI Agents SDK, Langroid, ShibaClaw |
| **Streaming Apps (12)** | Blender, LibreOffice, Code Server, GIMP, Krita, FreeCAD, Obsidian, Excalidraw, JupyterLab, Grafana, n8n, Terminal |
| **LLM Models** | 97-manifest local catalog: Qwen3 0.6B-32B, Qwen2.5 0.5B-72B (+ RKLLM 1.5B-14B for RK3588), Llama 3.1/3.2/3.3, Gemma 2/3, Phi-3.5/4/4-mini, Mistral/Nemo/Mixtral, DeepSeek, Granite, Command-R, SmolLM2, TinyLlama, plus 167k+ searchable from HuggingFace |
| **Vision Models** | Qwen2-VL, Qwen2.5-VL, MiniCPM-V 2.6, Moondream2, Florence-2, LLaVA 1.6 / LLaVA-Phi-3 |
| **Embeddings / Rerankers** | nomic-embed-text-v1.5, bge-large/small/m3, mxbai-embed-large, snowflake-arctic-embed, qwen3-embedding/reranker, bge-reranker-v2-m3 |
| **Audio Models** | Whisper tiny→large-v3-turbo, Kokoro TTS, Piper voices, Parakeet TDT |
| **Image Models** | SD 1.5 LCM, Dreamshaper 8 LCM, LCM Dreamshaper V7 (+ RKNN for RK3588), SDXL Turbo/Lightning, Flux schnell/dev GGUF, SD 3.5 Large Turbo, PixArt-Σ, SDXS, Playground v2.5, Kolors, AuraFlow, Stable Cascade |
| **Image Tools** | RMBG-1.4, BiRefNet, Real-ESRGAN x4, 4x-UltraSharp, GFPGAN, CodeFormer, ControlNet (canny/depth/openpose) |
| **Image Gen** | ComfyUI, Fooocus, SD Web UI, stable-diffusion.cpp, FastSD CPU, RKNN SD, rk-llama.cpp |
| **Video Gen** | WanGP (Wan 2.1/2.2, HunyuanVideo), LTX Video |
| **Voice/Audio** | Whisper STT, Piper TTS, Kokoro TTS, Chatterbox, MusicGPT |
| **AI Tools** | Perplexica (AI search), Open WebUI, Dify, SearXNG |
| **Infrastructure** | Gitea, Code Server, n8n, Docker Mailserver, Tailscale, Dynamic DNS |
| **Home & Monitoring** | Home Assistant, Uptime Kuma, File Browser, Excalidraw, Memos, Linkwarden |

## Supported Hardware

| Category | Hardware | Notes |
|----------|----------|-------|
| **Apple Silicon** | Mac Mini, MacBook, Mac Studio, Mac Pro (M1-M5) | MLX-accelerated via Ollama (93% faster), 8-192GB unified memory |
| **ARM + Rockchip NPU** | Orange Pi 5/5 Plus, Rock 5B | 6 TOPS NPU, primary SBC target |
| **Raspberry Pi** | Pi 4 (8GB), Pi 5 (8/16GB) | CPU-only or with accelerator HATs |
| **Pi Accelerators** | Hailo-10H (40T), M5Stack LLM-8850 (24T) | LLM-capable accelerators |
| **NVIDIA** | GTX 1050 Ti through RTX 4090/5090 | CUDA 4-24GB or Vulkan legacy |
| **AMD** | RX 6600 through RX 7900 XTX | ROCm 8-24GB |
| **Android** | Flagship phones/tablets (12-16GB) | 7-8B models at 15-30 tok/s via Termux + llama.cpp |
| **iOS/iPadOS** | iPad Pro M4, iPhones (6-8GB+) | Dashboard via PWA, future native worker app |
| **CPU Only** | Any device | Smallest quantized models |
| **Mixed Cluster** | All of the above combined | A Mac, a Pi, a gaming PC, and an old phone — all working together |

## Architecture

```
TinyAgentOS Controller (FastAPI + htmx + React Desktop Shell)
├── Web Desktop Shell (window manager, dock, launchpad, widgets, 26 bundled apps)
├── Mobile/Tablet Shell (card switcher, pill bar, iOS PWA)
├── Skills & Plugins Registry (7 default skills, 15 framework adapters)
├── User Memory (SQLite + FTS5, auto-capture, global search integration)
├── Web Dashboard (27 route modules, 48 templates)
├── Channel Hub (6 connectors, 15 framework adapters)
│   ├── Telegram, Discord, Slack, Email, Web Chat, Webhooks
│   └── Universal message format → framework-specific translation
├── LLM Proxy (LiteLLM, per-agent virtual keys)
├── Cluster Manager (worker registration, task routing)
├── App Streaming (12 apps, KasmVNC, split-view + agent chat sidebar)
├── App Orchestrator (worker selection, container lifecycle)
├── User Workspace (NAS-like file browser, shared with apps + agents)
├── Computer Use (vision + keyboard/mouse, agent escalation)
├── Message Hub (chat, channels, threads, canvas, dual PWA)
├── App Store + Registry (87 apps + 43 MCP plugins, manifest-based)
├── Live Model Browser (HuggingFace + Ollama search)
├── Container Manager (LXC or Docker, auto-detected)
├── Agent Memory (QMD per agent — FTS5 + sqlite-vec + hybrid)
├── Health Monitor + Notifications
├── Secrets Manager (encrypted, per-agent access)
├── Task Scheduler (cron with presets)
├── Training Manager (LoRA, per-agent adapters)
├── Agent Export/Import (portable JSON config)
├── Agent Templates (1,467 vendored from 3 sources)
├── Global Search (agents, apps, messages, folders)
├── Backup Scheduler (daily/weekly automated backups)
└── Backend Fallback (priority-based, auto-recovery)

Worker Apps (Windows / macOS / Linux)
├── System tray icon (no dock/taskbar window)
├── Auto-discovers local inference backends
├── Reports hardware profile to controller
└── Heartbeat with load monitoring
```

## Resource Overhead

Platform overhead: **~345 MB RAM** (without models or agents)

## Service Management

TinyAgentOS ships with a systemd unit at `/etc/systemd/system/tinyagentos.service`. It auto-restarts on failure and auto-starts on boot.

```bash
sudo systemctl start tinyagentos
sudo systemctl stop tinyagentos
sudo systemctl restart tinyagentos
sudo systemctl status tinyagentos
```

On RK3588 boards with NPU image generation enabled, the CPU and NPU image backends ship as additional units at `tinyagentos-sdcpp.service` and `tinyagentos-rknn-sd.service`. Both are started and enabled by the install script.

## RK3588 NPU Image Generation — Runtime Version Pin

**If you're running image generation on the Rockchip NPU, `/usr/lib/librknnrt.so` must be version 2.3.0.** The LCM Dreamshaper UNet RKNN file was compiled with `rknn-toolkit2 2.3.0` (2024-11-07) and segfaults at the first UNet inference step under `librknnrt 2.3.2` (2025-04-09) due to tightened tensor-layout validation in the newer runtime. The data-format fix (NHWC on unet + vae_decoder) is necessary but not sufficient; the runtime also needs to match.

The install script pulls the correct version from darkbit1001's model repo. If you install manually, use:

```bash
curl -fL -o ~/.local/share/tinyagentos/rknn-sd/librknnrt.so \
  https://huggingface.co/darkbit1001/Stable-Diffusion-1.5-LCM-ONNX-RKNN2/resolve/main/librknnrt.so
sudo cp ~/.local/share/tinyagentos/rknn-sd/librknnrt.so /usr/lib/librknnrt.so
sudo ldconfig
```

Verify:

```bash
strings /usr/lib/librknnrt.so | grep "librknnrt version"
# librknnrt version: 2.3.0 (c949ad889d@2024-11-07T11:35:33)
```

**rkllama compatibility**: rkllama works fine on `librknnrt 2.3.0` — there's no regression vs. 2.3.2 for LLM / embedding / rerank workloads. The version pin is specifically about the pre-compiled LCM Dreamshaper UNet, not a general runtime downgrade.

**Rollback**: if you ever need to restore the newer runtime (losing NPU SD), `sudo cp /home/$USER/rkllama/src/rkllama/lib/librknnrt.so /usr/lib/librknnrt.so && sudo ldconfig`.

## Design Docs

- [docs/design/desktop-shell.md](docs/design/desktop-shell.md) — full desktop shell spec
- [docs/design/skills-plugins.md](docs/design/skills-plugins.md) — skills & plugins system
- [docs/design/user-memory.md](docs/design/user-memory.md) — user memory design
- [docs/design/plan-desktop-shell-core.md](docs/design/plan-desktop-shell-core.md) — shell implementation plan
- [docs/design/plan-desktop-os-apps.md](docs/design/plan-desktop-os-apps.md) — OS apps implementation plan
- [docs/design/plan-desktop-mobile-view.md](docs/design/plan-desktop-mobile-view.md) — mobile view implementation plan

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 959 tests
```

CI runs automatically on every push (Python 3.10-3.13 + security audit).

## Roadmap

### Done ✅
- [x] Web GUI with 26 pages
- [x] App Store (84 apps, 15 agent frameworks)
- [x] Live model browser (HuggingFace + Ollama, 167k+ models)
- [x] Agent deployment wizard (LXC containers)
- [x] Image + video generation (multi-backend)
- [x] Semantic vector search via qmd serve
- [x] Multi-host backend fallback with auto-recovery
- [x] Communication channels (8 types, Easy/Advanced)
- [x] Secrets manager (encrypted, per-agent access)
- [x] Distributed compute cluster with auto-optimise
- [x] Cross-platform worker apps (Windows/Mac/Linux/Android)
- [x] Authentication (password + sessions)
- [x] Model conversion pipeline (GGUF→RKLLM, capability-gated)
- [x] Agent workspace (virtual computer per agent)
- [x] Inter-agent messaging with transcript depth
- [x] Shared folders for agent groups
- [x] Training page with LoRA presets
- [x] Dynamic capability system (features unlock by hardware)
- [x] LLM Proxy (LiteLLM) with per-agent keys
- [x] Webhook notifications (Slack/Discord/Telegram)
- [x] Health debug page
- [x] Channel Hub — framework-agnostic messaging (6 connectors, 18 adapters)
- [x] Agent config export/import
- [x] Agent template library (1,467 templates from 3 sources)
- [x] Global search across all platform data
- [x] Dashboard activity feed + quick actions
- [x] Backup scheduling (daily/weekly/off)
- [x] Hardware-filtered model recommendations
- [x] PWA service worker with offline fallback
- [x] Bulk agent operations (start/stop/restart all)
- [x] Notification preferences (mute by event type)
- [x] Playwright E2E test scaffolding
- [x] Message Hub — built-in chat with channels, threads, canvas, dual PWA
- [x] Dual container runtime (LXC + Docker, auto-detected)
- [x] Web desktop shell (window manager, dock, launchpad, widgets, 26 bundled apps)
- [x] Mobile/tablet responsive mode with iOS PWA support
- [x] Persistent desktop sessions across devices (windows, dock, wallpaper)
- [x] User memory system (personal QMD with FTS5 + auto-capture)
- [x] Skills & plugins registry (7 default skills, per-framework compatibility)
- [x] Terminal app with real PTY + SSH client
- [x] Standalone Chat PWA at /chat-pwa
- [x] Browser app with URL-rewriting proxy
- [x] 43 MCP server plugins in app catalog
- [x] Desktop notifications (toast stack + notification centre)
- [x] Widget system (Clock, Agent Status, Notes, System Stats, Weather)
- [x] Curated local model catalog — 97 manifests, all download URLs verified against HuggingFace
- [x] Activity monitor app — rktop-inspired per-core CPU/NPU/thermal/GPU/process stats
- [x] Loaded Models panel in Model Browser — shows running models, purpose, and VRAM/RAM usage
- [x] iOS PWA pill bar — safe-area-aware bottom nav with back / home / card-switcher / notifications
- [x] Model download manager — writes to `data/models/`, streams progress, surfaces errors

### In Progress
- [ ] Fresh install test on clean hardware (#2)
- [ ] Containerised app streaming (#22) — all 5 plans complete: session store, streaming pages, user workspace, agent-bridge, expert agents, 12 app manifests (Blender/LibreOffice/GIMP/Code Server + 8 Phase 2), app orchestrator, computer-use with escalation, companion launcher API

### Planned
- [ ] Local assistant LLM / Setup Agent (#4)
- [ ] Pre-built Armbian images (#7)
- [ ] Automated Playwright tests (#8)
- [ ] Exo integration for pipeline-parallel inference

### Future Vision
- [ ] Cloud services — tinyagentos.com (#5)
- [ ] AI-aware desktop with containerised app streaming (#6) — wrap apps with pre-wired MCP, stream via browser/Moonlight, companion app launcher
- [ ] Mobile worker native apps (iOS/Android)
- [ ] Dynamic NPU core allocation (#13)
- [ ] Ray as optional cluster backend for large-scale deployments (#23)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines. Join [GitHub Discussions](https://github.com/jaylfc/tinyagentos/discussions) for questions and ideas.

## Support the Project

TinyAgentOS makes AI agents accessible on affordable hardware.

- **Contact:** jaylfc25@gmail.com
- **Donate:** [Buy Me a Coffee](https://buymeacoffee.com/jaylfc)
- **Hardware donations/loans:** We test on real hardware. If you have spare SBCs, GPUs, or dev boards and want to help expand compatibility, reach out.

## License

MIT
