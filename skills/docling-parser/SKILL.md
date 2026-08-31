---
name: docling-parser
description: Parse PDF and PPTX documents into Markdown or structured JSON using Docling. Use when the agent needs to read the content of a PDF or PowerPoint file (brand decks, existing slide decks, design specs, competitor materials) before generating a design artifact.
---

# Docling Parser

Parse PDF and PPTX documents into clean, LLM-consumable Markdown or structured
JSON. Backed by IBM's [Docling](https://docling-project.github.io/docling/).

## When to use

- A user drops a `.pdf` or `.pptx` and asks you to work from its contents.
- You need the text, tables, images, or speaker notes of an existing deck.
- You are extracting a brand reference, design spec, or competitor material
  into a `DESIGN.md` or design brief.

## How to use

Prefer the MCP tool when it is available in your harness:

```
parse_document(source="path/to/deck.pptx", output_format="markdown", vision=true)
```

Otherwise, run the CLI from the shell:

```bash
docling-parser convert path/to/deck.pptx -o deck.md
docling-parser convert path/to/spec.pdf --format json
```

## Vision mode (design-grade visual intelligence)

For design work where the *visual* content matters (layout, colors, diagrams,
charts, visual hierarchy, design intent), pass `vision=true` (MCP) or
`--vision` (CLI). This:

1. Renders each page/slide to an image
2. Extracts a **color palette** (dominant colors, accent, dark/light theme)
   from real pixel data
3. Sends each image to a vision model for structured analysis: `summary`,
   `design_intent`, `layout`, `typography`, `sections`, `graphics` (with
   roles), `visual_hierarchy`, `readable_text`
4. Synthesizes a **document-level summary** with `document_summary`,
   `design_language`, `tone`, `estimated_audience`, and `key_themes`

Use vision mode when you need to understand *what a slide looks like*, not
just what it says — e.g. extracting a brand's visual language into `DESIGN.md`,
reconstructing an existing deck's structure, or feeding design intelligence
into a design agent.

PPTX vision mode requires LibreOffice installed
(`brew install --cask libreoffice`). PDF vision mode needs no extra
dependencies.

## Design system extraction

To build a design system from reference material (the input for a design
agent or Claude Design replacement), use the dedicated tool:

```
build_design_system(source="path/to/brand-deck.pptx")
```

Or the CLI:

```bash
docling-parser design-system path/to/brand-deck.pptx -o design-system.json
```

This produces semantic color tokens (primary/secondary/accent/background/text
with exact hex codes), a typography scale, spacing/radius tokens, component
specs, and usage guidelines — all synthesized from the vision analysis.

## File persistence and browsing

When parsing with `save=True` (MCP) or `--save` (CLI), outputs are split into
browsable files under `docling-output/`:

- `{stem}.index.json` — small index with page summaries (browse this first)
- `{stem}.summary.json` — document-level summary only (~1 KB)
- `{stem}.pages/page-NNN.json` — per-page vision analysis (~2-6 KB each)
- `{stem}.full.json` — complete output (load only when needed)

Use the browsing tools to avoid loading large outputs into context:
- `list_parsed()` — see what's been parsed
- `get_summary(source)` — document overview
- `get_page(source, page_number)` — single page analysis

## Output

- `markdown` (default): headings, paragraphs, tables, and image references as
  Markdown — ideal for direct LLM consumption and RAG.
- `json`: a stable schema with `title`, `source_format`, `page_count`, `text`,
  `tables`, `images`, and `notes` (PPTX speaker notes).

## Notes

- Scanned PDFs are handled via Docling's built-in OCR.
- Speaker notes are extracted best-effort for local PPTX files.
- Remote URLs are SSRF-guarded (private/loopback/link-local hosts rejected).