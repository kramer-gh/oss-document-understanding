"""Tests for the stable JSON normalizer using hand-written fakes.

No mocks and no Docling models required — the normalizer reads a small set of
attributes off the document object, so a minimal fake exercises it fully.
"""

from __future__ import annotations

from docling_parser.normalizer import normalize


class FakeCell:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeTable:
    def __init__(self, caption: str, data: list[list[FakeCell]]) -> None:
        self.caption_text = caption
        self.data = data


class FakeImage:
    def __init__(self, mimetype: str) -> None:
        self.mimetype = mimetype


class FakePicture:
    def __init__(self, caption: str, image: FakeImage) -> None:
        self.caption_text = caption
        self.image = image


class FakeDocument:
    name = "Quarterly Review"
    pages = {0: None, 1: None, 2: None}
    tables = [
        FakeTable(
            "Revenue",
            [[FakeCell("Q1"), FakeCell("120")], [FakeCell("Q2"), FakeCell("140")]],
        )
    ]
    pictures = [FakePicture("logo", FakeImage("image/png"))]


def test_normalize_shape() -> None:
    out = normalize(
        FakeDocument(),
        source_format="pptx",
        markdown="# Quarterly Review",
        notes=["[slide 1] intro"],
    )

    assert out["title"] == "Quarterly Review"
    assert out["source_format"] == "pptx"
    assert out["page_count"] == 3
    assert out["text"] == "# Quarterly Review"
    assert out["notes"] == ["[slide 1] intro"]


def test_normalize_tables() -> None:
    out = normalize(FakeDocument(), source_format="pptx", markdown="x")
    assert out["tables"][0]["caption"] == "Revenue"
    assert out["tables"][0]["rows"][0] == ["Q1", "120"]


def test_normalize_images() -> None:
    out = normalize(FakeDocument(), source_format="pptx", markdown="x")
    assert out["images"][0]["caption"] == "logo"
    assert out["images"][0]["mimetype"] == "image/png"


def test_normalize_empty_document() -> None:
    class Empty:
        name = None
        pages = {}
        tables = None
        pictures = None

    out = normalize(Empty(), source_format="pdf", markdown="")
    assert out["page_count"] == 0
    assert out["tables"] == []
    assert out["images"] == []
    assert out["notes"] == []