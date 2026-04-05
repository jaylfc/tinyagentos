"""MCP tool definition for agent image generation via any OpenAI-compatible backend."""
from __future__ import annotations

# MCP tool schema — agents can call this to generate images
IMAGE_GENERATION_TOOL = {
    "name": "generate_image",
    "description": "Generate an image from a text prompt using your local AI backend (rkllama, ollama, or standalone SD server). Returns the image as a base64-encoded PNG.",
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of the image to generate",
            },
            "size": {
                "type": "string",
                "enum": ["256x256", "384x384", "512x512"],
                "description": "Image dimensions (default 512x512)",
                "default": "512x512",
            },
            "steps": {
                "type": "integer",
                "description": "Number of inference steps (1-8, default 4 for LCM)",
                "default": 4,
                "minimum": 1,
                "maximum": 8,
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility (omit for random)",
            },
        },
        "required": ["prompt"],
    },
}


async def execute_image_generation(
    prompt: str,
    backend_url: str = "http://localhost:8080",
    model: str = "lcm-dreamshaper-v7",
    size: str = "512x512",
    steps: int = 4,
    seed: int | None = None,
    guidance_scale: float = 7.5,
) -> dict:
    """Execute image generation via an OpenAI-compatible endpoint.

    Works with rkllama, ollama, or any backend serving ``/v1/images/generations``.
    Returns dict with 'success', 'image_b64' (base64 PNG), and 'error' if failed.
    """
    import httpx
    import random

    if seed is None:
        seed = random.randint(1, 999999)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{backend_url.rstrip('/')}/v1/images/generations",
                json={
                    "prompt": prompt,
                    "model": model,
                    "size": size,
                    "n": 1,
                    "num_inference_steps": steps,
                    "seed": seed,
                    "guidance_scale": guidance_scale,
                    "response_format": "b64_json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if "data" in data and len(data["data"]) > 0:
                return {
                    "success": True,
                    "image_b64": data["data"][0].get("b64_json", ""),
                    "seed": seed,
                    "model": model,
                    "size": size,
                }
            return {"success": False, "error": "No image data in response"}
    except httpx.ConnectError:
        return {"success": False, "error": f"Cannot connect to image backend at {backend_url}"}
    except httpx.TimeoutException:
        return {"success": False, "error": "Image generation timed out (>120s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
