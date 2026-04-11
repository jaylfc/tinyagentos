"""OpenAI-compatible image generation server backed by RKNN2 Stable Diffusion on RK3588.

Default backend: ez_rknn_async (happyme531's ztu_somemodelruntime_ez_rknn_async).
  - tp_mode=all on unet + vae_decoder gives ~1.26x / 1.25x single-inference wins.
  - layout='nhwc' is handled inside the ez runtime (no Python-side transpose needed).

Legacy backend (rknn-toolkit-lite2 / darkbit1001's rknnlcm.py): set
  RKNN_SD_LEGACY_WRAPPER=1  to revert to the old path if ez breaks on your install.

Exposes POST /v1/images/generations so the TinyAgentOS Images app can call
the NPU backend identically to the CPU sd.cpp backend.

Environment:
  RKNN_SD_MODEL_DIR        directory containing text_encoder/unet/vae_decoder (default: ~/.local/share/tinyagentos/rknn-sd/model)
  RKNN_SD_WRAPPER          path to rknnlcm.py for legacy path               (default: ~/.local/share/tinyagentos/rknn-sd/rknnlcm.py)
  RKNN_SD_LEGACY_WRAPPER   set to 1 to force the rknn-toolkit-lite2 path    (default: unset / use ez)
  RKNN_SD_HOST             bind host                                         (default: 0.0.0.0)
  RKNN_SD_PORT             bind port                                         (default: 7863)

Run:
  python -m tinyagentos.services.rknn_sd_server
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("rknn_sd_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_HOME = Path.home() / ".local" / "share" / "tinyagentos" / "rknn-sd"
MODEL_DIR = Path(os.environ.get("RKNN_SD_MODEL_DIR", DEFAULT_HOME / "model"))
WRAPPER_PATH = Path(os.environ.get("RKNN_SD_WRAPPER", DEFAULT_HOME / "rknnlcm.py"))
HOST = os.environ.get("RKNN_SD_HOST", "0.0.0.0")
PORT = int(os.environ.get("RKNN_SD_PORT", "7863"))
USE_LEGACY_WRAPPER = os.environ.get("RKNN_SD_LEGACY_WRAPPER", "").strip() == "1"


def _load_wrapper_module():
    """Import darkbit1001's patched rknnlcm.py as a module, adding its dir to sys.path
    so its own helpers and the scheduler config load correctly."""
    if not WRAPPER_PATH.exists():
        raise FileNotFoundError(f"Wrapper script not found: {WRAPPER_PATH}")
    wrapper_dir = str(WRAPPER_PATH.parent)
    if wrapper_dir not in sys.path:
        sys.path.insert(0, wrapper_dir)
    spec = importlib.util.spec_from_file_location("rknnlcm", WRAPPER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {WRAPPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rknnlcm"] = module
    spec.loader.exec_module(module)
    return module


def _build_pipeline(wrapper_module):
    """Instantiate the LCM pipeline with text_encoder NCHW + UNet/VAE decoder NHWC.

    The data_format=nhwc on UNet and VAE is THE fix — it bypasses the runtime's
    broken NCHW→NHWC auto-conversion path on librknnrt 2.3.2 by doing the
    transpose in Python before handing the tensor to rknnlite.inference().
    """
    import json

    from diffusers.schedulers import LCMScheduler
    from transformers import CLIPTokenizer

    scheduler_config_path = MODEL_DIR / "scheduler" / "scheduler_config.json"
    with scheduler_config_path.open() as f:
        scheduler = LCMScheduler.from_config(json.load(f))

    logger.info("Loading RKNN submodels — text_encoder (nchw), unet (nhwc), vae_decoder (nhwc)")
    pipe = wrapper_module.RKNN2LatentConsistencyPipeline(
        text_encoder=wrapper_module.RKNN2Model(str(MODEL_DIR / "text_encoder"), data_format="nchw"),
        unet=wrapper_module.RKNN2Model(str(MODEL_DIR / "unet"), data_format="nhwc"),
        vae_decoder=wrapper_module.RKNN2Model(str(MODEL_DIR / "vae_decoder"), data_format="nhwc"),
        scheduler=scheduler,
        tokenizer=CLIPTokenizer.from_pretrained("openai/clip-vit-base-patch16"),
    )
    return pipe


class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = "lcm-dreamshaper-v7-rknn"
    size: str = "512x512"
    n: int = 1
    response_format: str = Field("b64_json", pattern="^(b64_json|url)$")
    seed: Optional[int] = None
    steps: int = Field(4, ge=1, le=20)
    guidance_scale: float = Field(7.5, ge=0.0, le=20.0)


app = FastAPI(title="RKNN Stable Diffusion", version="0.1.0")
_pipe = None
_load_error: Optional[str] = None
_runtime_name: str = "ez_rknn_async" if not USE_LEGACY_WRAPPER else "rknn-toolkit-lite2"
_pipe_lock = asyncio.Lock()  # serialise lazy loads on the first concurrent request


def _build_pipeline_ez():
    """Build the LCM pipeline using the ez_rknn_async backend (default).

    Uses tp_mode=all on unet and vae_decoder for the ~1.26x / 1.25x
    single-inference wins measured on 2026-04-11. text_encoder uses
    tp_mode=0 (single core; the model is tiny — no benefit from all).
    """
    from tinyagentos.services import rknn_sd_ez
    logger.info("using ez_rknn_async backend (tp_mode=all on unet/vae)")
    return rknn_sd_ez.build_pipeline(str(MODEL_DIR))


def _ensure_pipeline_sync():
    """Build the RKNN pipeline if it isn't loaded yet. Safe to call
    repeatedly; idempotent. Called from /generate's lazy-load path.
    The previous startup hook eagerly built the pipeline at boot,
    pinning ~5.5 GB of RAM permanently even when the user wasn't
    generating any images. Lazy loading frees the NPU memory budget
    for chat models / TTS / etc when image gen is idle. Sequential
    eviction is the next piece (Phase 1.5)."""
    global _pipe, _load_error, _runtime_name
    if _pipe is not None:
        return
    try:
        start = time.time()
        if USE_LEGACY_WRAPPER:
            logger.info("RKNN_SD_LEGACY_WRAPPER=1 — using rknn-toolkit-lite2 path")
            module = _load_wrapper_module()
            _pipe = _build_pipeline(module)
            _runtime_name = "rknn-toolkit-lite2"
        else:
            _pipe = _build_pipeline_ez()
            _runtime_name = "ez_rknn_async"
        logger.info(f"Pipeline lazy-loaded in {time.time() - start:.1f}s (runtime={_runtime_name})")
    except Exception as exc:
        _load_error = str(exc)
        logger.exception("Failed to load RKNN pipeline")
        raise


async def _ensure_pipeline():
    if _pipe is not None:
        return
    async with _pipe_lock:
        if _pipe is not None:
            return
        # The actual model load is sync + heavy; offload to a worker
        # thread so we don't block the event loop while ~5 GB of
        # weights stream into NPU memory.
        await asyncio.get_running_loop().run_in_executor(None, _ensure_pipeline_sync)


@app.on_event("startup")
async def _startup():
    # Intentionally empty: the pipeline is now lazy-loaded on the first
    # /generate request. Old behaviour was to build the full pipeline
    # here, which pinned ~5.5 GB of RAM at boot for users who never
    # actually used image gen.
    logger.info("rknn_sd_server up — pipeline will lazy-load on first /generate request")


@app.get("/health")
async def health():
    # Health is independent of pipeline state — the server is alive
    # even before the first lazy load. The 'pipeline_loaded' field
    # tells callers whether the next /generate will pay the load
    # latency or hit a warm pipeline. 'runtime' shows which backend
    # will be (or was) used: "ez_rknn_async" (default) or "rknn-toolkit-lite2".
    return {
        "status": "ok",
        "model": "lcm-dreamshaper-v7-rknn",
        "backend": "rknn2",
        "runtime": _runtime_name,
        "pipeline_loaded": _pipe is not None,
        "load_error": _load_error,
    }


@app.get("/v1/models")
async def list_models():
    return {
        "data": [
            {
                "id": "lcm-dreamshaper-v7-rknn",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "tinyagentos",
            }
        ],
        "object": "list",
    }


@app.post("/v1/images/generations")
async def generate(body: GenerateRequest):
    # Lazy load on first call. The build is offloaded to a worker
    # thread inside _ensure_pipeline so it doesn't block the event
    # loop while ~5 GB of weights stream in.
    try:
        await _ensure_pipeline()
    except Exception as exc:
        raise HTTPException(503, _load_error or f"pipeline failed to load: {exc}")
    if body.n != 1:
        raise HTTPException(400, "n > 1 not supported on this backend")

    try:
        height_s, width_s = body.size.split("x")
        height, width = int(height_s), int(width_s)
    except ValueError:
        raise HTTPException(400, f"invalid size: {body.size}")

    seed = body.seed if body.seed is not None else random.randint(0, 2**31 - 1)

    logger.info(
        f"generate prompt={body.prompt!r} size={width}x{height} steps={body.steps} seed={seed}"
    )
    start = time.time()
    result = _pipe(
        prompt=body.prompt,
        height=height,
        width=width,
        num_inference_steps=body.steps,
        guidance_scale=body.guidance_scale,
        generator=np.random.RandomState(seed),
    )
    elapsed = time.time() - start
    logger.info(f"generation complete in {elapsed:.1f}s")

    image = result["images"][0]
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "created": int(time.time()),
        "data": [
            {
                "b64_json": b64,
                "revised_prompt": body.prompt,
            }
        ],
        "model": "lcm-dreamshaper-v7-rknn",
        "usage": {"elapsed_seconds": round(elapsed, 2), "seed": seed},
    }


def main():
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
