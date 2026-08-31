"""Real-dependency round-trip test: convert a generated PPTX with Docling.

This is the one test that exercises the real Docling pipeline. It is marked
``slow`` because the first run downloads Docling's models. Run it explicitly:

    uv run pytest -m slow
"""

from __future__ import annotations

import pytest

from docling_parser.converter import DocumentParser

pytestmark = pytest.mark.slow


def test_parse_pptx_round_trip(tmp_path) -> None:
    from pptx import Presentation

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Hello Docling"
    path = tmp_path / "deck.pptx"
    prs.save(path)

    parser = DocumentParser()
    result = parser.parse(str(path), output_format="markdown")

    assert result.source_format == "pptx"
    assert "Hello Docling" in result.content
    assert result.truncated is False


def test_parse_pptx_json_round_trip(tmp_path) -> None:
    from pptx import Presentation

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "JSON Deck"
    path = tmp_path / "deck.pptx"
    prs.save(path)

    parser = DocumentParser()
    result = parser.parse(str(path), output_format="json")

    assert result.source_format == "pptx"
    assert isinstance(result.content, dict)
    assert result.content["source_format"] == "pptx"
    assert "JSON Deck" in result.content["text"]