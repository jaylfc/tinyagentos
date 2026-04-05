"""Deterministic SVG avatar generator for lobby agents."""

from __future__ import annotations

import hashlib


def _initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper()


def _name_to_colour(name: str) -> str:
    h = hashlib.md5(name.encode()).hexdigest()
    # Pick a hue from 0-360, keep saturation/lightness pleasant
    hue = int(h[:3], 16) % 360
    return f"hsl({hue}, 55%, 45%)"


def generate_avatar_svg(name: str, size: int = 40) -> str:
    """Return an inline SVG string: coloured circle with white initials."""
    colour = _name_to_colour(name)
    initials = _initials(name)
    r = size // 2
    font_size = size * 0.42
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
        f'<circle cx="{r}" cy="{r}" r="{r}" fill="{colour}"/>'
        f'<text x="50%" y="50%" dy=".35em" text-anchor="middle" '
        f'fill="white" font-family="system-ui,sans-serif" font-size="{font_size}" '
        f'font-weight="600">{initials}</text></svg>'
    )
