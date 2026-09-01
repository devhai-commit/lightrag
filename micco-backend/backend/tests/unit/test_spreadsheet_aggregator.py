"""
Unit tests for the spreadsheet aggregation engine.

Pure-function tests — no DB/async dependency. Covers correctness of every
allowed operation, group_by, filters, and the structured-error contract
(never an exception, always a dict with matched_row_count).
"""
from __future__ import annotations

import math

from app.services.spreadsheet_aggregator import aggregate


COLUMNS = [
    {"name": "year", "col_type": "numeric", "unit": ""},
    {"name": "quarter", "col_type": "text", "unit": ""},
    {"name": "region", "col_type": "text", "unit": ""},
    {"name": "revenue", "col_type": "numeric", "unit": "VND"},
]

ROWS = [
    {"year": 2023, "quarter": "Q1", "region": "North", "revenue": 100.0},
    {"year": 2023, "quarter": "Q2", "region": "South", "revenue": 200.0},
    {"year": 2023, "quarter": "Q3", "region": "North", "revenue": 150.0},
    {"year": 2024, "quarter": "Q1", "region": "North", "revenue": 300.0},
    {"year": 2024, "quarter": "Q2", "region": "South", "revenue": 250.0},
]


class TestScalarOperations:
    """sum/average/min/max/count/count_distinct correctness."""

    def test_sum(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue")
        assert result == {"result": 1000.0, "matched_row_count": 5}

    def test_average(self):
        result = aggregate(ROWS, COLUMNS, "average", "revenue")
        assert result["result"] == 200.0
        assert result["matched_row_count"] == 5

    def test_min(self):
        result = aggregate(ROWS, COLUMNS, "min", "revenue")
        assert result["result"] == 100.0

    def test_max(self):
        result = aggregate(ROWS, COLUMNS, "max", "revenue")
        assert result["result"] == 300.0

    def test_count_without_column_counts_rows(self):
        result = aggregate(ROWS, COLUMNS, "count", column=None)
        assert result == {"result": 5, "matched_row_count": 5}

    def test_count_with_column_counts_non_null(self):
        rows = ROWS + [{"year": 2024, "quarter": "Q3", "region": None, "revenue": None}]
        result = aggregate(rows, COLUMNS, "count", "revenue")
        assert result["result"] == 5  # last row's revenue is None, not counted

    def test_count_distinct(self):
        result = aggregate(ROWS, COLUMNS, "count_distinct", "region")
        assert result["result"] == 2

    def test_result_values_are_native_python_types(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue")
        assert isinstance(result["result"], float)
        assert isinstance(result["matched_row_count"], int)


class TestGroupBy:
    """group_by correctness and truncation."""

    def test_group_by_year_sum(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", group_by="year")
        assert result["groups"] == {"2023": 450.0, "2024": 550.0}
        assert result["matched_row_count"] == 5
        assert result["truncated_groups"] is False

    def test_group_by_region_count(self):
        result = aggregate(ROWS, COLUMNS, "count", "revenue", group_by="region")
        assert result["groups"] == {"North": 3, "South": 2}

    def test_group_by_max_groups_truncation(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", group_by="quarter", max_groups=1)
        assert result["truncated_groups"] is True
        assert len(result["groups"]) == 1


class TestFilters:
    """Single filter and combined filters (eq, gt, contains)."""

    def test_filter_eq(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", filters=[{"column": "year", "op": "eq", "value": 2023}])
        assert result == {"result": 450.0, "matched_row_count": 3}

    def test_filter_gt(self):
        result = aggregate(ROWS, COLUMNS, "count", filters=[{"column": "revenue", "op": "gt", "value": 150}])
        assert result["result"] == 3  # 200.0, 300.0, and 250.0

    def test_filter_contains(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", filters=[{"column": "region", "op": "contains", "value": "Nor"}])
        assert result == {"result": 550.0, "matched_row_count": 3}  # 100 + 150 + 300

    def test_combined_filters(self):
        result = aggregate(
            ROWS, COLUMNS, "sum", "revenue",
            filters=[
                {"column": "region", "op": "eq", "value": "North"},
                {"column": "year", "op": "eq", "value": 2023},
            ],
        )
        assert result == {"result": 250.0, "matched_row_count": 2}  # 100 + 150


class TestStructuredErrors:
    """Missing column / unknown operation -> structured error dict, never an exception."""

    def test_unknown_operation_returns_error_dict(self):
        result = aggregate(ROWS, COLUMNS, "median", "revenue")
        assert "error" in result
        assert "median" in result["error"]

    def test_missing_column_returns_error_dict(self):
        result = aggregate(ROWS, COLUMNS, "sum", "does_not_exist")
        assert "error" in result
        assert "does_not_exist" in result["error"]
        assert "available_columns" in result

    def test_missing_group_by_column_returns_error(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", group_by="does_not_exist")
        assert "error" in result

    def test_missing_filter_column_returns_error(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", filters=[{"column": "nope", "op": "eq", "value": 1}])
        assert "error" in result

    def test_unknown_filter_op_returns_error(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", filters=[{"column": "year", "op": "regex", "value": 1}])
        assert "error" in result

    def test_non_numeric_column_for_sum_returns_error(self):
        result = aggregate(ROWS, COLUMNS, "sum", "quarter")
        assert "error" in result
        assert "quarter" in result["error"]

    def test_missing_column_required_for_non_count_op(self):
        result = aggregate(ROWS, COLUMNS, "sum", column=None)
        assert "error" in result

    def test_never_raises_on_bad_input(self):
        # Should not raise even with garbage inputs.
        result = aggregate([], [], "sum", "x")
        assert isinstance(result, dict)


class TestEmptySelection:
    """Empty-selection-after-filter -> result=None, matched_row_count=0 (never NaN/inf)."""

    def test_filter_matches_nothing(self):
        result = aggregate(ROWS, COLUMNS, "sum", "revenue", filters=[{"column": "year", "op": "eq", "value": 1999}])
        assert result == {"result": None, "matched_row_count": 0}

    def test_empty_rows_input(self):
        result = aggregate([], COLUMNS, "sum", "revenue")
        assert result == {"result": None, "matched_row_count": 0}

    def test_group_by_with_no_matches(self):
        result = aggregate(
            ROWS, COLUMNS, "sum", "revenue", group_by="year",
            filters=[{"column": "year", "op": "eq", "value": 1999}],
        )
        assert result["matched_row_count"] == 0
        assert result["groups"] == {}

    def test_no_nan_or_inf_leaks(self):
        rows = [{"year": 2023, "quarter": "Q1", "region": "North", "revenue": None}]
        result = aggregate(rows, COLUMNS, "sum", "revenue")
        assert result["result"] is None
        value = result["result"]
        if isinstance(value, float):
            assert math.isfinite(value)
