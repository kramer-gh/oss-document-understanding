"""Tests for the design system generation module (deterministic parts)."""

from __future__ import annotations

from docling_parser.design_system import (
    _aggregate_colors,
    _aggregate_layouts,
    _aggregate_typography,
)


def _page(
    dominant: list[str],
    accent: str | None = None,
    dark: bool = False,
    structure: str = "cover",
    typo_desc: str = "Sans-serif",
    typo_hierarchy: str = "bold headings",
) -> dict:
    return {
        "page": 1,
        "color_palette": {
            "dominant": dominant,
            "accent": accent,
            "is_dark_theme": dark,
        },
        "layout": {"structure": structure},
        "typography": {"description": typo_desc, "hierarchy": typo_hierarchy},
    }


class TestAggregateColors:
    def test_counts_frequencies(self):
        pages = [
            _page(["#ffffff", "#003d4f"], accent="#ff0000"),
            _page(["#ffffff", "#003d4f"]),
        ]
        colors, is_dark = _aggregate_colors(pages)
        by_hex = {c["hex"]: c["count"] for c in colors}
        assert by_hex["#ffffff"] == 2
        assert by_hex["#003d4f"] == 2
        assert by_hex["#ff0000"] == 1
        assert is_dark is False

    def test_detects_dark_theme_majority(self):
        pages = [
            _page(["#003d4f"], dark=True),
            _page(["#003d4f"], dark=True),
            _page(["#ffffff"], dark=False),
        ]
        _, is_dark = _aggregate_colors(pages)
        assert is_dark is True

    def test_sorted_by_frequency(self):
        pages = [
            _page(["#ffffff", "#003d4f"]),
            _page(["#ffffff", "#003d4f"]),
            _page(["#ffffff"]),
        ]
        colors, _ = _aggregate_colors(pages)
        assert colors[0]["hex"] == "#ffffff"
        assert colors[0]["count"] == 3


class TestAggregateTypography:
    def test_dedupes_identical_descriptions(self):
        pages = [
            _page(["#ffffff"], typo_desc="Sans-serif", typo_hierarchy="bold"),
            _page(["#ffffff"], typo_desc="Sans-serif", typo_hierarchy="bold"),
            _page(["#ffffff"], typo_desc="Serif", typo_hierarchy="italic"),
        ]
        result = _aggregate_typography(pages)
        assert len(result) == 2

    def test_skips_empty_descriptions(self):
        pages = [
            _page(["#ffffff"], typo_desc=""),
            _page(["#ffffff"], typo_desc="Sans-serif"),
        ]
        result = _aggregate_typography(pages)
        assert len(result) == 1
        assert result[0]["description"] == "Sans-serif"


class TestAggregateLayouts:
    def test_collects_distinct_structures_in_order(self):
        pages = [
            _page(["#ffffff"], structure="cover"),
            _page(["#ffffff"], structure="two-column"),
            _page(["#ffffff"], structure="cover"),
            _page(["#ffffff"], structure="grid"),
        ]
        result = _aggregate_layouts(pages)
        assert result == ["cover", "two-column", "grid"]

    def test_skips_empty_structures(self):
        pages = [
            _page(["#ffffff"], structure=""),
            _page(["#ffffff"], structure="hero"),
        ]
        result = _aggregate_layouts(pages)
        assert result == ["hero"]