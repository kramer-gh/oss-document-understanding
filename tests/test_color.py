"""Tests for the color palette extraction module."""

from __future__ import annotations

import io

from PIL import Image

from docling_parser.color import extract_palette


def _solid_color_png(
    rgb: tuple[int, int, int], size: tuple[int, int] = (200, 200)
) -> bytes:
    """Create a PNG filled with a single color."""
    img = Image.new("RGB", size, rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _two_color_png(
    top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> bytes:
    """Create a PNG with top half one color, bottom half another."""
    img = Image.new("RGB", (200, 200), top)
    for y in range(100, 200):
        for x in range(200):
            img.putpixel((x, y), bottom)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestExtractPalette:
    def test_returns_dominant_as_hex_strings(self):
        png = _solid_color_png((255, 0, 0))
        palette = extract_palette(png)
        assert isinstance(palette["dominant"], list)
        assert all(c.startswith("#") for c in palette["dominant"])
        assert len(palette["dominant"]) <= 5

    def test_solid_red_dominant_is_red(self):
        png = _solid_color_png((255, 0, 0))
        palette = extract_palette(png)
        # The dominant color should be red-ish.
        assert palette["dominant"][0] == "#ff0000"

    def test_detects_dark_theme(self):
        png = _solid_color_png((10, 10, 30))
        palette = extract_palette(png)
        assert palette["is_dark_theme"] is True

    def test_detects_light_theme(self):
        png = _solid_color_png((250, 250, 250))
        palette = extract_palette(png)
        assert palette["is_dark_theme"] is False

    def test_accent_is_none_for_monochrome(self):
        png = _solid_color_png((128, 128, 128))
        palette = extract_palette(png)
        # Gray has zero saturation, so accent should be None.
        assert palette["accent"] is None

    def test_accent_is_saturated_color(self):
        # White background with a red block — red should be the accent.
        png = _two_color_png((255, 255, 255), (255, 0, 0))
        palette = extract_palette(png)
        assert palette["accent"] is not None
        assert palette["accent"] == "#ff0000"

    def test_colors_list_has_fractions(self):
        png = _two_color_png((0, 0, 255), (255, 255, 0))
        palette = extract_palette(png)
        for c in palette["colors"]:
            assert "hex" in c
            assert "fraction" in c
            assert 0 <= c["fraction"] <= 1

    def test_handles_small_image(self):
        img = Image.new("RGB", (2, 2), (100, 200, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        palette = extract_palette(buf.getvalue())
        assert len(palette["dominant"]) >= 1
