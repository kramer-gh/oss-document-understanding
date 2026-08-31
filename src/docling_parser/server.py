"""FastMCP server exposing the universal document parser.

Runs over stdio by default (the universal, harness-agnostic transport), and can
optionally serve over HTTP for shared deployments.

Usage:
    python -m docling_parser.server            # stdio
    python -m docling_parser.server --http     # HTTP on 127.0.0.1:8000

When ``save=True`` is passed to ``parse_document`` or ``build_design_system``,
outputs are written to the output directory (``DOCLING_PARSER_OUTPUT_DIR``,
default ``docling-output/``) as split, browsable files.  The response contains
file paths and a lightweight summary instead of the full content, so agents
can browse without loading everything into context.
"""

from __future__ import annotations

import argparse
from typing import Any

from fastmcp import FastMCP

from docling_parser.converter import ConversionError, DocumentParser

mcp = FastMCP("docling-parser")

# Construct once so Docling's models load a single time per process.
_parser = DocumentParser()


@mcp.tool
def parse_document(
    source: str,
    output_format: str = "markdown",
    max_chars: int | None = 100_000,
    vision: bool = False,
    save: bool = False,
) -> dict[str, Any]:
    """Parse a PDF or PPTX document into Markdown or structured JSON.

    Args:
        source: Local file path or http(s) URL to a PDF or PPTX document.
        output_format: "markdown" (default) or "json".
        max_chars: Truncate Markdown output to this many characters
            (default 100000; pass 0 to disable).
        vision: When True, render each page/slide and describe its layout,
            sections, and graphics with a BYOK vision model.
        save: When True, write split files to the output directory
            (DOCLING_PARSER_OUTPUT_DIR, default "docling-output/") and
            return a lightweight response with file paths + summary instead
            of the full content.  Use list_parsed() to browse, get_page()
            to load a single page, get_summary() for the document summary.

    Returns:
        When save=False: the full parsed content, metadata, notes, and
        (when vision=True) per-page visual analysis.
        When save=True: a lightweight response with "saved_files" paths,
        "summary", and "page_index".
        On failure: a dict with an "error" key.
    """
    try:
        result = _parser.parse(
            source,
            output_format=output_format,
            max_chars=max_chars or None,
            vision=vision,
        )
    except ConversionError as exc:
        return {"error": str(exc), "source": source}

    if save:
        from docling_parser import storage

        try:
            result_dict = result.to_dict()
            files = storage.save_parse_result(source, result_dict)
            index = storage.get_index(source)
        except OSError as exc:
            return {"error": f"failed to save output: {exc}", "source": source}
        return {
            "source": source,
            "saved": True,
            "saved_files": files,
            "summary": index.get("document_summary", {}) if index else {},
            "page_index": index.get("page_index", []) if index else {},
            "page_count": result_dict.get("metadata", {}).get("page_count"),
            "has_vision": vision,
        }

    return result.to_dict()


@mcp.tool
def build_design_system(
    source: str,
    save: bool = False,
) -> dict[str, Any]:
    """Extract a design system (tokens + components + guidelines) from a document.

    Renders every page/slide, extracts color palettes from real pixels, runs
    vision analysis with a BYOK model, and synthesizes a production-ready
    design system.

    Args:
        source: Local file path or http(s) URL to a PDF or PPTX document.
        save: When True, write the design system to the output directory
            and return a lightweight response with the file path.

    Returns:
        A design system dict with "name", "tokens", "components", and
        "guidelines".  When save=True, also includes "saved_file" path.
        On failure: a dict with an "error" key.
    """
    from docling_parser.converter import _detect_format
    from docling_parser.design_system import build_design_system as _build
    from docling_parser.vision import VisionError, analyze

    try:
        source_format = _detect_format(source)
        vision = analyze(source, source_format)
        system = _build(vision)
    except (ConversionError, VisionError) as exc:
        return {"error": str(exc), "source": source}

    if save:
        from docling_parser import storage

        try:
            path = storage.save_design_system(source, system)
        except OSError as exc:
            return {"error": f"failed to save design system: {exc}", "source": source}
        return {
            "source": source,
            "saved": True,
            "saved_file": path,
            "name": system.get("name"),
            "tone": system.get("guidelines", {}).get("tone"),
        }

    return system


@mcp.tool
def list_parsed() -> list[dict[str, Any]]:
    """List all previously parsed documents in the output directory.

    Returns a list of document metadata (stem, source, page_count, has_vision,
    has_design_system, document_summary).  Does NOT load full content —
    use get_page() or get_summary() to load specific parts.
    """
    from docling_parser import storage

    return storage.list_parsed()


@mcp.tool
def get_page(source: str, page_number: int) -> dict[str, Any]:
    """Get a single page's vision analysis from a previously parsed document.

    Args:
        source: The original source path/URL used when parsing.
        page_number: 1-based page number.

    Returns:
        The page's vision analysis (summary, design_intent, layout,
        color_palette, typography, sections, graphics, visual_hierarchy,
        readable_text).  Returns {"error": "not found"} if missing.
    """
    from docling_parser import storage

    result = storage.get_page(source, page_number)
    if result is None:
        return {"error": f"page {page_number} not found for {source}"}
    return result


@mcp.tool
def get_summary(source: str) -> dict[str, Any]:
    """Get the document-level summary for a previously parsed document.

    Returns the document summary (document_summary, design_language, tone,
    audience, key_themes) without loading per-page analysis.
    Returns {"error": "not found"} if the document has not been parsed.
    """
    from docling_parser import storage

    result = storage.get_summary(source)
    if result is None:
        return {"error": f"no summary found for {source}; parse with save=True first"}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="docling-parser MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve over HTTP instead of stdio",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP bind port (default: 8000)",
    )
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()  # stdio


if __name__ == "__main__":
    main()