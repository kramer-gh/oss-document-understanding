"""Command-line interface for the universal document parser.

Usage:
    docling-parser convert input.pdf -o out.md
    docling-parser convert deck.pptx --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from docling_parser.converter import ConversionError, DocumentParser


def _vision_to_markdown(vision: dict[str, Any]) -> str:
    """Render the vision analysis as a markdown appendix."""
    out = "\n\n<!-- VISION ANALYSIS -->\n"

    doc = vision.get("document_summary", {})
    if doc:
        out += "\n### Document Summary\n"
        out += f"**Summary:** {doc.get('document_summary', '')}\n\n"
        out += f"**Design Language:** {doc.get('design_language', '')}\n\n"
        out += f"**Tone:** {doc.get('tone', '')}\n\n"
        out += f"**Audience:** {doc.get('estimated_audience', '')}\n"
        themes = doc.get("key_themes", [])
        if themes:
            out += f"**Key Themes:** {', '.join(themes)}\n"

    for page in vision.get("pages", []):
        out += f"\n---\n\n### Page {page.get('page', '?')}\n"
        out += f"**Summary:** {page.get('summary', '')}\n\n"
        out += f"**Design Intent:** {page.get('design_intent', '')}\n\n"

        layout = page.get("layout", {})
        if isinstance(layout, dict):
            out += (
                f"**Layout:** {layout.get('structure', '')} — "
                f"{layout.get('description', '')}\n\n"
            )
        else:
            out += f"**Layout:** {layout}\n\n"

        palette = page.get("color_palette", {})
        if palette:
            dom = ", ".join(palette.get("dominant", []))
            out += f"**Colors:** {dom}"
            if palette.get("accent"):
                out += f" (accent: {palette['accent']})"
            if palette.get("description"):
                out += f"\n  {palette['description']}"
            out += "\n\n"

        typo = page.get("typography", {})
        if isinstance(typo, dict) and typo.get("description"):
            out += f"**Typography:** {typo.get('description', '')}\n"
            if typo.get("hierarchy"):
                out += f"  Hierarchy: {typo.get('hierarchy', '')}\n"
            out += "\n"

        out += f"**Visual Hierarchy:** {page.get('visual_hierarchy', '')}\n\n"

        for g in page.get("graphics", []):
            out += (
                f"- **[{g.get('type', 'graphic')}]** "
                f"{g.get('description', '')}"
            )
            if g.get("role"):
                out += f" _({g['role']})_"
            out += "\n"

    return out


def _convert(args: argparse.Namespace) -> int:
    parser = DocumentParser()
    try:
        result = parser.parse(
            args.source,
            output_format=args.format,
            max_chars=args.max_chars or None,
            vision=args.vision,
        )
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.save:
        from docling_parser import storage

        files = storage.save_parse_result(args.source, result.to_dict())
        print(json.dumps({"saved_files": files}, indent=2))
        return 0

    if args.format == "json":
        payload = json.dumps(result.to_dict(), indent=2, default=str)
    else:
        payload = result.content if isinstance(result.content, str) else ""
        if args.vision and result.vision:
            payload += _vision_to_markdown(result.vision)

    if args.output:
        Path(args.output).write_text(payload)
        print(f"wrote {args.output}")
    else:
        print(payload)
    return 0


def _design_system(args: argparse.Namespace) -> int:
    """Extract a design system from a document via vision analysis."""
    from docling_parser.converter import _detect_format
    from docling_parser.design_system import build_design_system
    from docling_parser.vision import VisionError, analyze

    try:
        source_format = _detect_format(args.source)
        vision = analyze(args.source, source_format)
        system = build_design_system(vision)
    except (ConversionError, VisionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(system, indent=2, default=str)
    if args.save:
        from docling_parser import storage

        path = storage.save_design_system(args.source, system)
        print(json.dumps({"saved_file": path, "name": system.get("name")}, indent=2))
        return 0

    if args.output:
        Path(args.output).write_text(payload)
        print(f"wrote {args.output}")
    else:
        print(payload)
    return 0


def _list(args: argparse.Namespace) -> int:
    """List all previously parsed documents."""
    from docling_parser import storage

    docs = storage.list_parsed()
    if not docs:
        print("no parsed documents found")
        return 0
    for d in docs:
        print(
            f"  {d.get('stem', '?'):40s} "
            f"{d.get('source_format', '?'):5s} "
            f"{d.get('page_count', 0):3d}pp "
            f"{'vision' if d.get('has_vision') else '      '} "
            f"{'design-sys' if d.get('has_design_system') else '          '}"
        )
    return 0


def _get_page(args: argparse.Namespace) -> int:
    """Get a single page's vision analysis."""
    from docling_parser import storage

    result = storage.get_page(args.source, args.page_number)
    if result is None:
        print(f"page {args.page_number} not found for {args.source}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def _get_summary(args: argparse.Namespace) -> int:
    """Get document-level summary."""
    from docling_parser import storage

    result = storage.get_summary(args.source)
    if result is None:
        print(f"no summary found for {args.source}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="docling-parser",
        description="Parse PDF and PPTX documents via Docling",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    conv = sub.add_parser("convert", help="convert a document")
    conv.add_argument("source", help="file path or http(s) URL")
    conv.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="output format (default: markdown)",
    )
    conv.add_argument("-o", "--output", help="write output to this file")
    conv.add_argument(
        "--max-chars",
        type=int,
        default=100_000,
        help="truncate markdown output (default: 100000; 0 disables)",
    )
    conv.add_argument(
        "--vision",
        action="store_true",
        help="render pages and describe layout/graphics with a BYOK vision model",
    )
    conv.add_argument(
        "--save",
        action="store_true",
        help="write split files to the output dir (DOCLING_PARSER_OUTPUT_DIR)",
    )
    conv.set_defaults(func=_convert)

    ds = sub.add_parser(
        "design-system",
        help="extract a design system (tokens + components) from a document",
    )
    ds.add_argument("source", help="file path or http(s) URL")
    ds.add_argument("-o", "--output", help="write output to this file")
    ds.add_argument(
        "--save",
        action="store_true",
        help="write to the output dir (DOCLING_PARSER_OUTPUT_DIR)",
    )
    ds.set_defaults(func=_design_system)

    lst = sub.add_parser("list", help="list previously parsed documents")
    lst.set_defaults(func=_list)

    pg = sub.add_parser("page", help="get a single page's vision analysis")
    pg.add_argument("source", help="original source path/URL")
    pg.add_argument("page_number", type=int, help="1-based page number")
    pg.set_defaults(func=_get_page)

    sm = sub.add_parser("summary", help="get document-level summary")
    sm.add_argument("source", help="original source path/URL")
    sm.set_defaults(func=_get_summary)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()