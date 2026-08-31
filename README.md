# docling-parser

Universal **PDF and PPTX document parser** built on IBM's
[Docling](https://docling-project.github.io/docling/). Ships as a **FastMCP
server** (the universal, harness-agnostic artifact), a **CLI**, and an
**OpenDesign skill** for first-class discoverability.

Works in any project, any harness — OpenCode, Claude Code, Codex, Cursor,
DeepSeek Harness, and OpenDesign (which delegates its agent loop to those same
CLIs).

## Why MCP (not a codebase-specific script)

MCP is the cross-harness standard. A script or skill written for one harness
dies in another; an MCP server runs identically everywhere. Docling already
ships an official `docling-mcp`, so this project is a **thin, stable wrapper**
that adds:

- a minimal, stable tool surface (`parse_document`) that won't churn upstream,
- **PPTX speaker-note extraction** (Docling doesn't reliably surface notes),
- a **normalized JSON schema** independent of Docling's internal object model,
- **SSRF guarding** on remote URLs (private/loopback/link-local rejected).

## Install

```bash
uv tool install --from git+https://github.com/your-org/docling-parser docling-parser
# or, for local development:
uv sync
```

Docling pulls in its ML stack (torch, onnxruntime, transformers). The first
conversion downloads models; subsequent runs are cached.

## CLI

```bash
docling-parser convert deck.pptx -o deck.md
docling-parser convert spec.pdf --format json
docling-parser convert https://example.com/report.pdf --max-chars 0
```

## MCP server

Run over stdio (default) or HTTP:

```bash
python -m docling_parser.server            # stdio
python -m docling_parser.server --http     # HTTP on 127.0.0.1:8000
```

Register it in **OpenCode** (`opencode.json`):

```json
{
  "mcp": {
    "docling-parser": {
      "type": "local",
      "command": ["uv", "run", "--directory", "/path/to/docling-parser", "python", "-m", "docling_parser.server"]
    }
  }
}
```

Or in any MCP client (`.mcp.json`, `claude_desktop_config.json`, etc.):

```json
{
  "mcpServers": {
    "docling-parser": {
      "command": "uvx",
      "args": ["--from", "docling-parser", "docling-parser-mcp"]
    }
  }
}
```

### OpenDesign integration

OpenDesign launches your coding-agent CLI (OpenCode, Claude Code, Codex, …) and
injects external MCP servers per harness (for OpenCode, via
`OPENCODE_CONFIG_CONTENT`). Two ways to wire it in:

1. **Register the MCP server in the harness config** OpenDesign launches (the
   `opencode.json` above), or
2. **Install the skill** by dropping `skills/docling-parser/` into OpenDesign's
   `skills/` directory, so the agent knows *when* to parse a document and how
   to consume the output.

## Output

`parse_document(source, output_format="markdown")` returns:

- **markdown** (default) — headings, paragraphs, tables, image references.
  Ideal for LLM consumption and RAG.
- **json** — stable schema:

```json
{
  "title": "Quarterly Review",
  "source_format": "pptx",
  "page_count": 12,
  "text": "# Quarterly Review\n…",
  "tables": [{"caption": "Revenue", "rows": [["Q1", "120"], ["Q2", "140"]]}],
  "images": [{"caption": "logo", "mimetype": "image/png"}],
  "notes": ["[slide 1] intro"]
}
```

## Vision mode (design-grade visual intelligence)

The default pipeline is text-first: it reads words and tables but cannot "see"
a diagram, understand a hero section vs. a sidebar, or describe an embedded
graphic. **Vision mode** closes that gap by rendering every page/slide,
extracting a color palette from real pixels, and describing each page with a
vision language model (BYOK). A document-level summary synthesizes the
per-page analyses into an overall design intelligence brief.

```bash
docling-parser convert deck.pptx --vision
docling-parser convert spec.pdf --vision --format json
```

### Output schema

Vision mode adds a `vision` key to the output with two levels:

**Document level:**

```json
{
  "document_summary": "A strategic sales deck focused on…",
  "design_language": "High-tech corporate minimalism with a deep dark-mode palette…",
  "tone": "authoritative",
  "estimated_audience": "Enterprise executives evaluating AI strategies",
  "key_themes": ["AI-Ready Data", "Governance", "Modular Architecture"]
}
```

**Per page:**

```json
{
  "page": 2,
  "summary": "An introductory section outlining the opportunity…",
  "design_intent": "Establish professional authority through a clean, structured layout",
  "layout": {
    "structure": "title-and-body",
    "description": "A single-column text-heavy layout with hierarchical headings…"
  },
  "color_palette": {
    "dominant": ["#003d4f", "#ffffff", "#365f6e"],
    "accent": "#b8a55f",
    "is_dark_theme": false,
    "description": "Deep navy conveys stability, white text ensures readability…"
  },
  "typography": {
    "description": "Clean sans-serif typeface, bold headings, regular body",
    "hierarchy": "All-caps bold headings vs regular-weight body text"
  },
  "sections": [{"heading": "Overview", "content": "…"}],
  "graphics": [
    {
      "type": "diagram",
      "description": "A workflow showing data flow between Slack, GitHub, and AWS",
      "role": "data evidence"
    }
  ],
  "visual_hierarchy": "The bold title dominates, then the table, then the footer",
  "readable_text": "…"
}
```

### How it works

1. **Render** each page/slide to PNG (pymupdf for PDF; LibreOffice→PDF→pymupdf
   for PPTX).
2. **Extract color palette** from the rendered image using PIL quantization —
   dominant colors, accent color, and dark/light theme detection from real
   pixel data (not VLM guessing).
3. **Analyze** each page with the vision model, which returns structured JSON
   with summary, design intent, layout, typography, sections, graphics, and
   visual hierarchy.
4. **Synthesize** a document-level summary from all per-page analyses (one
   text-only VLM call).
5. **Merge** the color palette (hex codes from pixels) with the VLM's color
   description into a unified `color_palette` field.

### Configuration (environment variables, all optional)

| Variable | Default |
|----------|---------|
| `VISION_API_URL` | `https://api.thoughtworks.polis.thoughtworks-labs.net/v1/inference/chat/completions` |
| `VISION_MODEL` | `agentworks/gemma-4-31b-it` |
| `VISION_API_KEY` | falls back to `AGENTWORKS_API_KEY` |
| `VISION_ROUTING` | `pin` (value of `x-agentworks-routing` header) |
| `VISION_CONCURRENCY` | `4` (parallel VLM calls; lower for large decks) |
| `VISION_TIMEOUT` | `120` (seconds per VLM call) |

Any OpenAI-compatible endpoint works — OpenAI, Azure, Groq, OpenRouter, vLLM,
Ollama, LM Studio, or Anthropic/Gemini through a compatible proxy.

### Rendering requirements

- **PDF** — no extra dependencies (pymupdf renders pages).
- **PPTX** — requires LibreOffice to rasterize slides:
  `brew install --cask libreoffice` (macOS) or `apt-get install libreoffice` (Linux).

## Design system extraction

Beyond parsing, the parser can **extract a design system** from a document —
the bridge between "understanding an existing design" and "generating a new
one". This is the primary input for a Claude Design replacement.

```bash
docling-parser design-system deck.pptx -o design-system.json
```

Or via MCP: `build_design_system(source="deck.pptx")`.

This runs the full vision pipeline, then synthesizes a production-ready design
system:

```json
{
  "name": "Architectural Azure Enterprise",
  "tokens": {
    "color": {
      "primary": {"value": "#003d4f", "role": "deep teal for branding"},
      "accent": {"value": "#d4bcc0", "role": "muted coral for eyebrows"},
      "background": {"value": "#ffffff", "role": "clean base"},
      "text": {"value": "#003d4f", "role": "primary text"}
    },
    "typography": {
      "font_family": "Inter, system-ui, sans-serif",
      "scale": {
        "display": {"size": "48px", "weight": 800, "line_height": "1.1"},
        "h1": {"size": "32px", "weight": 700, "line_height": "1.2"},
        "body": {"size": "16px", "weight": 400, "line_height": "1.6"}
      }
    },
    "spacing": {"xs": "4px", "sm": "8px", "md": "16px", "lg": "24px"}
  },
  "components": {
    "button": {"description": "…", "key_props": ["background: primary", "…"]},
    "card": {"description": "…", "key_props": ["…"]}
  },
  "guidelines": {
    "tone": "professional",
    "audience": "…",
    "design_language": "…",
    "usage_notes": ["…"]
  }
}
```

Color *values* are exact hex codes from pixel analysis; a single VLM call
assigns semantic roles (primary/secondary/accent/background/text), generates
the type scale, component specs, and usage guidelines from the descriptions.
A `_meta` block records the source colors and layout patterns for traceability.

## File strategy and browsing

When `save=True` (MCP) or `--save` (CLI), outputs are written to the output
directory (`DOCLING_PARSER_OUTPUT_DIR`, default `docling-output/`) as split,
browsable files — so agents can load exactly what they need without blowing up
their context window.

### File layout

```
docling-output/
  {stem}.index.json          metadata + page summaries (~6 KB, browseable)
  {stem}.summary.json        document-level summary only (~1 KB)
  {stem}.full.json           complete output (for when you want everything)
  {stem}.md                  markdown output (text-only parse)
  {stem}.pages/
    page-001.json            per-page vision analysis (~2-6 KB)
    page-002.json
    ...
  {stem}.design-system.json  design system
```

The **index** file is the entry point: it's small, lists every page with a
one-line summary and structure type, and points to all other files.

### Browsing tools (MCP + CLI)

| Tool | CLI | What it returns |
|------|-----|----------------|
| `list_parsed()` | `docling-parser list` | All parsed docs (stem, pages, has_vision) — no content |
| `get_summary(source)` | `docling-parser summary <source>` | Document-level summary (~1 KB) |
| `get_page(source, n)` | `docling-parser page <source> <n>` | Single page's vision analysis (~2-6 KB) |

### Agent workflow

1. **Parse**: `parse_document(source, vision=True, save=True)` → writes files, returns lightweight response (file paths + page index, ~7 KB)
2. **Browse**: `list_parsed()` → see what's available
3. **Drill in**: `get_summary(source)` for the overview, `get_page(source, 5)` for a specific page
4. **Full load**: read `{stem}.full.json` only when you need everything

### Naming convention

Source filenames are sanitized to lowercase-hyphenated stems:
- `My Great Deck.pptx` → `my-great-deck`
- `Agent_Works™ (former Polis)_ External Deck.pptx` → `agent-works-former-polis-external-deck`

## Development

```bash
uv sync --extra dev
uv run pytest                # fast unit tests (no model download)
uv run pytest -m slow        # real Docling round-trip (downloads models)
uv run ruff check .
```

## License

Apache-2.0.