"""Docling-backed PDF and PPTX document conversion.

This module is the universal core: it takes a local path or an http(s) URL,
runs it through Docling's ``DocumentConverter``, and returns a normalized
:class:`ParseResult` that is independent of any single harness or codebase.
"""

from __future__ import annotations

import html
import ipaddress
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from docling.document_converter import DocumentConverter

SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".ppt"}


class ConversionError(RuntimeError):
    """Raised when a document cannot be converted."""


class UnsupportedFormatError(ConversionError):
    """Raised when the input is not a supported PDF/PPTX document."""


@dataclass
class ParseResult:
    """Normalized output of a document parse.

    ``content`` is Markdown when ``output_format == "markdown"`` and a
    structured dict when ``output_format == "json"``.
    """

    source: str
    source_format: str
    output_format: str
    content: str | dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    notes: list[str] = field(default_factory=list)
    vision: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "source": self.source,
            "source_format": self.source_format,
            "output_format": self.output_format,
            "content": self.content,
            "metadata": self.metadata,
            "truncated": self.truncated,
            "notes": self.notes,
        }
        if self.vision is not None:
            out["vision"] = self.vision
        return out


def _detect_format(source: str) -> str:
    """Return the lowercase extension without the dot, or raise."""
    path = urlparse(source).path if "://" in source else source
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"unsupported format '{ext or '(none)'}'; "
            f"supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return ext.lstrip(".")


def _assert_public_url(url: str) -> None:
    """Reject URLs that resolve to private, loopback, or link-local hosts.

    This mirrors the SSRF posture used at the OpenDesign daemon edge: internal
    IPs, link-local, and CGNAT ranges are blocked before any fetch.
    """
    host = urlparse(url).hostname
    if not host:
        raise ConversionError(f"could not determine host from URL: {url}")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ConversionError(f"could not resolve host '{host}': {exc}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise ConversionError(
                f"refusing to fetch URL resolving to non-public address {ip}"
            )


class DocumentParser:
    """Convert PDF and PPTX documents into Markdown or structured JSON."""

    def __init__(self) -> None:
        # DocumentConverter is stateful (model loading) — construct once and
        # reuse across parses within a process (MCP server or CLI batch).
        self._converter = DocumentConverter()

    def parse(
        self,
        source: str,
        output_format: str = "markdown",
        *,
        max_chars: int | None = 100_000,
        vision: bool = False,
    ) -> ParseResult:
        """Parse a document from a local path or http(s) URL.

        Args:
            source: Local file path or http(s) URL to a PDF/PPTX document.
            output_format: ``"markdown"`` (default) or ``"json"``.
            max_chars: Truncate Markdown output to this many characters.
                ``None`` disables truncation.
            vision: When True, render each page/slide and describe its layout,
                sections, and graphics with a BYOK vision model (see
                :mod:`docling_parser.vision`). Results are attached to the
                returned result's ``vision`` field.

        Returns:
            A :class:`ParseResult` with normalized content and metadata.
        """
        if output_format not in {"markdown", "json"}:
            raise ConversionError(
                f"invalid output_format '{output_format}'; "
                "expected 'markdown' or 'json'"
            )

        source_format = _detect_format(source)

        if "://" in source:
            if not source.startswith(("http://", "https://")):
                raise ConversionError(f"unsupported URL scheme in: {source}")
            _assert_public_url(source)

        try:
            result = self._converter.convert(source)
        except Exception as exc:  # noqa: BLE001 — surface as typed error
            raise ConversionError(f"conversion failed for {source}: {exc}") from exc

        document = result.document
        metadata = {
            "title": getattr(document, "name", None),
            "page_count": len(getattr(document, "pages", {}) or {}),
        }

        notes = self._extract_notes(source, source_format)

        if output_format == "markdown":
            content: str | dict[str, Any] = html.unescape(
                document.export_to_markdown()
            )
            truncated = False
            if max_chars is not None and len(content) > max_chars:
                content = content[:max_chars]
                truncated = True
        else:
            from docling_parser.normalizer import normalize

            content = normalize(
                document,
                source_format=source_format,
                markdown=html.unescape(document.export_to_markdown()),
                notes=notes,
            )
            truncated = False

        vision_result: dict[str, Any] | None = None
        if vision:
            from docling_parser.vision import VisionError, analyze

            try:
                vision_result = analyze(source, source_format)
            except VisionError as exc:
                raise ConversionError(f"vision analysis failed: {exc}") from exc

        return ParseResult(
            source=source,
            source_format=source_format,
            output_format=output_format,
            content=content,
            metadata=metadata,
            truncated=truncated,
            notes=notes,
            vision=vision_result,
        )

    @staticmethod
    def _extract_notes(source: str, source_format: str) -> list[str]:
        """Best-effort extraction of PPTX speaker notes.

        Docling does not reliably surface speaker notes, so for local PPTX
        files we read them directly with python-pptx. Remote or non-PPTX
        sources return an empty list.
        """
        if source_format != "pptx" or "://" in source:
            return []
        try:
            from pptx import Presentation
        except ImportError:
            return []

        try:
            prs = Presentation(source)
        except Exception:  # noqa: BLE001 — notes are best-effort only
            return []

        notes: list[str] = []
        for idx, slide in enumerate(prs.slides, start=1):
            if slide.has_notes_slide:
                text = slide.notes_slide.notes_text_frame.text.strip()
                if text:
                    notes.append(f"[slide {idx}] {text}")
        return notes