# TinyAgentOS

Self-hosted AI agent memory system for low-power hardware. Web GUI for monitoring and managing AI agents, their memory, and inference backends.

## Quick Start

```bash
pip install -e .
python -m uvicorn tinyagentos.app:create_app --factory --host 0.0.0.0 --port 8888
```

Open `http://your-host:8888` in your browser.

## Supported Agent Frameworks

TinyAgentOS works with any agent framework that can make HTTP calls. First-class support for:

| Framework | Type | Notes |
|-----------|------|-------|
| [OpenClaw](https://github.com/openclaw/openclaw) | Full agent framework | Gateway protocol, multi-channel |
| [nanoclaw](https://github.com/openclaw/nanoclaw) | Lightweight OpenClaw | Minimal footprint |
| [picoclaw](https://github.com/openclaw/picoclaw) | Micro OpenClaw | Smallest possible agent |
| [SmolAgents](https://github.com/huggingface/smolagents) | Code-based agents | 26k stars, 30% fewer LLM calls |
| [PocketFlow](https://github.com/the-pocket/PocketFlow) | 100-line framework | Zero deps, graph-based |
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
    ├── Dashboard — KPIs, backend status, metrics charts
    ├── Memory Browser — search/browse agent memories
    ├── Agents — CRUD, status monitoring
    └── Config — YAML editor with validation

    Talks to:
    ├── Each agent's QMD serve instance (per-agent, in LXC)
    ├── Inference backends (rkllama, ollama, llama.cpp, vLLM)
    └── Metrics DB (local SQLite)
```

Agent data (memory, QMD database) always lives inside the agent's LXC container. TinyAgentOS accesses it via each agent's `qmd_url` over HTTP. This ensures multi-host fallback works.

## Investigating

- [Outlines](https://github.com/dottxt-ai/outlines) — structured generation for reliable tool calling with small models
- [DSPy](https://github.com/stanfordnlp/dspy) — automated prompt optimization for small local LLMs

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Hardware Targets

- **arm-npu-16gb**: Orange Pi 5 Plus (RK3588) with NPU
- **x86-vulkan-4gb**: GTX 1050 Ti, dynamic model swapping
- **x86-vulkan-8gb**: GTX 1070/1080
- **x86-rocm-12gb**: AMD RX 6700 XT
- **x86-cuda-12gb**: RTX 3060
- **cpu-only**: Fallback, slowest

## Support the Project

TinyAgentOS is built by [JAN LABS](https://github.com/jaylfc) — making AI agents accessible on affordable hardware.

- **Contact:** jaylfc25@gmail.com
- **Donate:** [Buy Me a Coffee](https://buymeacoffee.com/jaylfc)
- **Hardware donations/loans:** We test on real hardware. If you have spare SBCs, GPUs, or dev boards and want to help expand compatibility, reach out at the email above.

## License

MIT
