#!/usr/bin/env python3
"""Spike: does ez_rknn_async deliver meaningful concurrency wins on RK3588?

We do not compare against rknn-toolkit-lite2 for latency — they share the same
librknnrt underneath, so single-inference latency is expected to be equivalent.
The interesting question is what lite2 cannot do: overlap inference, run across
multiple cores, keep the NPU busy while the CPU prepares the next batch.

Tests, all on the LCM Dreamshaper unet.rknn (1.7 GB, the heaviest submodel):

    1. Cold load.
    2. 5 warm inferences, report median latency.
    3. 4 sequential inferences vs 4 via run_async. If async delivers real
       overlap, parallel wall time < sequential wall time.
    4. Repeat (3) with threads_per_core=3 to see if the library's own thread
       pool fans work across RK3588's 3 NPU cores.

Run on the Orange Pi 5 Plus; model dir must contain .rknn files.
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np

MODEL_DIR = Path(os.environ.get(
    "RKNN_SD_MODEL_DIR",
    Path.home() / ".local/share/tinyagentos/rknn-sd/model",
))

UNET_PATH = MODEL_DIR / "unet" / "model.rknn"
TEXT_ENCODER_PATH = MODEL_DIR / "text_encoder" / "model.rknn"
VAE_DECODER_PATH = MODEL_DIR / "vae_decoder" / "model.rknn"


_ORT_DTYPE_MAP = {
    "float": "float32",
    "float32": "float32",
    "float16": "float16",
    "double": "float64",
    "float64": "float64",
    "int8": "int8",
    "int16": "int16",
    "int32": "int32",
    "int64": "int64",
    "uint8": "uint8",
    "bool": "bool",
}


def _parse_ort_dtype(s: str) -> np.dtype:
    s = (s or "").replace("tensor(", "").replace(")", "").strip().lower()
    return np.dtype(_ORT_DTYPE_MAP.get(s, s or "float32"))


def _fmt_ms(values: list[float]) -> str:
    if not values:
        return "n/a"
    med = statistics.median(values)
    lo = min(values)
    hi = max(values)
    return f"{med*1000:7.1f} ms  (min {lo*1000:.1f}, max {hi*1000:.1f}, n={len(values)})"


def _random_feed(sess) -> tuple[dict, list[str]]:
    feed = {}
    for inp in sess.get_inputs():
        shape = tuple(int(d) if d and d > 0 else 1 for d in (inp.shape or [1]))
        dtype = _parse_ort_dtype(str(inp.type or "float32"))
        if np.issubdtype(dtype, np.floating):
            arr = np.random.randn(*shape).astype(dtype)
        else:
            arr = np.zeros(shape, dtype=dtype)
        feed[inp.name] = arr
    outs = [o.name for o in sess.get_outputs()]
    return feed, outs


def load_ez(path: Path, provider_options: dict | None = None):
    import ztu_somemodelruntime_ez_rknn_async as ez
    t0 = time.perf_counter()
    sess = ez.InferenceSession(
        str(path),
        provider_options=[provider_options] if provider_options else None,
    )
    return sess, time.perf_counter() - t0


def warm_latency(sess, feed, outs, warmup=1, repeats=5) -> list[float]:
    for _ in range(warmup):
        _ = sess.run(outs, feed)
    latencies = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        _ = sess.run(outs, feed)
        latencies.append(time.perf_counter() - t0)
    return latencies


def sequential_vs_async(sess, feed, outs, n=4):
    """Fire n inferences sequentially, then n via callback-based run_async."""
    import threading

    _ = sess.run(outs, feed)

    t0 = time.perf_counter()
    for _ in range(n):
        _ = sess.run(outs, feed)
    seq_wall = time.perf_counter() - t0

    if not hasattr(sess, "run_async"):
        return seq_wall, None, "run_async method not present"

    done = threading.Event()
    counter = {"n": 0}
    errors = []
    lock = threading.Lock()

    def cb(outputs, user_data=None, err=None):
        with lock:
            if err:
                errors.append(err)
            counter["n"] += 1
            if counter["n"] >= n:
                done.set()

    t0 = time.perf_counter()
    try:
        for i in range(n):
            sess.run_async(outs, feed, cb, i)
    except Exception as exc:
        return seq_wall, None, f"run_async submit failed: {type(exc).__name__}: {exc}"
    if not done.wait(timeout=max(60.0, seq_wall * 2)):
        return seq_wall, None, f"run_async timed out after {counter['n']}/{n} completions"
    async_wall = time.perf_counter() - t0

    if errors:
        return seq_wall, async_wall, f"async completed with {len(errors)} errors: {errors[0]}"
    return seq_wall, async_wall, None


def main():
    print(f"model dir: {MODEL_DIR}")
    for p in (UNET_PATH, TEXT_ENCODER_PATH, VAE_DECODER_PATH):
        if not p.exists():
            print(f"missing: {p}", file=sys.stderr)
            return 1

    import ztu_somemodelruntime_ez_rknn_async as ez
    print(f"ez_rknn_async: {getattr(ez, '__version__', '?')}")

    # The heavy SD submodels need layout=nhwc to match darkbit1001's wrapper.
    # Without it we get "unsupported src layout: NCHW" errors during inference.
    LAYOUT_NHWC = {"layout": "nhwc"}

    print("\n=== 1. Cold load + warm latency (layout-correct) ===")
    print(f"{'model':<14} {'cold':<12} {'warm':<60}")
    print("-" * 90)
    for name, path, opts in (
        ("text_encoder", TEXT_ENCODER_PATH, None),
        ("unet",         UNET_PATH,         LAYOUT_NHWC),
        ("vae_decoder",  VAE_DECODER_PATH,  LAYOUT_NHWC),
    ):
        try:
            sess, cold = load_ez(path, opts)
            feed, outs = _random_feed(sess)
            lat = warm_latency(sess, feed, outs)
            print(f"{name:<14} {cold:6.2f} s    {_fmt_ms(lat):<60}")
            del sess
        except Exception as exc:
            print(f"{name:<14} FAILED: {type(exc).__name__}: {exc}")

    print("\n=== 2. Sequential vs callback run_async on unet (tp_mode=auto) ===")
    sess, _ = load_ez(UNET_PATH, {"layout": "nhwc"})
    feed, outs = _random_feed(sess)
    n = 4
    seq, asy, err = sequential_vs_async(sess, feed, outs, n=n)
    print(f"  {n} sequential runs:    {seq*1000:8.1f} ms  ({seq/n*1000:7.1f} ms / run)")
    if err:
        print(f"  {n} run_async runs:    {err}")
    else:
        print(f"  {n} run_async runs:    {asy*1000:8.1f} ms  ({asy/n*1000:7.1f} ms / run)")
        if asy > 0:
            print(f"  speedup (seq / async): {seq/asy:.2f}x")
    del sess

    print("\n=== 3. tp_mode='all' on unet (use all 3 NPU cores for one model) ===")
    try:
        sess, cold = load_ez(UNET_PATH, {"layout": "nhwc", "tp_mode": "all"})
        feed, outs = _random_feed(sess)
        print(f"  load: {cold:.2f} s")
        lat = warm_latency(sess, feed, outs, repeats=3)
        print(f"  single run warm:  {_fmt_ms(lat)}")
        del sess
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")

    print("\n=== 4. Two sessions on cores 0 and 1, run in parallel threads ===")
    try:
        import threading
        sess_a, _ = load_ez(UNET_PATH, {"layout": "nhwc", "tp_mode": "0"})
        sess_b, _ = load_ez(UNET_PATH, {"layout": "nhwc", "tp_mode": "1"})
        feed_a, outs_a = _random_feed(sess_a)
        feed_b, outs_b = _random_feed(sess_b)
        sess_a.run(outs_a, feed_a)
        sess_b.run(outs_b, feed_b)

        t0 = time.perf_counter()
        sess_a.run(outs_a, feed_a)
        sess_b.run(outs_b, feed_b)
        seq = time.perf_counter() - t0

        def _t(s, f, o):
            s.run(o, f)
        t0 = time.perf_counter()
        ta = threading.Thread(target=_t, args=(sess_a, feed_a, outs_a))
        tb = threading.Thread(target=_t, args=(sess_b, feed_b, outs_b))
        ta.start(); tb.start()
        ta.join(); tb.join()
        par = time.perf_counter() - t0

        print(f"  sequential (2 calls, 2 sessions): {seq*1000:8.1f} ms")
        print(f"  parallel   (2 threads, cores 0+1):{par*1000:8.1f} ms")
        print(f"  speedup: {seq/par:.2f}x")
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")

    print("\nspike done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
