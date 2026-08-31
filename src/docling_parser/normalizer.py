"""Normalize a Docling document into a stable, harness-agnostic schema.

Docling's own ``export_to_dict()`` is lossless but verbose and tied to its
internal object model. This module produces a compact, stable JSON shape that
downstream agents and tools can rely on across Docling upgrades.
"""

from __future__ import annotations

from typing import Any


def normalize(
    document: Any,
    *,
    source_format: str,
    markdown: str,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Build a stable JSON representation of a parsed document.

    Args:
        document: The Docling ``DoclingDocument`` produced by the converter.
        source_format: ``"pdf"`` or ``"pptx"``.
        markdown: The Markdown export of the same document.
        notes: Optional speaker notes (PPTX only).

    Returns:
        A dict with ``title``, ``source_format``, ``page_count``, ``text``,
        ``tables``, ``images``, and ``notes`` keys.
    """
    tables = _extract_tables(document)
    images = _extract_images(document)

    return {
        "title": getattr(document, "name", None),
        "source_format": source_format,
        "page_count": len(getattr(document, "pages", {}) or {}),
        "text": markdown,
        "tables": tables,
        "images": images,
        "notes": notes or [],
    }


def _extract_tables(document: Any) -> list[dict[str, Any]]:
    tables = getattr(document, "tables", None)
    if not tables:
        return []

    out: list[dict[str, Any]] = []
    for table in tables:
        try:
            rows = [
                [cell.text if hasattr(cell, "text") else str(cell) for cell in row]
                for row in table.data
            ]
        except Exception:  # noqa: BLE001 — degrade gracefully on schema drift
            continue
        out.append(
            {
                "caption": getattr(table, "caption_text", None),
                "rows": rows,
            }
        )
    return out


def _extract_images(document: Any) -> list[dict[str, Any]]:
    pictures = getattr(document, "pictures", None)
    if not pictures:
        return []

    out: list[dict[str, Any]] = []
    for pic in pictures:
        caption = getattr(pic, "caption_text", None)
        # caption_text may be a string, a method, or None depending on
        # the Docling version. Normalise to a string.
        if callable(caption):
            try:
                caption = caption()
            except Exception:  # noqa: BLE001
                caption = None
        if caption and isinstance(caption, str) and len(caption) > 500:
            # Docling sometimes stuffs base64 image data into caption_text.
            caption = caption[:500] + "…[truncated]"
        out.append(
            {
                "caption": caption,
                "mimetype": getattr(pic, "image", None).mimetype
                if getattr(pic, "image", None)
                else None,
            }
        )
    return out