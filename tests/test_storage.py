"""Tests for the storage module (file persistence and browsing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docling_parser import storage


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Point storage at a temp directory."""
    monkeypatch.setenv("DOCLING_PARSER_OUTPUT_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def sample_result():
    """A minimal parse result dict with vision analysis."""
    return {
        "source": "test-deck.pptx",
        "source_format": "pptx",
        "output_format": "json",
        "content": {"title": "Test", "text": "# Test\n"},
        "metadata": {"title": "Test", "page_count": 3},
        "truncated": False,
        "notes": [],
        "vision": {
            "document_summary": {
                "document_summary": "A test deck.",
                "design_language": "Minimal",
                "tone": "professional",
            },
            "pages": [
                {
                    "page": 1,
                    "summary": "Cover slide",
                    "layout": {"structure": "cover", "description": "..."},
                    "color_palette": {"dominant": ["#ffffff", "#003d4f"]},
                },
                {
                    "page": 2,
                    "summary": "Content slide",
                    "layout": {"structure": "two-column", "description": "..."},
                    "color_palette": {"dominant": ["#ffffff"]},
                },
                {
                    "page": 3,
                    "summary": "Closing slide",
                    "layout": {"structure": "section-divider", "description": "..."},
                    "color_palette": {"dominant": ["#003d4f"]},
                },
            ],
        },
    }


class TestSaveParseResult:
    def test_creates_index_file(self, tmp_output, sample_result):
        files = storage.save_parse_result("test-deck.pptx", sample_result)
        assert "index" in files
        index = json.loads(Path(files["index"]).read_text())
        assert index["stem"] == "test-deck"
        assert index["page_count"] == 3
        assert index["has_vision"] is True
        assert len(index["page_index"]) == 3

    def test_creates_summary_file(self, tmp_output, sample_result):
        files = storage.save_parse_result("test-deck.pptx", sample_result)
        summary = json.loads(Path(files["summary"]).read_text())
        assert summary["document_summary"]["document_summary"] == "A test deck."
        assert summary["page_count"] == 3

    def test_creates_full_file(self, tmp_output, sample_result):
        files = storage.save_parse_result("test-deck.pptx", sample_result)
        full = json.loads(Path(files["full"]).read_text())
        assert full["source"] == "test-deck.pptx"
        assert "vision" in full

    def test_splits_pages(self, tmp_output, sample_result):
        files = storage.save_parse_result("test-deck.pptx", sample_result)
        pages_dir = Path(files["pages_dir"])
        page_files = sorted(pages_dir.glob("page-*.json"))
        assert len(page_files) == 3
        page1 = json.loads(page_files[0].read_text())
        assert page1["page"] == 1
        assert page1["summary"] == "Cover slide"

    def test_page_index_has_summaries(self, tmp_output, sample_result):
        files = storage.save_parse_result("test-deck.pptx", sample_result)
        index = json.loads(Path(files["index"]).read_text())
        summaries = [p["summary"] for p in index["page_index"]]
        assert summaries == ["Cover slide", "Content slide", "Closing slide"]

    def test_no_vision_still_works(self, tmp_output):
        result = {
            "source": "doc.pdf",
            "source_format": "pdf",
            "output_format": "markdown",
            "content": "# Doc\n",
            "metadata": {"page_count": 1},
            "truncated": False,
            "notes": [],
        }
        files = storage.save_parse_result("doc.pdf", result)
        index = json.loads(Path(files["index"]).read_text())
        assert index["has_vision"] is False
        assert index["page_index"] == []


class TestListParsed:
    def test_empty_dir(self, tmp_output):
        assert storage.list_parsed() == []

    def test_lists_documents(self, tmp_output, sample_result):
        storage.save_parse_result("test-deck.pptx", sample_result)
        docs = storage.list_parsed()
        assert len(docs) == 1
        assert docs[0]["stem"] == "test-deck"
        assert docs[0]["has_vision"] is True


class TestGetPage:
    def test_returns_page(self, tmp_output, sample_result):
        storage.save_parse_result("test-deck.pptx", sample_result)
        page = storage.get_page("test-deck.pptx", 2)
        assert page is not None
        assert page["page"] == 2
        assert page["summary"] == "Content slide"

    def test_missing_page_returns_none(self, tmp_output, sample_result):
        storage.save_parse_result("test-deck.pptx", sample_result)
        assert storage.get_page("test-deck.pptx", 99) is None

    def test_missing_doc_returns_none(self, tmp_output):
        assert storage.get_page("nonexistent.pptx", 1) is None


class TestGetSummary:
    def test_returns_summary(self, tmp_output, sample_result):
        storage.save_parse_result("test-deck.pptx", sample_result)
        summary = storage.get_summary("test-deck.pptx")
        assert summary is not None
        assert summary["document_summary"]["tone"] == "professional"

    def test_missing_doc_returns_none(self, tmp_output):
        assert storage.get_summary("nonexistent.pptx") is None


class TestSaveDesignSystem:
    def test_saves_and_updates_index(self, tmp_output, sample_result):
        storage.save_parse_result("test-deck.pptx", sample_result)
        path = storage.save_design_system("test-deck.pptx", {"name": "Test DS"})
        assert Path(path).exists()
        # Index should be updated.
        index = storage.get_index("test-deck.pptx")
        assert index["has_design_system"] is True


class TestStem:
    def test_simple_filename(self):
        assert storage._stem("deck.pptx") == "deck"

    def test_with_spaces(self):
        assert storage._stem("My Great Deck.pptx") == "my-great-deck"

    def test_url(self):
        assert storage._stem("https://example.com/report.pdf") == "report"

    def test_special_chars(self):
        assert storage._stem("Agent_Works™ (former Polis)_ External Deck.pptx") == \
            "agent-works-former-polis-external-deck"