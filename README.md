# TinyAgentOS

> **⚠️ Early Development** — This project is under active development and has not been tested on clean hardware yet. Do not install in production. Star/watch the repo to follow progress.

Self-hosted AI agent platform that runs on whatever hardware you have. An old laptop, a Raspberry Pi, a gaming PC, an SBC gathering dust — or all of them at once. TinyAgentOS turns your spare hardware into a distributed AI compute cluster.

52+ apps, 167k+ searchable models, agent deployment, image/video/audio generation, and full system monitoring — all from a single web dashboard.

## Quick Start

```bash
pip install -e .
python -m uvicorn tinyagentos.app:create_app --factory --host 0.0.0.0 --port 8888
```

Open `http://your-host:8888` (or `http://tinyagentos.local:8888` with mDNS).

## Key Features

### Distributed Compute Cluster
Combine multiple devices into one AI compute mesh. A gaming PC handles large models, a laptop runs smaller ones, a Pi handles embeddings — all managed from one dashboard. Cross-platform worker apps (Windows, macOS, Linux) connect any machine to your cluster from the system tray.

```bash
# On any Windows/Mac/Linux machine — joins your cluster
tinyagentos-worker http://your-server:8888
```

### Live Model Browser
Search 167k+ GGUF models from HuggingFace and the Ollama library directly from the dashboard. Hardware-filtered compatibility indicators show what runs on your device (green/yellow/red).

### App Store (52+ Apps)
One-click install for agent frameworks, AI models, and services. Hardware-aware — only shows what works on your device.

### Agent Deployment
5-step wizard: pick framework → choose model → configure → deploy into isolated LXC container. Each agent gets its own memory system.

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

### Agent Management
- **Communication Channels** — Telegram, Discord, Slack, web chat, email, webhooks (Easy/Advanced setup)
- **Secrets Manager** — encrypted storage with per-agent access control
- **Inter-Agent Relationships** — groups, departments, lead agents, permissions matrix
- **Scheduled Tasks** — cron jobs with presets, per-agent or group assignment
- **Data Import** — drag-and-drop file upload to agent memory
- **Memory Browser** — keyword + semantic vector search across all agents

### Monitoring & Management
- **Dashboard** — KPIs, CPU/RAM sparklines, activity feed, backend health
- **Notifications** — health alerts, backend up/down state changes
- **Agent Logs** — real-time log viewer with auto-refresh
- **Backup & Restore** — downloadable config backup, one-click restore
- **System Updates** — pull latest from GitHub via Settings page

## App Catalog (52+ Apps)

| Category | Apps |
|----------|------|
| **Agent Frameworks** | SmolAgents, PocketFlow, OpenClaw, nanoclaw, picoclaw, TinyAgent, Hermes, Agent Zero, Swarm, OpenAI Agents SDK, Langroid |
| **LLM Models** | Qwen3 0.6B-8B (GGUF + RKLLM + MLX), plus 167k+ searchable from HuggingFace |
| **Image Models** | LCM Dreamshaper, SD 1.5 LCM, SDXL Turbo |
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
| **CPU Only** | Any device | Smallest quantized models |
| **Mixed Cluster** | All of the above combined | Distributed compute — a Mac, a Pi, and a gaming PC working together |

## Architecture

```
TinyAgentOS Controller (FastAPI + htmx)
├── Web Dashboard (13 pages + lobby demo)
├── Cluster Manager (worker registration, task routing)
├── App Store + Registry (52+ apps, manifest-based)
├── Live Model Browser (HuggingFace + Ollama search)
├── Container Manager (LXC via incus)
├── Health Monitor + Notifications
├── Secrets Manager (encrypted, per-agent access)
├── Channel Manager (8 channel types)
├── Task Scheduler (cron with presets)
└── Backend Fallback (priority-based, auto-recovery)

Worker Apps (Windows / macOS / Linux)
├── System tray icon (no dock/taskbar window)
├── Auto-discovers local inference backends
├── Reports hardware profile to controller
└── Heartbeat with load monitoring
```

## Resource Overhead

Platform overhead: **~345 MB RAM** (without models or agents)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 320+ tests
```

CI runs automatically on every push (Python 3.10-3.12 + security audit).

## Roadmap

### Done ✅
- [x] Web GUI with 13 pages
- [x] App Store (52+ apps)
- [x] Live model browser (HuggingFace + Ollama)
- [x] Agent deployment wizard (LXC)
- [x] Image generation (multi-backend)
- [x] Semantic vector search
- [x] Multi-host backend fallback
- [x] Communication channels
- [x] Secrets manager
- [x] Distributed compute cluster
- [x] Cross-platform worker apps

### In Progress
- [ ] Fresh install test on clean hardware (#2)
- [ ] Pre-built Armbian images (#7)
- [ ] Automated Playwright tests (#8)

### Planned
- [ ] Authentication system (#3)
- [ ] Local assistant LLM / Setup Agent (#4)
- [ ] RKNN model conversion pipeline (#10)
- [ ] Exo integration for model splitting

### Future Vision
- [ ] Cloud services — tinyagentos.com (#5)
- [ ] AI-aware desktop with auto-attaching MCP (#6)
- [ ] LoRA fine-tuning pipeline (#12)
- [ ] Dynamic NPU core allocation (#13)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines. Join [GitHub Discussions](https://github.com/jaylfc/tinyagentos/discussions) for questions and ideas.

## Support the Project

TinyAgentOS makes AI agents accessible on affordable hardware.

- **Contact:** jaylfc25@gmail.com
- **Donate:** [Buy Me a Coffee](https://buymeacoffee.com/jaylfc)
- **Hardware donations/loans:** We test on real hardware. If you have spare SBCs, GPUs, or dev boards and want to help expand compatibility, reach out.

## License

MIT
