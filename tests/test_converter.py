"""Tests for format detection, SSRF guarding, and parse error paths.

These exercise pure logic and pre-conversion error paths only, so they do not
require Docling's models to be downloaded.
"""

from __future__ import annotations

import pytest

from docling_parser.converter import (
    ConversionError,
    DocumentParser,
    UnsupportedFormatError,
    _assert_public_url,
    _detect_format,
)


def test_detect_format_pdf() -> None:
    assert _detect_format("report.pdf") == "pdf"
    assert _detect_format("https://example.com/report.PDF") == "pdf"


def test_detect_format_pptx() -> None:
    assert _detect_format("deck.pptx") == "pptx"
    assert _detect_format("legacy.ppt") == "ppt"


def test_detect_format_unsupported() -> None:
    with pytest.raises(UnsupportedFormatError):
        _detect_format("notes.docx")
    with pytest.raises(UnsupportedFormatError):
        _detect_format("no-extension")


def test_assert_public_url_rejects_private() -> None:
    for url in [
        "http://127.0.0.1/report.pdf",
        "http://10.0.0.5/report.pdf",
        "http://169.254.1.1/report.pdf",
        "http://localhost/report.pdf",
    ]:
        with pytest.raises(ConversionError):
            _assert_public_url(url)


def test_assert_public_url_allows_public() -> None:
    # example.com resolves to a public address.
    _assert_public_url("https://example.com/report.pdf")


def test_parse_rejects_invalid_output_format() -> None:
    parser = DocumentParser()
    with pytest.raises(ConversionError):
        parser.parse("report.pdf", output_format="yaml")


def test_parse_rejects_unsupported_scheme() -> None:
    parser = DocumentParser()
    with pytest.raises(ConversionError):
        parser.parse("ftp://example.com/report.pdf")