"""
Unit tests for the aggregate_spreadsheet_data chat tool executor.

No LLM involved — calls _execute_aggregate_spreadsheet_data directly with a
mocked AsyncSession, following this repo's convention (see
tests/unit/test_expert_recommendation.py) of mocking external calls with
unittest.mock.AsyncMock/MagicMock.

The workspace-ownership check is security-relevant: a document_id comes
straight from model output and could belong to another workspace, so the
"not found" path must trigger instead of leaking another workspace's data.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.chat_agent import _execute_aggregate_spreadsheet_data


def _fake_dataset(**overrides) -> SimpleNamespace:
    defaults = dict(
        dataset_id="ds-uuid-1",
        sheet_name="Q1 2024",
        columns=[
            {"name": "quarter", "col_type": "text", "unit": ""},
            {"name": "revenue", "col_type": "numeric", "unit": "VND"},
        ],
        row_count=2,
        rows=[
            {"quarter": "Q1", "revenue": 100.0},
            {"quarter": "Q1", "revenue": 200.0},
        ],
        truncated=False,
        truncated_at_row=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_result(scalar_value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    return result


def _mock_rows_result(values: list):
    """Mimic `.all()` on a select(DocumentDataset.sheet_name) query — list of 1-tuples."""
    result = MagicMock()
    result.all.return_value = [(v,) for v in values]
    return result


class TestScalarAggregation:
    @pytest.mark.asyncio
    async def test_scalar_sum_formats_correctly(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_mock_result(_fake_dataset()))

        text, source = await _execute_aggregate_spreadsheet_data(
            workspace_id=1,
            document_id=12,
            sheet_name="Q1 2024",
            operation="sum",
            column="revenue",
            group_by=None,
            filters=None,
            db=db,
            existing_ids=set(),
        )

        assert "300" in text
        assert "sum" in text
        assert source is not None
        assert source.source_type == "dataset"
        assert source.document_id == 12
        assert source.heading_path == ["Q1 2024"]

    @pytest.mark.asyncio
    async def test_truncated_dataset_includes_caveat(self):
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=_mock_result(_fake_dataset(truncated=True, truncated_at_row=5000))
        )

        text, source = await _execute_aggregate_spreadsheet_data(
            workspace_id=1,
            document_id=12,
            sheet_name="Q1 2024",
            operation="sum",
            column="revenue",
            group_by=None,
            filters=None,
            db=db,
            existing_ids=set(),
        )

        assert "5000" in text
        assert "cắt" in text or "truncat" in text.lower()


class TestGroupByAggregation:
    @pytest.mark.asyncio
    async def test_group_by_result_formats_as_table(self):
        dataset = _fake_dataset(
            rows=[
                {"quarter": "Q1", "revenue": 100.0},
                {"quarter": "Q2", "revenue": 200.0},
            ],
        )
        db = MagicMock()
        db.execute = AsyncMock(return_value=_mock_result(dataset))

        text, source = await _execute_aggregate_spreadsheet_data(
            workspace_id=1,
            document_id=12,
            sheet_name="Q1 2024",
            operation="sum",
            column="revenue",
            group_by="quarter",
            filters=None,
            db=db,
            existing_ids=set(),
        )

        assert "Q1" in text
        assert "Q2" in text
        assert "100" in text
        assert "200" in text
        assert source is not None


class TestErrorFormatting:
    @pytest.mark.asyncio
    async def test_aggregator_error_surfaces_in_text_no_source(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_mock_result(_fake_dataset()))

        text, source = await _execute_aggregate_spreadsheet_data(
            workspace_id=1,
            document_id=12,
            sheet_name="Q1 2024",
            operation="sum",
            column="does_not_exist",
            group_by=None,
            filters=None,
            db=db,
            existing_ids=set(),
        )

        assert "error" in text.lower() or "not found" in text.lower()
        # A source chunk is still produced (pointing at the sheet); the
        # error text itself communicates the failure to the LLM.
        assert source is not None


class TestWorkspaceIsolation:
    """Security-relevant: document_id from model output must be workspace-scoped."""

    @pytest.mark.asyncio
    async def test_document_in_other_workspace_returns_not_found_no_leak(self):
        db = MagicMock()
        # 1st call: joined dataset+workspace query -> no match (wrong workspace)
        # 2nd call: Document.id check scoped to this workspace -> also no match
        db.execute = AsyncMock(side_effect=[
            _mock_result(None),
            _mock_result(None),
        ])

        text, source = await _execute_aggregate_spreadsheet_data(
            workspace_id=999,  # attacker's workspace
            document_id=12,    # document actually belongs to workspace 1
            sheet_name="Q1 2024",
            operation="sum",
            column="revenue",
            group_by=None,
            filters=None,
            db=db,
            existing_ids=set(),
        )

        assert "not found" in text.lower()
        assert source is None
        # Must not have reached the sheet-listing query, which would only
        # be safe to run once ownership is confirmed.
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_wrong_sheet_name_same_workspace_lists_available_sheets(self):
        db = MagicMock()
        # 1st call: dataset+sheet_name match fails (wrong sheet name)
        # 2nd call: Document.id check scoped to workspace -> found (correct workspace)
        # 3rd call: list sheet_names for this document -> some other sheets exist
        db.execute = AsyncMock(side_effect=[
            _mock_result(None),
            _mock_result(12),
            _mock_rows_result(["Q1 2024", "Q2 2024"]),
        ])

        text, source = await _execute_aggregate_spreadsheet_data(
            workspace_id=1,
            document_id=12,
            sheet_name="Nonexistent Sheet",
            operation="sum",
            column="revenue",
            group_by=None,
            filters=None,
            db=db,
            existing_ids=set(),
        )

        assert "Q1 2024" in text
        assert "Q2 2024" in text
        assert source is None
