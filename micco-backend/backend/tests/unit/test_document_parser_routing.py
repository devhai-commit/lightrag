"""
Unit tests for extension-aware document parser routing.

Verifies get_document_parser() routes .xlsx/.csv to SpreadsheetDocumentParser
regardless of the configured NEXUSRAG_DOCUMENT_PARSER, that non-spreadsheet
extensions still route to the configured docling/marker default, and that
the original no-file_path call style is unaffected.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.document_parser import get_document_parser
from app.services.document_parser.spreadsheet_parser import SpreadsheetDocumentParser
from app.services.document_parser.docling_parser import DoclingDocumentParser


class TestSpreadsheetRouting:
    @pytest.mark.parametrize("configured_parser", ["docling", "marker"])
    def test_xlsx_routes_to_spreadsheet_parser(self, monkeypatch, configured_parser):
        monkeypatch.setattr(settings, "NEXUSRAG_DOCUMENT_PARSER", configured_parser)

        parser = get_document_parser(workspace_id=1, file_path="revenue.xlsx")

        assert isinstance(parser, SpreadsheetDocumentParser)

    @pytest.mark.parametrize("configured_parser", ["docling", "marker"])
    def test_csv_routes_to_spreadsheet_parser(self, monkeypatch, configured_parser):
        monkeypatch.setattr(settings, "NEXUSRAG_DOCUMENT_PARSER", configured_parser)

        parser = get_document_parser(workspace_id=1, file_path="revenue.csv")

        assert isinstance(parser, SpreadsheetDocumentParser)

    def test_xlsx_uppercase_extension_still_routes(self, monkeypatch):
        monkeypatch.setattr(settings, "NEXUSRAG_DOCUMENT_PARSER", "docling")
        parser = get_document_parser(workspace_id=1, file_path="revenue.XLSX")
        assert isinstance(parser, SpreadsheetDocumentParser)


class TestNonSpreadsheetRouting:
    def test_pdf_routes_to_configured_default_docling(self, monkeypatch):
        monkeypatch.setattr(settings, "NEXUSRAG_DOCUMENT_PARSER", "docling")
        parser = get_document_parser(workspace_id=1, file_path="report.pdf")
        assert isinstance(parser, DoclingDocumentParser)

    def test_pdf_routes_to_configured_default_marker(self, monkeypatch):
        monkeypatch.setattr(settings, "NEXUSRAG_DOCUMENT_PARSER", "marker")
        from app.services.document_parser.marker_parser import MarkerDocumentParser

        parser = get_document_parser(workspace_id=1, file_path="report.pdf")
        assert isinstance(parser, MarkerDocumentParser)


class TestNoFilePathCallStyle:
    def test_no_file_path_returns_default_docling(self, monkeypatch):
        monkeypatch.setattr(settings, "NEXUSRAG_DOCUMENT_PARSER", "docling")
        parser = get_document_parser(workspace_id=1)
        assert isinstance(parser, DoclingDocumentParser)

    def test_no_file_path_returns_default_marker(self, monkeypatch):
        monkeypatch.setattr(settings, "NEXUSRAG_DOCUMENT_PARSER", "marker")
        from app.services.document_parser.marker_parser import MarkerDocumentParser

        parser = get_document_parser(workspace_id=1)
        assert isinstance(parser, MarkerDocumentParser)
