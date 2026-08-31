# Agent Instructions

This project is a universal PDF/PPTX document parser with vision-based design
intelligence. It ships as a FastMCP server and CLI. Treat this file as the
primary, tool-agnostic contract for coding agents.

## Environment

- Use `uv run ...` for all Python commands.
- Use `uv sync --extra dev` to install dev dependencies (pytest, ruff).
- PPTX vision mode requires LibreOffice: `brew install --cask libreoffice`
  (macOS). The code checks PATH, then `/Applications/LibreOffice.app/...`.
- Vision mode requires `AGENTWORKS_API_KEY` (or `VISION_API_KEY`) env var.
- Output directory is configurable via `DOCLING_PARSER_OUTPUT_DIR` (default:
  `docling-output/`).

## Build And Test

- Fast confidence gate: `uv run ruff check src/ tests/ && uv run pytest -q`
- Lint only: `uv run ruff check src/ tests/`
- Tests only: `uv run pytest`
- Run MCP server (stdio): `uv run docling-parser-mcp`
- Run CLI: `uv run docling-parser convert <source> [--vision] [--save]`

## Testing Contract

- Tests use real PIL images and real Docling conversions where practical.
- The VLM API calls are not unit-tested (require external service). Test the
  deterministic parts: JSON extraction, color extraction, storage, design
  system aggregation.
- No `Mock`, `MagicMock`, or `patch` for internal behavior. If a test double
  is needed for an external boundary (VLM API, file system), add a comment:
  `# test-double-allowed: <reason>`.
- Tests should assert observable outcomes, not that a collaborator was called.

## Architecture

The pipeline has two modes:

1. **Text mode** (default): Docling converts PDF/PPTX to markdown or structured
   JSON. Fast, deterministic, no external dependencies.

2. **Vision mode** (`vision=True`): Renders each page/slide to PNG, extracts
   color palette from real pixels (PIL quantization), sends each image to a
   BYOK vision model (Gemma 4 by default) for structured design analysis, and
   synthesizes a document-level summary. Optionally builds a design system.

File persistence (`save=True`) splits output into browsable chunks:
- `{stem}.index.json` — small index with page summaries
- `{stem}.summary.json` — document-level summary
- `{stem}.pages/page-NNN.json` — per-page vision analysis
- `{stem}.full.json` — complete output
- `{stem}.design-system.json` — design system

## Code Conventions

- Python 3.11+, `from __future__ import annotations` in all modules.
- Ruff line-length 88, rules: E, F, I, N, UP, B.
- Type annotations on all public functions.
- Error types: `ConversionError` (parsing), `VisionError` (vision/rendering).
- MCP tools return `{"error": ...}` on failure, never raise.
- CLI returns exit code 1 on error, prints to stderr.

## Safety

- Never commit `AGENTWORKS_API_KEY` or other secrets.
- Vision mode sends page images to an external API — do not use for
  confidential documents unless the endpoint is self-hosted.
- Remote URLs are SSRF-guarded in the converter (private/loopback/link-local
  rejected). Vision mode downloads URLs to a temp file before rendering.
- Do not push directly to protected branches.
