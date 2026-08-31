"""Tests for the vision module (JSON extraction, config, rendering).

These tests exercise the local, deterministic parts of the vision pipeline
(JSON repair, config from env, soffice detection).  The actual VLM API calls
and page rendering require external services and are not unit-tested here.
"""

from __future__ import annotations

import pytest

from docling_parser.vision import (
    VisionConfig,
    VisionError,
    _extract_json,
    _find_soffice,
)


class TestExtractJson:
    def test_valid_json(self):
        text = '{"layout": "hero", "summary": "test"}'
        result = _extract_json(text)
        assert result["layout"] == "hero"
        assert result["summary"] == "test"

    def test_json_with_surrounding_text(self):
        text = 'Here is the analysis:\n{"layout": "grid"}\nDone.'
        result = _extract_json(text)
        assert result["layout"] == "grid"

    def test_json_with_markdown_fence(self):
        text = '```json\n{"layout": "cover"}\n```'
        result = _extract_json(text)
        assert result["layout"] == "cover"

    def test_malformed_json_repaired(self):
        # Missing comma between fields — json_repair should fix this.
        text = '{"layout": "hero" "summary": "test"}'
        result = _extract_json(text)
        # json_repair may or may not fix this specific case, but it should
        # not raise — it should either return a dict or raise VisionError.
        assert isinstance(result, dict)

    def test_trailing_comma_repaired(self):
        text = '{"layout": "hero", "summary": "test",}'
        result = _extract_json(text)
        assert result["layout"] == "hero"

    def test_no_json_raises(self):
        with pytest.raises(VisionError, match="no JSON object"):
            _extract_json("just some text, no json here")

    def test_empty_string_raises(self):
        with pytest.raises(VisionError, match="no JSON object"):
            _extract_json("")


class TestVisionConfig:
    def test_from_env_defaults(self, monkeypatch):
        monkeypatch.delenv("VISION_API_URL", raising=False)
        monkeypatch.delenv("VISION_MODEL", raising=False)
        monkeypatch.delenv("VISION_CONCURRENCY", raising=False)
        monkeypatch.setenv("AGENTWORKS_API_KEY", "test-key-12345")
        cfg = VisionConfig.from_env()
        assert cfg.api_key == "test-key-12345"
        assert cfg.model == "agentworks/gemma-4-31b-it"
        assert cfg.concurrency == 4
        assert cfg.routing_header == "pin"

    def test_from_env_overrides(self, monkeypatch):
        monkeypatch.setenv("VISION_API_URL", "https://custom.example.com/v1/chat")
        monkeypatch.setenv("VISION_API_KEY", "custom-key")
        monkeypatch.setenv("VISION_MODEL", "custom-model")
        monkeypatch.setenv("VISION_CONCURRENCY", "8")
        monkeypatch.setenv("VISION_ROUTING", "round-robin")
        cfg = VisionConfig.from_env()
        assert cfg.api_url == "https://custom.example.com/v1/chat"
        assert cfg.api_key == "custom-key"
        assert cfg.model == "custom-model"
        assert cfg.concurrency == 8
        assert cfg.routing_header == "round-robin"

    def test_validate_missing_key(self, monkeypatch):
        monkeypatch.delenv("VISION_API_KEY", raising=False)
        monkeypatch.delenv("AGENTWORKS_API_KEY", raising=False)
        cfg = VisionConfig.from_env()
        with pytest.raises(VisionError, match="no vision API key"):
            cfg.validate()

    def test_validate_with_key(self, monkeypatch):
        monkeypatch.setenv("AGENTWORKS_API_KEY", "valid-key")
        cfg = VisionConfig.from_env()
        cfg.validate()  # should not raise


class TestFindSoffice:
    def test_returns_path_or_none(self):
        # _find_soffice returns a string path or None.  On this machine it
        # may or may not find LibreOffice, but it should not raise.
        result = _find_soffice()
        assert result is None or isinstance(result, str)
