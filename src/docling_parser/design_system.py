"""Design system generation from vision analysis.

Takes the output of :func:`docling_parser.vision.analyze` (document-level
design intelligence + per-page color/typography/layout analysis) and
synthesizes a structured design system: semantic color tokens, a type scale,
spacing/radius tokens, component specs, and usage guidelines.

The color *values* come from real pixel analysis (exact hex codes); a single
VLM call assigns semantic roles (primary/secondary/accent/background/text) and
generates the type scale, components, and guidelines from the descriptions.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from docling_parser.vision import VisionConfig, _extract_json, _vlm_chat

DESIGN_SYSTEM_PROMPT = """\
You are a senior design systems architect. Below is a design-intelligence \
analysis of a document (color palette with exact hex codes, typography \
descriptions, layout patterns, and design language). Synthesize it into a \
complete, production-ready design system.

Return STRICT JSON with EXACTLY these fields:

- "name": A short, evocative name for this design system (e.g. "Thoughtworks \
Corporate", "Deep Teal Enterprise").
- "tokens": An object with:
  - "color": semantic color roles. Each role is {"value": "#hex", "role": \
"short description"}. Roles MUST include: primary, secondary, accent, \
background, surface, text, text_inverse. Add semantic roles (success, \
warning, error, info) if the palette supports them. Use the EXACT hex codes \
provided — do not invent new ones. Choose the most representative hex for \
each role from the provided palette.
  - "typography": {"font_family": string, "scale": object mapping \
display/h1/h2/h3/body/caption to {"size": "NNpx", "weight": N, \
"line_height": "N.N"}}. Infer the scale from the described hierarchy.
  - "spacing": {"xs": "4px", "sm": "8px", "md": "16px", "lg": "24px", \
"xl": "32px", "xxl": "48px"} (a standard 4px-based scale).
  - "radius": {"sm": "4px", "md": "8px", "lg": "16px"}.
- "components": An object mapping 3-5 core component names (button, card, \
navigation, hero, data-table, etc.) to {"description": string, "key_props": \
[string]} describing how each should look given the design language.
- "guidelines": {"tone": string, "audience": string, "design_language": \
string, "key_themes": [string], "usage_notes": [string]}.

Return ONLY the JSON object. No markdown fences. No commentary. No trailing \
commas."""


def _aggregate_colors(
    pages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Aggregate color palettes across pages into a frequency-ranked list.

    Returns a tuple of (colors, is_dark_theme) where colors is a list of
    {"hex": str, "count": int} sorted by frequency.
    """
    counter: Counter[str] = Counter()
    dark_count = 0
    for page in pages:
        palette = page.get("color_palette", {})
        for hex_code in palette.get("dominant", []):
            counter[hex_code] += 1
        if palette.get("accent"):
            counter[palette["accent"]] += 1
        if palette.get("is_dark_theme"):
            dark_count += 1

    total_pages = len(pages) or 1
    return [
        {"hex": hex_code, "count": count}
        for hex_code, count in counter.most_common(20)
    ], dark_count / total_pages > 0.5


def build_design_system(
    vision_analysis: dict[str, Any],
    config: VisionConfig | None = None,
) -> dict[str, Any]:
    """Synthesize a design system from a vision analysis.

    Args:
        vision_analysis: The dict returned by
            :func:`docling_parser.vision.analyze` (with ``document_summary``
            and ``pages``).
        config: Optional :class:`VisionConfig`. Defaults to env config.

    Returns:
        A design system dict with ``name``, ``tokens``, ``components``, and
        ``guidelines``.
    """
    config = config or VisionConfig.from_env()
    config.validate()

    pages = vision_analysis.get("pages", [])
    doc = vision_analysis.get("document_summary", {})

    colors, is_dark = _aggregate_colors(pages)

    # Condense the analysis into a compact prompt payload.
    payload = {
        "design_language": doc.get("design_language", ""),
        "tone": doc.get("tone", ""),
        "audience": doc.get("estimated_audience", ""),
        "key_themes": doc.get("key_themes", []),
        "is_dark_theme": is_dark,
        "color_palette": colors,
        "typography": _aggregate_typography(pages),
        "layout_patterns": _aggregate_layouts(pages),
    }

    user_text = (
        "Design intelligence analysis:\n"
        + json.dumps(payload, indent=2, default=str)
    )
    content = _vlm_chat(
        config,
        [{"role": "user", "content": DESIGN_SYSTEM_PROMPT + "\n\n" + user_text}],
        max_tokens=2000,
    )
    system = _extract_json(content)

    # Attach provenance so the design system is traceable to its source.
    system["_meta"] = {
        "is_dark_theme": is_dark,
        "source_colors": colors,
        "layout_patterns": payload["layout_patterns"],
    }
    return system


def _aggregate_typography(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect unique typography descriptions across pages."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for page in pages:
        typo = page.get("typography", {})
        if isinstance(typo, dict):
            desc = typo.get("description", "")
            hierarchy = typo.get("hierarchy", "")
            key = (desc, hierarchy)
            if desc and key not in seen:
                seen.add(key)
                out.append({"description": desc, "hierarchy": hierarchy})
    return out[:5]


def _aggregate_layouts(pages: list[dict[str, Any]]) -> list[str]:
    """Collect the distinct layout structure types used across pages."""
    structures: list[str] = []
    seen: set[str] = set()
    for page in pages:
        layout = page.get("layout", {})
        if isinstance(layout, dict):
            structure = layout.get("structure", "")
            if structure and structure not in seen:
                seen.add(structure)
                structures.append(structure)
    return structures


__all__ = ["build_design_system"]