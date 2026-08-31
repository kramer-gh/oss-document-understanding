# docling-parser Project Memory

Cross-session learnings and gotchas. Updated as new patterns are discovered.

## Environment

- **LibreOffice broken symlink on macOS** — `brew install --cask libreoffice`
  creates a symlink at `/opt/homebrew/bin/soffice` that can be broken. The code
  falls back to `/Applications/LibreOffice.app/Contents/MacOS/soffice`. If
  vision mode fails with "requires LibreOffice", check `ls -la
  /opt/homebrew/bin/soffice` — if broken, use the app bundle path directly.

- **AGENTWORKS_API_KEY** — Must be set for vision mode. Length 43. The env var
  is inherited by the MCP server subprocess from OpenCode's environment.

## Vision Pipeline

- **VLM JSON is often malformed** — Gemma 4 sometimes emits missing commas,
  trailing commas, or unescaped quotes in `readable_text`. The `_extract_json`
  function tries `json.loads` first, then falls back to `json_repair.loads`.
  If both fail, the page gets an error entry (not a crash).

- **One failed page doesn't kill the document** — Per-page VLM failures are
  caught and included as error entries in the results. The document summary
  still synthesizes from successful pages.

- **Large decks need lower concurrency** — 64-slide deck with concurrency=6
  caused "Connection reset by peer". Use `VISION_CONCURRENCY=3` for large
  decks. The retry logic (3 attempts, exponential backoff) helps but doesn't
  fully prevent rate-limiting.

- **Docling `caption_text` can be a method** — In some Docling versions,
  `pic.caption_text` is a method, not a string. The normalizer calls it if
  callable, then truncates to 500 chars (Docling sometimes stuffs base64 image
  data into caption_text — one deck had a 1.8M char "caption").

- **Docling page images work for PDF but not PPTX** — `page.image.pil_image`
  returns a PIL image for PDF pages but `None` for PPTX. That's why we use
  pymupdf for rendering (PDF directly, PPTX via LibreOffice→PDF→pymupdf).

## Color Extraction

- **PIL quantize palette can be shorter than requested** — For solid-color
  images, `quantize(colors=8)` may return fewer than 8 palette entries. The
  code checks `len(palette) // 3` instead of assuming `num_colors`.

- **Accent color is None for monochrome pages** — If all non-dominant colors
  are near-white/near-black (zero saturation), accent is None. This is correct
  for monochrome pages.

## File Strategy

- **`save=True` splits output into browsable chunks** — The index file
  (`{stem}.index.json`) is the entry point: ~6 KB with page summaries and
  file paths. Per-page files are ~2-6 KB each. The full file can be 70KB-1MB.
  Agents should load the index first, then specific pages.

- **Stem sanitization** — Source filenames are lowercased and non-alphanumeric
  chars replaced with hyphens. `Agent_Works™ (former Polis)_ External Deck.pptx`
  → `agent-works-former-polis-external-deck`.

## MCP Integration

- **MCP server runs via `uv run --directory <path> docling-parser-mcp`** —
  Registered in OpenCode global config at `~/.config/opencode/opencode.json`.
  Config is loaded once at startup; restart OpenCode after changes.

- **5 MCP tools exposed** — `parse_document`, `build_design_system`,
  `list_parsed`, `get_page`, `get_summary`. All return `{"error": ...}` on
  failure, never raise.
