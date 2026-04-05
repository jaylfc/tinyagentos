# TinyAgentOS

Self-hosted AI agent platform for low-power hardware. Like [Umbrel](https://umbrel.com) but for AI agents — app store, model management, agent deployment, and system monitoring in a single web dashboard.

Run AI agents on a $150 Orange Pi, a budget x86 PC, or anything in between. Flash an image, open the browser, deploy your first agent.

## Quick Start

```bash
pip install -e .
python -m uvicorn tinyagentos.app:create_app --factory --host 0.0.0.0 --port 8888
```

Open `http://your-host:8888` in your browser.

## Features

### App Store
Browse and install agent frameworks, LLM models, and services from the built-in catalog. Hardware-aware recommendations — the store shows what works on your hardware.

### Model Manager
Download and manage LLM models with support for multiple formats (GGUF, RKLLM). Automatic variant selection based on your hardware profile (NPU, GPU, CPU).

### Agent Deployment
Create agents through a wizard — pick a framework, choose a model, configure, and deploy. Each agent gets its own LXC container with isolated memory and QMD serve.

### Dashboard
Real-time KPIs, backend health monitoring, agent status, and query latency metrics with Chart.js graphs. Auto-refreshes via htmx.

### Memory Browser
Search and browse agent memories using QMD's full-text search. Filter by agent and collection, view chunks, delete entries.

### System Config
YAML editor with validation, hardware profile display, catalog sync.

## App Catalog

| Type | Apps |
|------|------|
| **Agent Frameworks** | SmolAgents, PocketFlow, OpenClaw |
| **Models** | Qwen3 Embedding 0.6B, Reranker 0.6B, 1.7B, 4B, 8B |
| **Services** | Gitea (Git server), Code Server (web IDE) |

Models include RKLLM variants for Rockchip NPU and GGUF for CPU/GPU. Community can contribute apps via PR to the catalog repo.

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

## Supported Backends

| Backend | Type | API |
|---------|------|-----|
| [rkllama](https://github.com/notpunchnox/rkllama) | Rockchip NPU | Ollama-compatible |
| [ollama](https://ollama.ai) | CPU/GPU | Native |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | CPU/GPU/Vulkan | OpenAI-compatible |
| [vLLM](https://github.com/vllm-project/vllm) | GPU (CUDA/ROCm) | OpenAI-compatible |

## Architecture

```
TinyAgentOS (FastAPI + htmx, port 8888)
├── Dashboard  — KPIs, backend health, metrics charts
├── App Store  — browse/install frameworks, models, services
├── Models     — download, manage, assign LLM models
├── Memory     — search/browse agent memories
├── Agents     — deploy, manage, start/stop, logs
└── Settings   — config editor, hardware profile

Infrastructure:
├── App Registry      — manifest parsing, install tracking
├── Hardware Detector  — CPU, RAM, NPU, GPU, disk profiling
├── Installers        — pip/venv, Docker Compose, model downloads
├── Container Manager — LXC via incus (agent isolation)
├── Health Monitor    — background polling, metrics SQLite
└── Catalog Sync      — git-based app catalog updates
```

**Agent data always lives in the agent's LXC container.** TinyAgentOS accesses memory via each agent's QMD serve instance over HTTP. This enables multi-host fallback.

**Service apps use Docker.** Gitea, Code Server, and other services run as Docker containers managed via Docker Compose.

## Hardware Targets

| Profile | Example Hardware | Notes |
|---------|-----------------|-------|
| arm-npu-16gb | Orange Pi 5 Plus (RK3588) | Primary dev target, NPU accelerated |
| arm-npu-32gb | RK3588 32GB boards | More concurrent models |
| arm-npu-64gb+ | High-RAM ARM boards | Full model suite |
| x86-cuda-12gb | Budget PC + RTX 3060 | Fast GPU inference |
| x86-cuda-24gb | PC + RTX 3090/4090 | Large models |
| x86-vulkan-8gb | GTX 1070/1080 | Medium models via Vulkan |
| x86-rocm-12gb | AMD RX 6700 XT | AMD GPU support |
| cpu-only | Any device | Smallest quantized models |

Hardware is auto-detected on first boot. The platform adapts to what's available — users with more RAM or better accelerators get access to larger models automatically.

## Resource Overhead

Platform overhead (without models or agents): **~345 MB RAM**

| Component | RAM |
|-----------|-----|
| Armbian base | ~200 MB |
| TinyAgentOS (FastAPI) | ~67 MB |
| incusd (container management) | ~67 MB |
| Metrics + health monitor | ~5 MB |

## Investigating

- [Outlines](https://github.com/dottxt-ai/outlines) — structured generation for reliable tool calling with small models
- [DSPy](https://github.com/stanfordnlp/dspy) — automated prompt optimization for small local LLMs

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 123+ tests
```

## Roadmap

- [ ] Pre-built Armbian OS images for supported SBCs
- [ ] Local assistant LLM (chat-based setup agent)
- [ ] Cloud services (tinyagentos.com, agent email, subscriptions)
- [ ] AI-aware desktop environment with auto-attaching MCP servers
- [ ] Custom domain support for agents

## Support the Project

TinyAgentOS is built by [JAN LABS](https://github.com/jaylfc) — making AI agents accessible on affordable hardware.

- **Contact:** jaylfc25@gmail.com
- **Donate:** [Buy Me a Coffee](https://buymeacoffee.com/jaylfc)
- **Hardware donations/loans:** We test on real hardware. If you have spare SBCs, GPUs, or dev boards and want to help expand compatibility, reach out at the email above.

## License

MIT
