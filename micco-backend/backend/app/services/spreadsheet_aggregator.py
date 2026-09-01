"""
Spreadsheet Aggregation Engine
===============================

Pure, deterministic aggregation over ``DocumentDataset`` rows — no DB/async
dependency, trivially unit-testable. Backs the ``aggregate_spreadsheet_data``
chat tool so revenue/total/average questions get an exact computed answer
instead of the LLM eyeball-summing numbers from retrieved text chunks.

Security note: ``operation``/``column``/filter values are NEVER passed into
``eval``, ``exec``, or ``DataFrame.query()`` — every operation is dispatched
through an explicit allow-list, and filters are applied via boolean
``.loc[]`` masks built in plain Python.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

_ALLOWED_OPS = {"sum", "average", "min", "max", "count", "count_distinct"}
_FILTER_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "contains"}

_NUMERIC_OPS = {"sum", "average", "min", "max"}


def _apply_filter_mask(series: pd.Series, op: str, value: Any) -> pd.Series:
    """Build a boolean mask for one filter triple, without string eval."""
    if op == "contains":
        return series.astype(str).str.contains(str(value), na=False, regex=False)

    numeric_series = pd.to_numeric(series, errors="coerce")
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]

    if pd.notna(numeric_value) and numeric_series.notna().sum() > 0:
        left, right = numeric_series, numeric_value
    else:
        left, right = series.astype(str), str(value)

    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    raise ValueError(f"unsupported filter op: {op}")  # pragma: no cover — guarded by caller


def _to_json_native(value: Any) -> Any:
    """Cast numpy/pandas scalar types to native Python types for JSON safety."""
    if value is None:
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):  # numpy scalar (int64, float64, bool_, ...)
        native = value.item()
        return _to_json_native(native)
    return value


def aggregate(
    rows: list[dict],
    columns: list[dict],
    operation: str,
    column: Optional[str] = None,
    group_by: Optional[str] = None,
    filters: Optional[list[dict]] = None,
    max_groups: int = 50,
) -> dict:
    """Compute a deterministic aggregation over spreadsheet rows.

    Args:
        rows: JSON-native row dicts (as stored on ``DocumentDataset.rows``).
        columns: ``[{"name":..., "col_type":..., "unit":...}, ...]`` — plain
            dicts, not the ``DatasetColumn`` dataclass.
        operation: one of ``sum, average, min, max, count, count_distinct``.
        column: target column for the operation. Required for every op
            except ``count`` (which may operate on plain row count).
        group_by: optional column name to group by before aggregating.
        filters: optional list of ``{"column", "op", "value"}`` triples,
            ``op`` in ``eq/neq/gt/gte/lt/lte/contains``.
        max_groups: cap on the number of groups returned (by row count desc).

    Returns:
        A JSON-serializable dict. Always includes ``matched_row_count``.
        On any validation failure, returns ``{"error": ..., ...}`` instead
        of raising — callers should treat any ``"error"`` key as a failure.
    """
    column_names = {c["name"] for c in columns}
    col_type_by_name = {c["name"]: c.get("col_type", "unknown") for c in columns}

    if operation not in _ALLOWED_OPS:
        return {
            "error": f"unsupported operation: {operation}",
            "allowed_operations": sorted(_ALLOWED_OPS),
        }

    if column is not None and column not in column_names:
        return {"error": f"column not found: {column}", "available_columns": sorted(column_names)}

    if group_by is not None and group_by not in column_names:
        return {"error": f"column not found: {group_by}", "available_columns": sorted(column_names)}

    if column is None and operation != "count":
        return {"error": f"'column' is required for operation '{operation}'"}

    for f in filters or []:
        f_col = f.get("column")
        f_op = f.get("op")
        if f_col not in column_names:
            return {"error": f"column not found: {f_col}", "available_columns": sorted(column_names)}
        if f_op not in _FILTER_OPS:
            return {"error": f"unsupported filter op: {f_op}", "allowed_filter_ops": sorted(_FILTER_OPS)}

    if column is not None and operation in _NUMERIC_OPS:
        col_type = col_type_by_name.get(column, "unknown")
        if col_type not in ("numeric", "percentage"):
            return {
                "error": (
                    f"column '{column}' is not numeric (actual type: {col_type}); "
                    f"cannot compute {operation} over it"
                )
            }

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=sorted(column_names))
    # Ensure every declared column exists even if all rows happened to omit it.
    for name in column_names:
        if name not in df.columns:
            df[name] = None

    for f in filters or []:
        try:
            mask = _apply_filter_mask(df[f["column"]], f["op"], f.get("value"))
        except Exception as e:
            return {"error": f"failed to apply filter on '{f['column']}': {e}"}
        df = df[mask]

    matched_row_count = int(len(df))

    if matched_row_count == 0:
        result: dict = {"result": None, "matched_row_count": 0}
        if group_by:
            result["groups"] = {}
            result["truncated_groups"] = False
        return result

    numeric_series = pd.to_numeric(df[column], errors="coerce") if column and operation in _NUMERIC_OPS else None

    if group_by:
        return _aggregate_grouped(df, operation, column, group_by, max_groups, matched_row_count)

    scalar = _aggregate_scalar(df, operation, column, numeric_series)
    return {"result": _to_json_native(scalar), "matched_row_count": matched_row_count}


def _aggregate_scalar(
    df: pd.DataFrame, operation: str, column: Optional[str], numeric_series: Optional[pd.Series]
) -> Any:
    if operation == "count":
        if column is None:
            return len(df)
        return int(df[column].notna().sum())
    if operation == "count_distinct":
        return int(df[column].dropna().nunique())

    # sum/average/min/max — numeric_series is pre-coerced, NaN-safe
    valid = numeric_series.dropna() if numeric_series is not None else pd.Series(dtype=float)
    if valid.empty:
        return None
    if operation == "sum":
        return float(valid.sum())
    if operation == "average":
        return float(valid.mean())
    if operation == "min":
        return float(valid.min())
    if operation == "max":
        return float(valid.max())
    raise AssertionError(f"unreachable operation: {operation}")  # pragma: no cover


def _aggregate_grouped(
    df: pd.DataFrame,
    operation: str,
    column: Optional[str],
    group_by: str,
    max_groups: int,
    matched_row_count: int,
) -> dict:
    grouped = df.groupby(group_by, dropna=False)

    group_sizes = grouped.size().sort_values(ascending=False)
    truncated_groups = len(group_sizes) > max_groups
    kept_keys = list(group_sizes.index[:max_groups])

    groups: dict[str, Any] = {}
    for key in kept_keys:
        sub_df = grouped.get_group(key)
        if operation in _NUMERIC_OPS:
            numeric_sub = pd.to_numeric(sub_df[column], errors="coerce")
            value = _aggregate_scalar(sub_df, operation, column, numeric_sub)
        else:
            value = _aggregate_scalar(sub_df, operation, column, None)
        group_key = "null" if pd.isna(key) else str(key)
        groups[group_key] = _to_json_native(value)

    return {
        "groups": groups,
        "matched_row_count": matched_row_count,
        "truncated_groups": truncated_groups,
    }
