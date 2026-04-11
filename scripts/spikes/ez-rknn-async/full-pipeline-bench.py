"""Full LCM pipeline wall-time benchmark for the ez_rknn_async backend.

Calls the FastAPI endpoint at localhost:7863 and measures total wall time
for a 4-step 512x512 generation. Reports per-stage timing from server logs
if available.

Usage:
    python full-pipeline-bench.py [--host HOST] [--port PORT] [--runs N]

Defaults:
    host=localhost, port=7863, runs=3
    prompt="a cat sitting on a chair", steps=4, size=512x512
"""
import argparse
import json
import statistics
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx not found — install with: pip install httpx", file=sys.stderr)
    sys.exit(1)


PROMPT = "a cat sitting on a chair"
STEPS = 4
SIZE = "512x512"


def check_health(base_url: str) -> dict:
    resp = httpx.get(f"{base_url}/health", timeout=10)
    resp.raise_for_status()
    return resp.json()


def generate(base_url: str, seed: int) -> tuple[float, dict]:
    """Run one generation. Returns (wall_seconds, response_body)."""
    payload = {
        "prompt": PROMPT,
        "steps": STEPS,
        "size": SIZE,
        "seed": seed,
        "response_format": "b64_json",
    }
    t0 = time.perf_counter()
    resp = httpx.post(
        f"{base_url}/v1/images/generations",
        json=payload,
        timeout=300,
    )
    wall = time.perf_counter() - t0
    resp.raise_for_status()
    return wall, resp.json()


def main():
    parser = argparse.ArgumentParser(description="LCM pipeline wall-time benchmark")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7863)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    print(f"=== TinyAgentOS RKNN SD Full Pipeline Benchmark ===")
    print(f"Endpoint : {base_url}")
    print(f"Prompt   : {PROMPT!r}")
    print(f"Steps    : {STEPS}")
    print(f"Size     : {SIZE}")
    print(f"Runs     : {args.runs}")
    print()

    # Health check
    try:
        health = check_health(base_url)
    except Exception as e:
        print(f"ERROR: Cannot reach {base_url}/health — {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Health   : {health}")
    runtime = health.get("runtime", "unknown")
    print(f"Runtime  : {runtime}")
    print(f"Pipeline loaded: {health.get('pipeline_loaded', '?')}")
    print()

    # Note: first run may pay the lazy-load penalty (~30-50s model load)
    wall_times = []
    server_elapsed = []

    for i in range(args.runs):
        seed = 42 + i
        print(f"Run {i + 1}/{args.runs} (seed={seed}) ...", end=" ", flush=True)
        try:
            wall, body = generate(base_url, seed)
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            sys.exit(1)

        wall_times.append(wall)
        usage = body.get("usage", {})
        server_s = usage.get("elapsed_seconds")
        if server_s is not None:
            server_elapsed.append(server_s)
            print(f"wall={wall:.2f}s  server_reported={server_s:.2f}s")
        else:
            print(f"wall={wall:.2f}s")

    print()
    print("=== Results ===")
    print(f"Runtime           : {runtime}")
    print(f"Prompt            : {PROMPT!r}")
    print(f"Steps / Size      : {STEPS} / {SIZE}")
    print()
    print(f"Wall time (client-side, includes network):")
    for i, t in enumerate(wall_times):
        label = "  [first/lazy-load]" if i == 0 and t > 40 else ""
        print(f"  Run {i + 1}: {t:.2f}s{label}")
    if len(wall_times) > 1:
        warm = wall_times[1:]  # skip first (lazy load penalty)
        print(f"  Warm runs avg : {statistics.mean(warm):.2f}s")
        if len(warm) > 1:
            print(f"  Warm runs min : {min(warm):.2f}s")
            print(f"  Warm runs max : {max(warm):.2f}s")
    if server_elapsed:
        warm_srv = server_elapsed[1:] if len(server_elapsed) > 1 else server_elapsed
        print(f"Server-reported elapsed (generation only):")
        for i, t in enumerate(server_elapsed):
            print(f"  Run {i + 1}: {t:.2f}s")
        print(f"  Warm avg: {statistics.mean(warm_srv):.2f}s")


if __name__ == "__main__":
    main()
