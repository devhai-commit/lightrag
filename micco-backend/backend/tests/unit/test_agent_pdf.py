"""Unit tests for rendering an n8n AI Agent's markdown answer to PDF."""
from __future__ import annotations

from app.services.agent_pdf import render_markdown_to_pdf


def test_render_markdown_to_pdf_produces_a_valid_pdf_document():
    pdf_bytes = render_markdown_to_pdf(
        title="Tóm tắt tài liệu",
        content_markdown="# Mục 1\n\nNội dung tóm tắt bằng tiếng Việt có dấu.",
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 0


def test_render_markdown_to_pdf_handles_multiple_paragraphs_and_blank_lines():
    pdf_bytes = render_markdown_to_pdf(
        title="Báo cáo",
        content_markdown="Đoạn một.\n\nĐoạn hai sau dòng trống.",
    )

    assert pdf_bytes.startswith(b"%PDF")
