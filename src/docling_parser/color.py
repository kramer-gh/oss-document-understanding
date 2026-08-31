"""Color palette extraction from rendered page images.

Uses PIL quantization to extract dominant and accent colors from a page
raster. This gives the design pipeline *measured* color data (hex codes from
real pixels) rather than relying on the VLM to guess hex values.
"""

from __future__ import annotations

import colorsys
import io
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

# Colors near-pure-white / near-pure-black are common but low-signal for
# design intelligence. We still include them in dominant but prefer saturated
# colors for accent.
_WHITE_THRESHOLD = 245
_BLACK_THRESHOLD = 12


@dataclass
class ColorInfo:
    """A single extracted color with metadata."""

    hex: str
    rgb: tuple[int, int, int]
    fraction: float  # fraction of pixels (0-1)
    hsv: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "hex": self.hex,
            "fraction": round(self.fraction, 4),
        }


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _is_near_white(rgb: tuple[int, int, int]) -> bool:
    return all(c >= _WHITE_THRESHOLD for c in rgb)


def _is_near_black(rgb: tuple[int, int, int]) -> bool:
    return all(c <= _BLACK_THRESHOLD for c in rgb)


def _saturation(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255 for c in rgb)
    _, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return s


def extract_palette(
    png_bytes: bytes,
    *,
    num_colors: int = 8,
    dominant_count: int = 5,
) -> dict[str, Any]:
    """Extract a color palette from a PNG image.

    Args:
        png_bytes: PNG image data.
        num_colors: Number of quantized colors to extract.
        dominant_count: How many dominant colors to return.

    Returns:
        A dict with ``dominant`` (list of hex strings sorted by frequency),
        ``accent`` (hex of the most saturated non-dominant color, or None),
        ``is_dark_theme`` (bool), and ``colors`` (detailed list).
    """
    img = Image.open(io.BytesIO(png_bytes))
    img = img.convert("RGB")

    # Downsample for speed — 100x100 is plenty for color clustering.
    img.thumbnail((100, 100))

    # Quantize to ``num_colors`` colors using PIL's fast median-cut.
    quantized = img.quantize(colors=num_colors, method=Image.MEDIANCUT)
    palette = quantized.getpalette()

    # Count pixel frequencies for each palette slot.
    histogram = quantized.histogram()

    # Build (color, count) pairs, filtering out fully-transparent / empty.
    # The palette is a flat list [r0,g0,b0, r1,g1,b1, ...]; it may be shorter
    # than num_colors * 3 if the image has fewer unique colors.
    num_palette_colors = len(palette) // 3 if palette else 0
    color_counts: list[tuple[tuple[int, int, int], int]] = []
    for i in range(num_palette_colors):
        r, g, b = palette[i * 3 : i * 3 + 3]
        count = histogram[i] if i < len(histogram) else 0
        if count > 0:
            color_counts.append(((r, g, b), count))

    total = sum(c for _, c in color_counts) or 1
    color_counts.sort(key=lambda x: x[1], reverse=True)

    # Build ColorInfo list.
    colors: list[ColorInfo] = []
    for rgb, count in color_counts:
        r, g, b = (c / 255 for c in rgb)
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        colors.append(
            ColorInfo(
                hex=_rgb_to_hex(rgb),
                rgb=rgb,
                fraction=count / total,
                hsv=(round(h, 3), round(s, 3), round(v, 3)),
            )
        )

    dominant = [c.hex for c in colors[:dominant_count]]

    # Accent: most saturated color that isn't near-white/near-black and isn't
    # the #1 dominant.
    accent: str | None = None
    best_sat = 0.0
    for c in colors[1:]:
        if _is_near_white(c.rgb) or _is_near_black(c.rgb):
            continue
        sat = _saturation(c.rgb)
        if sat > best_sat:
            best_sat = sat
            accent = c.hex

    # Dark theme heuristic: is the most common color dark?
    is_dark = False
    if colors:
        top_rgb = colors[0].rgb
        is_dark = sum(top_rgb) / 3 < 80

    return {
        "dominant": dominant,
        "accent": accent,
        "is_dark_theme": is_dark,
        "colors": [c.to_dict() for c in colors],
    }
