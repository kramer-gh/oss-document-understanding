"""Vision layer: render pages and describe them with a BYOK vision model.

This is the "full" mode that gives the parser Claude-Design-like visual
intelligence: each page/slide is rasterized, its color palette is extracted
from real pixels, and the image is sent to a vision language model (Gemma 4
by default, any OpenAI-compatible endpoint) which produces a structured
design-intelligence analysis.

The output per page includes:
- ``summary`` — concise summary of what the page communicates
- ``design_intent`` — what the page is trying to achieve
- ``layout`` — spatial structure and description
- ``color_palette`` — hex codes from pixel analysis + VLM color description
- ``typography`` — font styles, weights, hierarchy
- ``sections`` — heading + content for each section
- ``graphics`` — charts, diagrams, logos, photos with descriptions and roles
- ``visual_hierarchy`` — what draws the eye and reading order
- ``readable_text`` — verbatim text content

A document-level summary (``document_summary``, ``design_language``, ``tone``,
``estimated_audience``) is produced from the per-page analyses.

Rendering:
- PDF  -> pymupdf renders each page to PNG.
- PPTX -> LibreOffice converts to PDF, then pymupdf renders each page.

Configuration (environment variables):
- VISION_API_URL   OpenAI-compatible chat/completions endpoint
- VISION_API_KEY   bearer token (defaults to AGENTWORKS_API_KEY)
- VISION_MODEL     model id (default: agentworks/gemma-4-31b-it)
- VISION_ROUTING   value for the x-agentworks-routing header (default: pin)
- VISION_CONCURRENCY  number of parallel VLM calls (default: 4)
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DEFAULT_API_URL = (
    "https://api.thoughtworks.polis.thoughtworks-labs.net/v1/inference"
    "/chat/completions"
)
DEFAULT_MODEL = "agentworks/gemma-4-31b-it"

PAGE_PROMPT = """\
You are a senior design analyst examining a single page or slide from a \
document. Your analysis will feed into a design-intelligence system that \
reconstructs visual language for a Claude Design replacement.

Analyze the page image carefully and return STRICT JSON with EXACTLY these \
fields:

- "summary": A concise 1-2 sentence summary of what this page communicates \
and its purpose.
- "design_intent": What this page is trying to achieve visually and \
communicatively (e.g. "establish authority with a bold hero", "present data \
clearly with a clean table", "create urgency with red accents").
- "layout": An object with "structure" (one of: cover, section-divider, \
hero, two-column, three-column, grid, full-bleed, title-and-body, \
sidebar, table-centric, diagram-centric, list, timeline, comparison, \
quote, contact) and "description" (detailed spatial description of how \
elements are arranged).
- "color_description": A description of the color scheme and its \
emotional/brand connotation (e.g. "corporate navy conveys trust, green \
accents suggest growth"). Do NOT guess hex codes — those are provided \
separately.
- "typography": An object with "description" (font styles, weights, sizes \
observed) and "hierarchy" (how headings vs body text are differentiated).
- "sections": An array of {"heading": string, "content": string} for each \
distinct content section.
- "graphics": An array of {"type": string (chart, diagram, logo, photo, \
icon, illustration, screenshot, table, callout, decorative), \
"description": string (what it shows, including data for charts), \
"role": string (what it does for the page — e.g. "brand reinforcement", \
"data evidence", "visual break")} for each visual element.
- "visual_hierarchy": One sentence on what draws the eye first, second, \
third and the intended reading order.
- "readable_text": All text you can read on the page, verbatim where \
possible, separated by newlines.

Return ONLY the JSON object. No markdown fences. No commentary. No \
trailing commas."""

DOC_SUMMARY_PROMPT = """\
You are a senior design analyst. Below are per-page analyses of a document. \
Synthesize them into a document-level design intelligence summary.

Return STRICT JSON with EXACTLY these fields:

- "document_summary": 2-3 sentence summary of what this document is and its \
overall purpose.
- "design_language": Description of the overall visual identity and style \
(e.g. "Corporate minimalism with navy/white palette, sans-serif typography, \
data-forward layouts").
- "tone": One word for the tone (e.g. professional, playful, corporate, \
minimalist, bold, technical, persuasive, informational).
- "estimated_audience": Who this document is for (e.g. "executive \
stakeholders evaluating a vendor proposal").
- "key_themes": Array of 3-5 short strings capturing the document's main \
themes.

Return ONLY the JSON object. No markdown fences. No commentary."""


class VisionError(RuntimeError):
    """Raised when rendering or vision analysis fails."""


@dataclass
class VisionConfig:
    api_url: str
    api_key: str
    model: str
    routing_header: str = "pin"
    concurrency: int = 4
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> VisionConfig:
        return cls(
            api_url=os.environ.get("VISION_API_URL", DEFAULT_API_URL),
            api_key=os.environ.get(
                "VISION_API_KEY", os.environ.get("AGENTWORKS_API_KEY", "")
            ),
            model=os.environ.get("VISION_MODEL", DEFAULT_MODEL),
            routing_header=os.environ.get("VISION_ROUTING", "pin"),
            concurrency=int(os.environ.get("VISION_CONCURRENCY", "4")),
            timeout=float(os.environ.get("VISION_TIMEOUT", "120")),
        )

    def validate(self) -> None:
        if not self.api_key:
            raise VisionError(
                "no vision API key: set VISION_API_KEY or AGENTWORKS_API_KEY"
            )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_pages(source: str, source_format: str) -> list[bytes]:
    """Render every page/slide to PNG bytes.

    Returns a list of PNG byte strings, one per page.
    """
    path = Path(source)
    if "://" in source:
        # Download remote URLs to a temp file before rendering.
        import tempfile
        import urllib.request

        suffix = f".{source_format}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            urllib.request.urlretrieve(source, tmp.name)
            path = Path(tmp.name)
        try:
            return _render_with_path(path, source_format)
        finally:
            path.unlink(missing_ok=True)
    return _render_with_path(path, source_format)


def _render_with_path(path: Path, source_format: str) -> list[bytes]:
    if source_format == "pdf":
        return _render_pdf(path)
    if source_format in {"pptx", "ppt"}:
        return _render_pptx(path)
    raise VisionError(f"vision mode does not support format: {source_format}")


def _render_pdf(path: Path) -> list[bytes]:
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - older pymupdf releases
        import fitz as pymupdf  # type: ignore[no-redef]

    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:  # noqa: BLE001
        raise VisionError(f"could not open PDF {path}: {exc}") from exc

    pages: list[bytes] = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            pages.append(pix.tobytes("png"))
    finally:
        doc.close()
    return pages


def _find_soffice() -> str | None:
    """Locate the LibreOffice headless binary.

    Checks PATH first, then common macOS and Linux install locations.
    """
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    # macOS app bundle (brew cask sometimes leaves a broken symlink).
    for mac_path in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/local/lib/libreoffice/program/soffice",
        "/opt/homebrew/bin/soffice",
    ):
        if Path(mac_path).exists():
            return mac_path
    return None


def _render_pptx(path: Path) -> list[bytes]:
    soffice = _find_soffice()
    if not soffice:
        raise VisionError(
            "PPTX vision mode requires LibreOffice. Install it with: "
            "brew install --cask libreoffice"
        )

    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", tmp, str(path)],
                check=True,
                capture_output=True,
                timeout=300,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise VisionError(f"LibreOffice failed to convert {path}: {exc}") from exc

        pdf = Path(tmp) / f"{path.stem}.pdf"
        if not pdf.exists():
            raise VisionError(f"LibreOffice did not produce a PDF for {path}")
        return _render_pdf(pdf)


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any]:
    """Robustly extract a JSON object from a model response.

    Vision models frequently emit slightly malformed JSON (missing/trailing
    commas, unescaped quotes in verbatim text, markdown fences). We try strict
    parsing first, then fall back to a JSON repair pass.
    """
    text = text.strip()
    # Strip markdown fences.
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise VisionError(f"no JSON object in model response: {text[:200]!r}")
    candidate = text[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    try:
        from json_repair import loads as repair_loads

        return repair_loads(candidate)
    except Exception as exc:  # noqa: BLE001
        raise VisionError(
            f"could not parse JSON from model: {candidate[:200]!r}"
        ) from exc


# ---------------------------------------------------------------------------
# Vision model calls
# ---------------------------------------------------------------------------


def _vlm_chat(
    config: VisionConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1500,
    retries: int = 3,
) -> str:
    """Send a chat completion request and return the content string.

    Retries on transient network errors with exponential backoff.
    """
    body = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "x-agentworks-routing": config.routing_header,
        "Content-Type": "application/json",
    }
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.post(
                config.api_url, headers=headers, json=body, timeout=config.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                time.sleep(wait)
        except (KeyError, IndexError) as exc:
            raise VisionError(f"unexpected vision API response: {exc}") from exc

    raise VisionError(f"vision API request failed after {retries} retries: {last_exc}")


def describe_page(png_bytes: bytes, config: VisionConfig) -> dict[str, Any]:
    """Send one rendered page to the vision model and parse its description."""
    b64 = base64.b64encode(png_bytes).decode()
    content = _vlm_chat(
        config,
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PAGE_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
    )
    return _extract_json(content)


def summarize_document(
    page_analyses: list[dict[str, Any]], config: VisionConfig
) -> dict[str, Any]:
    """Produce a document-level design summary from per-page analyses.

    Makes one text-only VLM call (no images) with condensed per-page summaries.
    """
    # Condense each page to its summary + design_intent to keep the prompt
    # small (text-only, no images).
    condensed = []
    for p in page_analyses:
        condensed.append(
            {
                "page": p.get("page"),
                "summary": p.get("summary", ""),
                "design_intent": p.get("design_intent", ""),
                "layout": p.get("layout", {}).get("structure", ""),
                "graphics": [g.get("type", "") for g in p.get("graphics", [])],
            }
        )

    user_text = (
        "Per-page analyses:\n"
        + json.dumps(condensed, indent=2, default=str)
    )
    content = _vlm_chat(
        config,
        [
            {
                "role": "user",
                "content": DOC_SUMMARY_PROMPT + "\n\n" + user_text,
            }
        ],
        max_tokens=800,
    )
    return _extract_json(content)


# ---------------------------------------------------------------------------
# Full analysis pipeline
# ---------------------------------------------------------------------------


def analyze(
    source: str,
    source_format: str,
    config: VisionConfig | None = None,
) -> dict[str, Any]:
    """Render, extract colors, and visually analyze every page/slide.

    Returns a dict with:
    - ``document_summary``: document-level design intelligence
    - ``pages``: list of per-page analyses with color palettes
    """
    from docling_parser.color import extract_palette

    config = config or VisionConfig.from_env()
    config.validate()

    pages_png = render_pages(source, source_format)

    # Phase 1: per-page color extraction + VLM analysis (parallel).
    results: list[dict[str, Any]] = [{}] * len(pages_png)

    def _work(idx: int) -> tuple[int, dict[str, Any]]:
        png = pages_png[idx]
        # Color extraction (fast, local).
        palette = extract_palette(png)
        # VLM analysis (slow, remote).
        try:
            desc = describe_page(png, config)
        except VisionError as exc:
            desc = {
                "summary": f"[vision analysis failed: {exc}]",
                "design_intent": "",
                "layout": {"structure": "unknown", "description": str(exc)},
                "typography": {},
                "sections": [],
                "graphics": [],
                "visual_hierarchy": "",
                "readable_text": "",
            }
        # Merge color palette into the result.
        desc["color_palette"] = {
            "dominant": palette["dominant"],
            "accent": palette["accent"],
            "is_dark_theme": palette["is_dark_theme"],
            "description": desc.pop("color_description", ""),
        }
        return idx, {"page": idx + 1, **desc}

    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        futures = [pool.submit(_work, i) for i in range(len(pages_png))]
        for future in as_completed(futures):
            idx, desc = future.result()
            results[idx] = desc

    # Phase 2: document-level summary from per-page analyses.
    doc_summary = summarize_document(results, config)

    return {
        "document_summary": doc_summary,
        "pages": results,
    }
