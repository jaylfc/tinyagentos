"""ez_rknn_async adapter for the RKNN Stable Diffusion LCM pipeline.

Replaces darkbit1001's rknnlcm.py / rknn-toolkit-lite2 path with
happyme531's ztu_somemodelruntime_ez_rknn_async library.

Key wins (measured 2026-04-11 on RK3588 / Orange Pi 5 Plus):
  - tp_mode='all' on unet:        ~1.26x single-inference speedup
  - tp_mode='all' on vae_decoder: ~1.25x single-inference speedup
  - Concurrent multi-session:     ~1.78x via core-pinned sessions

Input shape contract (with layout='nhwc' provider option):
  - The ez runtime accepts NCHW from Python and converts to NHWC
    internally before sending to the NPU — no Python-side transpose needed.
  - text_encoder stays NCHW (default, no layout option required).
  - unet timestep must be int64 (the rknn model reports int64, not int32).
  - All other float inputs are fed as float16 (model native dtype).

License: AGPL-3.0-or-later (matches project; ez library is also AGPL).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("rknn_sd_server")

# ---------------------------------------------------------------------------
# dtype helper (mirrors _parse_ort_dtype from spike/bench.py)
# ---------------------------------------------------------------------------

_ORT_DTYPE_MAP: Dict[str, np.dtype] = {
    "tensor(float16)": np.float16,
    "tensor(float)":   np.float32,
    "tensor(float32)": np.float32,
    "tensor(int64)":   np.int64,
    "tensor(int32)":   np.int32,
}


def _parse_ort_dtype(type_str: str) -> np.dtype:
    dt = _ORT_DTYPE_MAP.get(type_str)
    if dt is None:
        raise ValueError(f"Unknown ORT type string: {type_str!r}")
    return np.dtype(dt)


# ---------------------------------------------------------------------------
# RKNN2Model — drop-in replacement backed by ez InferenceSession
# ---------------------------------------------------------------------------

class RKNN2Model:
    """Callable wrapper around ez.InferenceSession.

    Construction::

        RKNN2Model(model_dir, layout="nhwc", tp_mode="all")

    Calling convention matches darkbit1001's original::

        model(**kwargs) -> list[np.ndarray]

    The wrapper builds the input_feed dict dynamically from
    session.get_inputs(), matching by kwarg name, and casts each
    tensor to the dtype reported by the model (preserving float16
    rather than force-casting to float32).
    """

    def __init__(
        self,
        model_dir: str,
        layout: str = "nchw",
        tp_mode: str = "all",
        **_ignored: Any,
    ) -> None:
        import ztu_somemodelruntime_ez_rknn_async as ez

        self.model_dir = model_dir
        self.modelname = os.path.basename(model_dir.rstrip("/"))
        self.layout = layout.lower()
        self.tp_mode = tp_mode

        rknn_path = os.path.join(model_dir, "model.rknn")
        if not os.path.exists(rknn_path):
            raise FileNotFoundError(f"model.rknn not found in {model_dir}")

        cfg_path = os.path.join(model_dir, "config.json")
        self.config: Dict[str, Any] = {}
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                self.config = json.load(f)

        provider_opts: Dict[str, Any] = {}
        if self.layout == "nhwc":
            provider_opts["layout"] = "nhwc"
        provider_opts["tp_mode"] = self.tp_mode

        logger.info(
            "Loading %s via ez_rknn_async (layout=%s tp_mode=%s)",
            self.modelname, self.layout, self.tp_mode,
        )
        t0 = time.time()
        self._session = ez.InferenceSession(rknn_path, provider_options=[provider_opts])
        logger.info("Loaded %s in %.1fs", self.modelname, time.time() - t0)

        # Cache input metadata for fast __call__ dispatch
        self._input_info: List[tuple] = [
            (inp.name, _parse_ort_dtype(inp.type))
            for inp in self._session.get_inputs()
        ]
        self._input_names = [n for n, _ in self._input_info]

    def __call__(self, **kwargs: Any) -> List[np.ndarray]:
        """Run synchronous inference.

        Accepts keyword arguments matching the model's input names.
        Extra kwargs are silently ignored (positional-order fallback
        is not used — explicit name matching only).
        """
        input_feed: Dict[str, np.ndarray] = {}
        for name, dtype in self._input_info:
            if name not in kwargs:
                raise KeyError(
                    f"{self.modelname}: missing required input {name!r}. "
                    f"Got: {list(kwargs.keys())}"
                )
            arr = kwargs[name]
            if isinstance(arr, np.ndarray):
                arr = np.ascontiguousarray(arr.astype(dtype, copy=False))
            input_feed[name] = arr

        results = self._session.run(None, input_feed)
        logger.debug(
            "%s out[0] shape=%s dtype=%s",
            self.modelname, results[0].shape, results[0].dtype,
        )
        return results


# ---------------------------------------------------------------------------
# Pipeline assembly
# ---------------------------------------------------------------------------

def build_pipeline(model_dir: str):
    """Build the LCM pipeline using ez_rknn_async models.

    Mirrors _build_pipeline() in rknn_sd_server.py but uses RKNN2Model
    from this module instead of importing rknnlcm.

    tp_mode defaults:
      text_encoder  -> "0"   (single core; tiny model, no multi-core benefit)
      unet          -> "all" (heaviest model; biggest tp_mode=all win)
      vae_decoder   -> "all" (second heaviest; biggest tp_mode=all win)
    """
    from diffusers.schedulers import LCMScheduler
    from transformers import CLIPTokenizer

    # Import pipeline class from the rknnlcm.py still living on-disk;
    # we only replace RKNN2Model — the pipeline orchestration logic
    # in RKNN2LatentConsistencyPipeline is unchanged.
    import importlib.util
    import sys

    wrapper_path = (
        Path.home() / ".local" / "share" / "tinyagentos" / "rknn-sd" / "rknnlcm.py"
    )
    wrapper_dir = str(wrapper_path.parent)
    if wrapper_dir not in sys.path:
        sys.path.insert(0, wrapper_dir)

    spec = importlib.util.spec_from_file_location("rknnlcm", wrapper_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load rknnlcm spec from {wrapper_path}")
    rknnlcm_mod = importlib.util.module_from_spec(spec)
    sys.modules["rknnlcm"] = rknnlcm_mod
    spec.loader.exec_module(rknnlcm_mod)

    mdir = Path(model_dir)

    scheduler_config_path = mdir / "scheduler" / "scheduler_config.json"
    with scheduler_config_path.open() as f:
        scheduler = LCMScheduler.from_config(json.load(f))

    logger.info(
        "Loading RKNN submodels via ez_rknn_async "
        "(text_encoder tp=0/nchw, unet tp=all/nhwc, vae_decoder tp=all/nhwc)"
    )

    text_encoder = RKNN2Model(
        str(mdir / "text_encoder"),
        layout="nchw",
        tp_mode="0",
    )
    unet = RKNN2Model(
        str(mdir / "unet"),
        layout="nhwc",
        tp_mode="all",
    )
    vae_decoder = RKNN2Model(
        str(mdir / "vae_decoder"),
        layout="nhwc",
        tp_mode="all",
    )

    tokenizer = CLIPTokenizer.from_pretrained("openai/clip-vit-base-patch16")

    pipe = rknnlcm_mod.RKNN2LatentConsistencyPipeline(
        text_encoder=text_encoder,
        unet=unet,
        vae_decoder=vae_decoder,
        scheduler=scheduler,
        tokenizer=tokenizer,
    )
    return pipe
