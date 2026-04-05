# Raspberry Pi 5

| Field | Value |
|-------|-------|
| SoC | Broadcom BCM2712 (Cortex-A76) |
| RAM | 4 / 8 GB LPDDR4X |
| NPU | None (Hailo-8L via M.2 HAT+) |
| GPU | VideoCore VII |
| Storage | microSD, NVMe via HAT+ |
| Ethernet | 1x GbE |

## Kernel

Use **current** branch (Armbian mainline-based kernel for RPi5).

## Build Command

```bash
./build.sh rpi5 BRANCH=current
```

Or manually:

```bash
./compile.sh BOARD=rpi5 BRANCH=current RELEASE=bookworm BUILD_DESKTOP=no \
  ENABLE_EXTENSIONS=tinyagentos
```

## NPU Support

No integrated NPU. AI acceleration requires the Hailo-8L M.2 module on the
Raspberry Pi AI HAT+. Hailo support is **not yet integrated** into TinyAgentOS
images — this is planned for a future release.

Without an accelerator, inference falls back to CPU-only (slow for large models).

## Board-Specific Notes

- Most widely available SBC, good for development and testing.
- 8 GB RAM variant required for meaningful agent workloads.
- NVMe via M.2 HAT+ recommended for storage performance.
- No vendor kernel needed — mainline support is excellent.
- Board-specific patches: none currently required.
