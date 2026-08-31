"""docling-parser: universal PDF/PPTX document parsing via Docling."""

from docling_parser.color import extract_palette
from docling_parser.converter import DocumentParser, ParseResult
from docling_parser.design_system import build_design_system
from docling_parser.storage import get_page, get_summary, list_parsed
from docling_parser.vision import VisionConfig, analyze

__all__ = [
    "DocumentParser",
    "ParseResult",
    "VisionConfig",
    "analyze",
    "build_design_system",
    "extract_palette",
    "get_page",
    "get_summary",
    "list_parsed",
]
__version__ = "0.2.0"