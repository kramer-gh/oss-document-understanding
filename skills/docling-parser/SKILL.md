---
name: docling-parser
description: Parse PDF and PPTX documents into Markdown or structured JSON, with design-grade vision analysis and design-system extraction. Use when the agent needs to read the content of a PDF or PowerPoint file (brand decks, existing slide decks, design specs, competitor materials) before generating a design artifact.
od:
  mode: import
---

# Docling Parser

Parse PDF and PPTX documents into clean, LLM-consumable Markdown or structured
JSON, with an optional design-grade vision pipeline and design-system
extraction. Backed by IBM's [Docling](https://docling-project.github.io/docling/).

## When to use

- A user drops a `.pdf` or `.pptx` and asks you to work from its contents.
- You need the text, tables, images, or speaker notes of an existing deck.
- You need to understand *what a slide looks like* (layout, colors, diagrams,
  visual hierarchy), not just what it says.
- You are extracting a brand reference, design spec, or competitor material
  into a `DESIGN.md`, design brief, or a full design system.

## Tool surface

Prefer the MCP tools when the `docling-parser` MCP server is available. Fall
back to the CLI otherwise.

| Purpose | MCP tool | CLI |
| --- | --- | --- |
| Parse a document | `parse_document(source, output_format, max_chars, vision, save)` | `docling-parser convert <source>` |
| Extract a design system | `build_design_system(source, save)` | `docling-parser design-system <source>` |
| List parsed docs | `list_parsed()` | `docling-parser list` |
| One page's analysis | `get_page(source, page_number)` | `docling-parser page <source> <n>` |
| Document summary | `get_summary(source)` | `docling-parser summary <source>` |

## Parsing

```
parse_document(source="path/to/deck.pptx", output_format="markdown", vision=false, save=false)
```

```bash
docling-parser convert path/to/deck.pptx -o deck.md
docling-parser convert path/to/spec.pdf --format json
docling-parser convert https://example.com/report.pdf --max-chars 0
```

- `source` — local file path or http(s) URL (PDF or PPTX).
- `output_format` — `markdown` (default) or `json`.
- `max_chars` — truncate Markdown output (default `100000`; `0` disables).
- `vision` — render pages and run the vision pipeline (see below).
- `save` — write split, browsable files instead of returning full content.

**Markdown** output has headings, paragraphs, tables, and image references —
ideal for direct LLM consumption and RAG.

**JSON** output uses a stable schema: `title`, `source_format`, `page_count`,
`text`, `tables`, `images`, and `notes` (PPTX speaker notes).

## Vision mode (design-grade visual intelligence)

For design work where the *visual* content matters, pass `vision=true` (MCP)
or `--vision` (CLI). This:

1. Renders each page/slide to an image (pymupdf for PDF; LibreOffice→PDF→pymupdf for PPTX).
2. Extracts a **color palette** from real pixels (dominant colors, accent, dark/light theme) — not VLM guessing.
3. Analyzes each page with a BYOK vision model, returning structured JSON: `summary`, `design_intent`, `layout`, `typography`, `sections`, `graphics` (with roles), `visual_hierarchy`, `readable_text`.
4. Synthesizes a **document-level summary**: `document_summary`, `design_language`, `tone`, `estimated_audience`, `key_themes`.

Use vision mode to extract a brand's visual language into `DESIGN.md`,
reconstruct an existing deck's structure, or feed design intelligence into a
design agent.

PPTX vision mode requires LibreOffice (`brew install --cask libreoffice`).
PDF vision mode needs no extra dependencies.

## Design system extraction

To build a design system from reference material (the input for a design
agent or Claude Design replacement):

```
build_design_system(source="path/to/brand-deck.pptx", save=false)
```

```bash
docling-parser design-system path/to/brand-deck.pptx -o design-system.json
```

This runs the full vision pipeline, then synthesizes a production-ready design
system: semantic color tokens (primary/secondary/accent/background/text with
exact hex codes from pixel analysis), a typography scale, spacing/radius
tokens, component specs, and usage guidelines. A `_meta` block records source
colors and layout patterns for traceability.

## File persistence and browsing

When parsing with `save=true` (MCP) or `--save` (CLI), outputs are split into
browsable files under the output directory (`DOCLING_PARSER_OUTPUT_DIR`,
default `docling-output/`):

- `{stem}.index.json` — small index with page summaries (browse this first)
- `{stem}.summary.json` — document-level summary only (~1 KB)
- `{stem}.pages/page-NNN.json` — per-page vision analysis (~2-6 KB each)
- `{stem}.full.json` — complete output (load only when needed)
- `{stem}.md` — markdown output (text-only parse)
- `{stem}.pages/page-NNN.png` — the rendered page, beside its analysis
- `{stem}.design-system.json` — extracted design system

Use the browsing tools to avoid loading large outputs into context:

- `list_parsed()` — see what's been parsed (stem, pages, has_vision, has_design_system)
- `get_summary(source)` — document overview
- `get_page(source, page_number)` — single page analysis (1-based), including its `image` path

**Read the image, not only the description.** With `vision=true, save=true`
every page is written as `page-NNN.png` next to its `page-NNN.json`, and the
index's `page_index` carries both `file` and `image`. The analysis is a model's
description of the page; the PNG is the page. For judging layout, collisions,
hierarchy or chart craft, open the image.

**Recommended agent workflow:**

1. `parse_document(source, vision=true, save=true)` → returns file paths + page index (~7 KB)
2. `list_parsed()` → see what's available
3. `get_summary(source)` for the overview, `get_page(source, n)` for a specific page
4. Read `{stem}.full.json` only when you need everything

## Configuration (environment variables, all optional)

| Variable | Default |
| --- | --- |
| `VISION_API_URL` | `https://api.thoughtworks.polis.thoughtworks-labs.net/v1/inference/chat/completions` |
| `VISION_MODEL` | `agentworks/gemma-4-31b-it` |
| `VISION_API_KEY` | falls back to `AGENTWORKS_API_KEY` |
| `VISION_ROUTING` | `pin` (value of `x-agentworks-routing` header) |
| `VISION_CONCURRENCY` | `4` (parallel VLM calls; lower for large decks) |
| `VISION_TIMEOUT` | `120` (seconds per VLM call) |
| `DOCLING_PARSER_OUTPUT_DIR` | `docling-output/` |

Any OpenAI-compatible endpoint works — OpenAI, Azure, Groq, OpenRouter, vLLM,
Ollama, LM Studio, or Anthropic/Gemini through a compatible proxy.

## Notes

- Scanned PDFs are handled via Docling's built-in OCR.
- Speaker notes are extracted best-effort for local PPTX files.
- Remote URLs are SSRF-guarded (private/loopback/link-local hosts rejected).
- Source filenames are sanitized to lowercase-hyphenated stems (e.g. `My Great Deck.pptx` → `my-great-deck`).