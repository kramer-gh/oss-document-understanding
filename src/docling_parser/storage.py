"""File persistence and browsing for parsed documents.

Splits large outputs into browsable chunks so agents can load exactly what
they need without blowing up their context window.

File layout under the output directory::

    {stem}.index.json          metadata + page summaries (small, ~2 KB)
    {stem}.summary.json        document-level summary only (~1 KB)
    {stem}.full.json            complete output (for when you want everything)
    {stem}.md                  markdown output (text-only parse)
    {stem}.pages/
        page-001.json          per-page vision analysis (~10-15 KB)
        page-002.json
        ...
    {stem}.design-system.json  design system

The index file is the key entry point: it's small, lists every page with a
one-line summary, and points to all other files.  An agent can browse the
index, then load specific pages on demand.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = "docling-output"


def _stem(source: str) -> str:
    """Derive a safe, lowercase stem from a source path or URL."""
    # Strip path and extension.
    name = source.rsplit("/", 1)[-1]
    name = re.sub(r"\.(pdf|pptx|ppt)$", "", name, flags=re.IGNORECASE)
    # Replace spaces and special chars with hyphens, lowercase.
    name = re.sub(r"[^a-zA-Z0-9.-]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-").lower()
    return name or "document"


def _output_dir() -> Path:
    """Get the configured output directory."""
    return Path(os.environ.get("DOCLING_PARSER_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def save_parse_result(
    source: str,
    result_dict: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Save a parse result to disk, splitting into browsable chunks.

    Returns a dict mapping file roles to their paths:
    ``{"index": "...", "summary": "...", "full": "...", "pages_dir": "..."}``
    """
    out = output_dir or _output_dir()
    stem = _stem(source)
    out.mkdir(parents=True, exist_ok=True)

    vision = result_dict.get("vision")
    has_vision = vision is not None

    files: dict[str, str] = {}

    # 1. Full output (everything).
    full_path = out / f"{stem}.full.json"
    full_path.write_text(json.dumps(result_dict, indent=2, default=str))
    files["full"] = str(full_path)

    # 2. Markdown (if markdown format).
    if result_dict.get("output_format") == "markdown":
        md_path = out / f"{stem}.md"
        content = result_dict.get("content", "")
        if isinstance(content, str):
            md_path.write_text(content)
            files["markdown"] = str(md_path)

    # 3. Document-level summary (small).
    summary: dict[str, Any] = {
        "source": source,
        "source_format": result_dict.get("source_format"),
        "page_count": result_dict.get("metadata", {}).get("page_count"),
    }
    if has_vision:
        doc_summary = vision.get("document_summary", {})
        summary["document_summary"] = doc_summary
    summary_path = out / f"{stem}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    files["summary"] = str(summary_path)

    # 4. Per-page vision analysis (split into small chunks).
    page_index: list[dict[str, Any]] = []
    if has_vision:
        pages = vision.get("pages", [])
        pages_dir = out / f"{stem}.pages"
        pages_dir.mkdir(exist_ok=True)
        for page in pages:
            page_num = page.get("page", 0)
            page_file = pages_dir / f"page-{page_num:03d}.json"
            page_file.write_text(json.dumps(page, indent=2, default=str))
            # Add to index: one-line summary + structure.
            layout = page.get("layout", {})
            structure = layout.get("structure", "") if isinstance(layout, dict) else ""
            page_index.append({
                "page": page_num,
                "summary": page.get("summary", ""),
                "structure": structure,
                "file": str(page_file),
            })
        files["pages_dir"] = str(pages_dir)

    # 5. Index file (the browsing entry point).
    index = {
        "source": source,
        "stem": stem,
        "source_format": result_dict.get("source_format"),
        "output_format": result_dict.get("output_format"),
        "page_count": result_dict.get("metadata", {}).get("page_count"),
        "has_vision": has_vision,
        "has_design_system": False,
        "files": files,
        "document_summary": summary.get("document_summary", {}),
        "page_index": page_index,
    }
    index_path = out / f"{stem}.index.json"
    index_path.write_text(json.dumps(index, indent=2, default=str))
    files["index"] = str(index_path)

    return files


def save_design_system(
    source: str,
    system: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> str:
    """Save a design system to disk. Returns the file path."""
    out = output_dir or _output_dir()
    stem = _stem(source)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{stem}.design-system.json"
    path.write_text(json.dumps(system, indent=2, default=str))

    # Update the index file's has_design_system flag.
    index_path = out / f"{stem}.index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
            index["has_design_system"] = True
            index.setdefault("files", {})["design_system"] = str(path)
            index_path.write_text(json.dumps(index, indent=2, default=str))
        except (json.JSONDecodeError, KeyError):
            pass

    return str(path)


def list_parsed(output_dir: Path | None = None) -> list[dict[str, Any]]:
    """List all parsed documents in the output directory.

    Returns a list of index summaries (source, stem, page_count, has_vision,
    has_design_system, page_index).  Does NOT load full content.
    """
    out = output_dir or _output_dir()
    if not out.exists():
        return []

    results: list[dict[str, Any]] = []
    for index_file in sorted(out.glob("*.index.json")):
        try:
            index = json.loads(index_file.read_text())
            results.append({
                "stem": index.get("stem"),
                "source": index.get("source"),
                "source_format": index.get("source_format"),
                "page_count": index.get("page_count"),
                "has_vision": index.get("has_vision"),
                "has_design_system": index.get("has_design_system"),
                "document_summary": index.get("document_summary", {}),
                "page_count_in_vision": len(index.get("page_index", [])),
                "index_file": str(index_file),
            })
        except json.JSONDecodeError:
            continue

    return results


def get_page(
    source: str,
    page_number: int,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Get a single page's vision analysis from disk.

    Returns None if the page or document is not found.
    """
    out = output_dir or _output_dir()
    stem = _stem(source)
    page_file = out / f"{stem}.pages" / f"page-{page_number:03d}.json"
    if not page_file.exists():
        return None
    return json.loads(page_file.read_text())


def get_summary(
    source: str,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Get the document-level summary from disk.

    Returns None if the document has not been parsed.
    """
    out = output_dir or _output_dir()
    stem = _stem(source)
    summary_file = out / f"{stem}.summary.json"
    if not summary_file.exists():
        return None
    return json.loads(summary_file.read_text())


def get_index(
    source: str,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Get the full index (metadata + page_index) for a document."""
    out = output_dir or _output_dir()
    stem = _stem(source)
    index_file = out / f"{stem}.index.json"
    if not index_file.exists():
        return None
    return json.loads(index_file.read_text())


__all__ = [
    "get_index",
    "get_page",
    "get_summary",
    "list_parsed",
    "save_design_system",
    "save_parse_result",
]