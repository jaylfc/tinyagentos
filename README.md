# TinyAgentOS

> **⚠️ Early Development** — This project is under active development and has not been tested on clean hardware yet. Do not install in production. Star/watch the repo to follow progress.

Self-hosted AI agent platform for low-power hardware. App store, model management, agent deployment, and system monitoring — all from a single web dashboard running on a $150 SBC or budget PC.

## Quick Start

```bash
pip install -e .
python -m uvicorn tinyagentos.app:create_app --factory --host 0.0.0.0 --port 8888
```

Open `http://your-host:8888` (or `http://tinyagentos.local:8888` with mDNS).

## Features

### App Store
Browse and install agent frameworks, LLM models, and services from a built-in catalog of 43+ apps. Hardware-aware recommendations filter what works on your hardware.

### Model Manager
Download and manage LLM models (GGUF, RKLLM). Background downloads with progress tracking. Automatic variant selection based on hardware profile.

### Agent Deployment
Create agents through a 5-step wizard — pick a framework, choose a model, configure, and deploy. Each agent gets its own LXC container with isolated memory.

### Image Generation
Generate images using Stable Diffusion on your NPU/GPU. Built-in gallery, prompt history, and an MCP tool so agents can generate images too.

### Memory Browser
Search and browse agent memories. Keyword search across agents, filter by collection, view/delete chunks.

### Communication Channels
Configure how agents communicate — Telegram, Discord, Slack, email, web chat, webhooks. Split into "Easy Setup" (no dev account needed) and "Advanced".

### Secrets Manager
Encrypted storage for API keys, tokens, and credentials. Per-agent access control — choose which agents can see each secret. Categories and groups for organisation.

### Scheduled Tasks
Manage cron jobs across agents. Built-in presets for common tasks (daily embedding, memory cleanup). Edit schedules, enable/disable, apply presets to agent groups.

### Data Import
Drag-and-drop files to embed into agent memory. Supports .txt, .md, .pdf, .html, .json, .csv.

### Dashboard
Real-time KPIs, CPU/RAM sparklines, backend health, agent status, query latency charts, and an activity feed. Auto-refreshes via htmx.

### Notifications
Bell icon in nav bar with health alerts. Backend up/down state changes trigger notifications. Mark read, notification history.

### Settings
System info, storage usage, backup/restore, system updates via git pull, platform config, test backend connections. Dark/light theme toggle.

### First Boot
Setup wizard detects hardware, shows quick-start links. Interactive onboarding tour on first visit.

## App Catalog (43+ apps)

| Type | Apps |
|------|------|
| **Agent Frameworks** | SmolAgents, PocketFlow, OpenClaw, nanoclaw, picoclaw, TinyAgent, Hermes, Agent Zero, Swarm, OpenAI Agents SDK, Langroid |
| **LLM Models** | Qwen3 Embedding 0.6B, Reranker 0.6B, 1.7B, 4B, 8B |
| **Image Models** | LCM Dreamshaper V7, SD 1.5 LCM, SDXL Turbo |
| **AI Tools** | Perplexica (AI search), Open WebUI (chat), ComfyUI, Fooocus, SD Web UI, stable-diffusion.cpp, FastSD CPU, RKNN SD, LCM Dreamshaper RKNN, Mali GPU SD |
| **Infrastructure** | Gitea, Code Server, n8n, Dify, SearXNG |
| **Home & Monitoring** | Home Assistant, Uptime Kuma, File Browser, Excalidraw, Memos, Linkwarden |
| **Voice** | Whisper (speech-to-text), Piper TTS (text-to-speech) |

## Supported Agent Frameworks

| Framework | Type | Notes |
|-----------|------|-------|
| [OpenClaw](https://github.com/openclaw/openclaw) | Full agent framework | Multi-channel (Discord, Telegram, Slack, Signal) |
| [nanoclaw](https://github.com/openclaw/nanoclaw) | Lightweight OpenClaw | Minimal footprint |
| [picoclaw](https://github.com/openclaw/picoclaw) | Micro OpenClaw | Smallest possible agent |
| [SmolAgents](https://github.com/huggingface/smolagents) | Code-based agents | 26k stars, 30% fewer LLM calls |
| [PocketFlow](https://github.com/the-pocket/PocketFlow) | 100-line framework | Zero deps, graph-based, MCP support |
| [TinyAgent](https://github.com/SqueezeAILab/TinyAgent) | Edge tool calling | 1-3B models with LLMCompiler |
| [Hermes](https://github.com/NousResearch/Hermes-Function-Calling) | Function calling | Nous Research |
| [Agent Zero](https://github.com/frdel/agent-zero) | Autonomous agent | Self-correcting workflows |
| [Swarm](https://github.com/openai/swarm) | Multi-agent handoffs | OpenAI, lightweight |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | Multi-agent orchestration | Provider-agnostic, guardrails |
| [Langroid](https://github.com/langroid/langroid) | Message-passing agents | Built-in vector store, local LLM support |

## Supported Inference Backends

| Backend | Type | API |
|---------|------|-----|
| [rkllama](https://github.com/notpunchnox/rkllama) | Rockchip NPU | Ollama-compatible |
| [ollama](https://ollama.ai) | CPU/GPU | Native |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | CPU/GPU/Vulkan | OpenAI-compatible |
| [vLLM](https://github.com/vllm-project/vllm) | GPU (CUDA/ROCm) | OpenAI-compatible |

## Hardware Support

| Category | Hardware | Notes |
|----------|----------|-------|
| **ARM + Rockchip NPU** | Orange Pi 5/5 Plus (RK3588), Rock 5B | 6 TOPS NPU, primary target |
| **Raspberry Pi** | Pi 4 (8GB), Pi 5 (8/16GB) | CPU-only or with accelerator HATs |
| **Pi Accelerators** | Hailo-10H (40 TOPS), M5Stack LLM-8850 (24 TOPS), Hailo-8L (13 TOPS) | LLM-capable: Hailo-10H, M5Stack |
| **NVIDIA** | GTX 1050 Ti through RTX 4090 | CUDA (4-24GB) or Vulkan (legacy) |
| **AMD** | RX 6600 through RX 7900 XTX | ROCm (8-24GB) |
| **CPU Only** | Any device | Smallest quantized models |

Hardware auto-detected on first boot. Platform recommends compatible models and apps.

## Architecture

```
TinyAgentOS (FastAPI + htmx, port 8888)
├── Dashboard    — KPIs, sparklines, activity feed, backend health
├── App Store    — 43+ apps, search, filters, install/uninstall
├── Models       — download with progress, hardware recommendations
├── Images       — generate via NPU/GPU, gallery, MCP tool
├── Memory       — search/browse agent memories via qmd serve
├── Channels     — Telegram, Discord, Slack, web chat, webhooks
├── Agents       — deploy wizard, LXC containers, logs viewer
├── Secrets      — encrypted storage, per-agent access control
├── Tasks        — scheduled jobs, presets, cron management
├── Import       — drag-and-drop file upload to agent memory
├── Settings     — system info, updates, backup/restore, test connections
└── Notifications — health alerts, activity feed, nav bell

Infrastructure:
├── Hardware Detector    — CPU, RAM, NPU (RKNPU/Hailo/Axera/Coral), GPU, disk
├── App Registry         — manifest parsing, install tracking, catalog sync
├── Secrets Store        — encrypted at rest, agent access control
├── Container Manager    — LXC via incus
├── Download Manager     — background downloads with progress
├── Task Scheduler       — cron-based with presets
├── Channel Store        — per-agent communication config
├── Health Monitor       — background polling, notifications on state change
├── Metrics Store        — SQLite time-series
└── Notification Store   — alerts, activity feed
```

## Resource Overhead

Platform overhead (without models or agents): **~345 MB RAM**

| Component | RAM |
|-----------|-----|
| Armbian base | ~200 MB |
| TinyAgentOS (FastAPI) | ~67 MB |
| incusd (container management) | ~67 MB |
| Metrics + health monitor | ~5 MB |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 180+ tests
```

## Roadmap

### In Progress
- [ ] Fresh install test on clean Orange Pi 5 Plus
- [ ] Pre-built Armbian OS images for supported SBCs
- [ ] Semantic vector search via qmd serve

### Planned
- [ ] Authentication system for web GUI
- [ ] Local assistant LLM (chat-based setup agent)
- [ ] Inter-agent relationship manager
- [ ] Progressive Web App (mobile-optimised)
- [ ] Automated Playwright test suite
- [ ] Multi-host inference fallback
- [ ] RKNN model conversion pipeline

### Future Vision
- [ ] Cloud services (tinyagentos.com, agent email, subscriptions)
- [ ] AI-aware desktop environment with auto-attaching MCP servers
- [ ] LoRA fine-tuning pipeline
- [ ] Dynamic NPU core allocation
- [ ] Custom domain support for agents

## Investigating

- [Outlines](https://github.com/dottxt-ai/outlines) — structured generation for reliable tool calling with small models
- [DSPy](https://github.com/stanfordnlp/dspy) — automated prompt optimization for small local LLMs

## Support the Project

TinyAgentOS makes AI agents accessible on affordable hardware.

- **Contact:** jaylfc25@gmail.com
- **Donate:** [Buy Me a Coffee](https://buymeacoffee.com/jaylfc)
- **Hardware donations/loans:** We test on real hardware. If you have spare SBCs, GPUs, or dev boards and want to help expand compatibility, reach out at the email above.

## License

MIT
