"""
Document Parser Package
========================

Factory function to create document parsers based on config.

Usage::

    from app.services.document_parser import get_document_parser

    parser = get_document_parser(workspace_id=1)
    result = parser.parse(file_path, document_id, original_filename)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.services.document_parser.base import BaseDocumentParser


def get_document_parser(
    workspace_id: int,
    output_dir: Optional[Path] = None,
    file_path: Optional[str | Path] = None,
) -> BaseDocumentParser:
    """Create a document parser based on ``NEXUSRAG_DOCUMENT_PARSER`` config.

    When *file_path* is given and its extension is a spreadsheet extension
    (``.xlsx``/``.csv``), the ``SpreadsheetDocumentParser`` is returned
    immediately, bypassing the docling/marker branch entirely — spreadsheets
    need structured typed-row parsing, not markdown chunking. Call sites that
    don't pass *file_path* (the original call style) are unaffected.
    """
    from app.core.config import settings
    from app.services.document_parser.spreadsheet_parser import SpreadsheetDocumentParser

    if file_path is not None and Path(file_path).suffix.lower() in SpreadsheetDocumentParser.supported_extensions():
        return SpreadsheetDocumentParser(workspace_id, output_dir)

    provider = settings.NEXUSRAG_DOCUMENT_PARSER.lower()

    if provider == "marker":
        from app.services.document_parser.marker_parser import MarkerDocumentParser

        return MarkerDocumentParser(workspace_id, output_dir)

    # Default: docling
    from app.services.document_parser.docling_parser import DoclingDocumentParser

    return DoclingDocumentParser(workspace_id, output_dir)


__all__ = [
    "get_document_parser",
    "BaseDocumentParser",
]
