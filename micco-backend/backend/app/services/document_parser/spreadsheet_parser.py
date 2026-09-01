"""
Spreadsheet Document Parser
============================

Parses ``.xlsx`` / ``.csv`` files into structured, typed row data
(``SheetDataset``) alongside a per-sheet LLM-facing summary chunk.

Unlike Docling/Marker, this parser does NOT chunk by token count — each
sheet becomes exactly one ``EnrichedChunk`` + one ``ExtractedTable`` + one
``SheetDataset``, so downstream consumers (the ``aggregate_spreadsheet_data``
chat tool) can reference a sheet by ``(document_id, sheet_name)`` and compute
exact sums/averages instead of asking the LLM to eyeball totals from a
markdown preview.
"""
from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from app.core.config import settings
from app.services.document_parser.base import BaseDocumentParser
from app.services.models.parsed_document import (
    DatasetColumn,
    EnrichedChunk,
    ExtractedTable,
    ParsedDocument,
    SheetDataset,
)

logger = logging.getLogger(__name__)

_SPREADSHEET_EXTENSIONS = {".xlsx", ".csv"}

# How many leading rows to scan when the naive header=0 read looks wrong.
_HEADER_SCAN_ROWS = 20

# Currency/unit suffixes stripped from numeric strings before parsing.
# Sorted longest-first so "VNĐ" is checked before "Đ" etc.
_CURRENCY_UNIT_SUFFIXES = sorted(
    ["VNĐ", "VND", "USD", "₫", "đ", "$"], key=len, reverse=True
)

# A cell "looks numeric-ish" if, after unit stripping, it only contains
# digits, separators, and an optional leading minus sign.
_NUMERIC_CHAR_RE = re.compile(r"^-?[\d.,]+$")


class SpreadsheetDocumentParser(BaseDocumentParser):
    """Parses Excel/CSV workbooks into typed ``SheetDataset`` rows + summaries."""

    parser_name = "spreadsheet"

    @staticmethod
    def supported_extensions() -> set[str]:
        return _SPREADSHEET_EXTENSIONS

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse(
        self,
        file_path: str | Path,
        document_id: int,
        original_filename: str,
    ) -> ParsedDocument:
        path = Path(file_path)
        ext = path.suffix.lower()

        raw_sheets = self._read_raw_sheets(path, ext)

        max_sheets = settings.NEXUSRAG_SPREADSHEET_MAX_SHEETS_PER_WORKBOOK
        sheet_names = list(raw_sheets.keys())[:max_sheets]

        chunks: list[EnrichedChunk] = []
        tables: list[ExtractedTable] = []
        datasets: list[SheetDataset] = []
        markdown_parts: list[str] = []

        for sheet_index, sheet_name in enumerate(sheet_names):
            try:
                cleaned = self._detect_and_clean(raw_sheets[sheet_name])
                if cleaned is None or cleaned.empty:
                    logger.info(f"Skipping empty/unrecognized sheet '{sheet_name}'")
                    continue

                columns, df_typed = self._infer_types(cleaned)
                dataset = self._build_dataset(document_id, str(sheet_name), columns, df_typed)
                datasets.append(dataset)

                summary_text = self._build_summary_chunk_text(document_id, str(sheet_name), dataset)
                chunks.append(EnrichedChunk(
                    content=summary_text,
                    chunk_index=sheet_index,
                    source_file=original_filename,
                    document_id=document_id,
                    page_no=sheet_index + 1,
                    has_table=True,
                ))
                markdown_parts.append(summary_text)

                preview_md = self._preview_markdown(dataset)
                tables.append(ExtractedTable(
                    table_id=f"spreadsheet_{document_id}_{sheet_index}",
                    document_id=document_id,
                    page_no=sheet_index + 1,
                    content_markdown=preview_md,
                    caption=f"Sheet '{sheet_name}' ({dataset.row_count} rows)",
                    num_rows=dataset.row_count,
                    num_cols=len(dataset.columns),
                ))
            except Exception as e:
                logger.warning(f"Failed to parse sheet '{sheet_name}' of doc {document_id}: {e}")
                continue

        return ParsedDocument(
            document_id=document_id,
            original_filename=original_filename,
            markdown="\n\n---\n\n".join(markdown_parts),
            page_count=len(sheet_names),
            chunks=chunks,
            images=[],
            tables=tables,
            tables_count=len(tables),
            datasets=datasets,
        )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @staticmethod
    def _read_raw_sheets(path: Path, ext: str) -> dict[str, pd.DataFrame]:
        """Read every sheet with ``header=None`` so header-row detection runs uniformly.

        ``dtype=object`` preserves native per-cell Python types (float/int/str/
        datetime/None) exactly as read from the file, instead of pandas
        coercing an entire column to one dtype up front.
        """
        if ext == ".csv":
            try:
                df = pd.read_csv(path, header=None, dtype=object, encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(path, header=None, dtype=object, encoding="latin-1")
            return {"Sheet1": df}

        # .xlsx
        return pd.read_excel(path, sheet_name=None, header=None, dtype=object, engine="openpyxl")

    # ------------------------------------------------------------------
    # Header detection + cleaning
    # ------------------------------------------------------------------

    def _detect_and_clean(self, df_raw: pd.DataFrame) -> Optional[pd.DataFrame]:
        if df_raw is None or df_raw.empty:
            return None

        header_idx = self._detect_header_row(df_raw)
        if header_idx is None:
            return None

        header_row = df_raw.iloc[header_idx]
        body = df_raw.iloc[header_idx + 1:].reset_index(drop=True)
        if body.empty:
            return None

        body.columns = self._dedupe_column_names(header_row.tolist())

        # Drop fully-empty rows/columns (merged-cell / spacer artifacts).
        body = body.dropna(axis=0, how="all")
        body = body.dropna(axis=1, how="all")
        if body.empty:
            return None
        body = body.reset_index(drop=True)

        # Forward-fill only partially-null LABEL columns among the first few
        # columns (merged-cell artifact where a group label only appears on
        # the first row of the group). Never touch numeric columns — a blank
        # numeric cell must stay blank, not inherit a neighboring value.
        n_label_cols = min(3, len(body.columns))
        for col in body.columns[:n_label_cols]:
            series = body[col]
            if series.isna().any() and not series.isna().all() and self._looks_like_label_column(series):
                body[col] = series.ffill()

        return body

    def _detect_header_row(self, df_raw: pd.DataFrame) -> Optional[int]:
        """Find the header row, scanning past title/spacer rows if needed."""
        scan_limit = min(_HEADER_SCAN_ROWS, len(df_raw) - 1)

        for idx in range(scan_limit + 1):
            if self._row_is_header_like(df_raw, idx) and self._row_is_data_like(df_raw, idx + 1):
                return idx

        # Fallback: naive header=0, as long as it has any content at all.
        if not df_raw.iloc[0].dropna().empty:
            return 0
        return None

    def _row_is_header_like(self, df_raw: pd.DataFrame, idx: int) -> bool:
        if idx >= len(df_raw):
            return False
        row = df_raw.iloc[idx]
        non_null = row.dropna()
        if non_null.empty:
            return False
        text_like = sum(1 for v in non_null if self._parse_vn_number_with_unit(v)[0] is None)
        return (text_like / len(non_null)) >= 0.6 and (len(non_null) / len(row)) >= 0.5

    def _row_is_data_like(self, df_raw: pd.DataFrame, idx: int) -> bool:
        if idx >= len(df_raw):
            return False
        row = df_raw.iloc[idx]
        non_null = row.dropna()
        if non_null.empty:
            return False
        numeric_like = sum(1 for v in non_null if self._parse_vn_number_with_unit(v)[0] is not None)
        return numeric_like > 0

    @staticmethod
    def _dedupe_column_names(raw_names: list) -> list[str]:
        columns = [
            str(v).strip() if v is not None and str(v).strip() else f"col_{i}"
            for i, v in enumerate(raw_names)
        ]
        seen: dict[str, int] = {}
        deduped: list[str] = []
        for c in columns:
            if c in seen:
                seen[c] += 1
                deduped.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                deduped.append(c)
        return deduped

    def _looks_like_label_column(self, series: pd.Series) -> bool:
        non_null = series.dropna()
        if non_null.empty:
            return False
        numeric_like = sum(1 for v in non_null if self._parse_vn_number_with_unit(v)[0] is not None)
        return (numeric_like / len(non_null)) < 0.5

    # ------------------------------------------------------------------
    # Type inference
    # ------------------------------------------------------------------

    def _infer_types(self, df: pd.DataFrame) -> tuple[list[DatasetColumn], pd.DataFrame]:
        columns: list[DatasetColumn] = []
        result = pd.DataFrame(index=df.index)

        for col in df.columns:
            series = df[col]
            col_type, unit, converted = self._infer_column(series)
            columns.append(DatasetColumn(name=str(col), col_type=col_type, unit=unit))
            result[str(col)] = converted

        return columns, result

    def _infer_column(self, series: pd.Series) -> tuple[str, str, pd.Series]:
        non_null = series.dropna()
        if len(non_null) == 0:
            return "unknown", "", series.apply(lambda v: None)

        parsed = [self._parse_vn_number_with_unit(v) for v in non_null]
        numeric_hits = sum(1 for num, _ in parsed if num is not None)
        pct_hits = sum(1 for v in non_null if isinstance(v, str) and v.strip().endswith("%"))
        units_found = {u for _, u in parsed if u and u != "%"}

        if numeric_hits / len(non_null) >= 0.6:
            is_percentage = pct_hits / len(non_null) >= 0.5
            col_type = "percentage" if is_percentage else "numeric"
            unit = "%" if is_percentage else (next(iter(units_found), ""))
            converted = series.apply(lambda v: self._parse_vn_number_with_unit(v)[0])
            return col_type, unit, converted

        date_hits = sum(1 for v in non_null if self._fmt_date_cell(v) is not None)
        if date_hits / len(non_null) >= 0.6:
            converted = series.apply(self._fmt_date_cell)
            return "date", "", converted

        converted = series.apply(lambda v: None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v).strip())
        return "text", "", converted

    @staticmethod
    def _fmt_date_cell(v) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        if isinstance(v, (int, float)):
            # Bare numbers are handled by the numeric branch, not dates.
            return None
        try:
            ts = pd.to_datetime(v, errors="coerce", dayfirst=True)
        except (ValueError, TypeError):
            return None
        if ts is None or pd.isna(ts):
            return None
        return ts.strftime("%Y-%m-%d")

    @staticmethod
    def _normalize_number_string(s: str) -> str:
        """Normalize a numeric string, handling Vietnamese ',' decimal / '.' thousands."""
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                # VN style: "." thousands, "," decimal -> "1.234,56" -> "1234.56"
                return s.replace(".", "").replace(",", ".")
            # US style: "," thousands, "." decimal -> "1,234.56" -> "1234.56"
            return s.replace(",", "")
        if "," in s:
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                # Single comma with 1-2 trailing digits -> decimal comma.
                return s.replace(",", ".")
            # Multiple commas or 3+ trailing digits -> thousands separator.
            return s.replace(",", "")
        return s

    def _parse_vn_number_with_unit(self, v) -> tuple[Optional[float], str]:
        """Parse a cell as a number, returning ``(value, unit)``.

        Handles native numeric types (already-typed Excel cells) and
        Vietnamese-formatted number strings. Currency/percent suffixes are
        stripped from the numeric string and recorded as the unit instead.
        """
        if v is None:
            return None, ""
        if isinstance(v, bool):
            return None, ""
        if isinstance(v, (int, float)):
            return (float(v), "") if math.isfinite(v) else (None, "")

        s = str(v).strip()
        if not s:
            return None, ""

        unit = ""
        for suffix in _CURRENCY_UNIT_SUFFIXES:
            if s.upper().endswith(suffix.upper()) and len(s) > len(suffix):
                unit = "VND" if suffix.upper() in ("VND", "VNĐ", "Đ", "₫") else suffix
                s = s[: len(s) - len(suffix)].strip()
                break

        if s.endswith("%"):
            unit = unit or "%"
            s = s[:-1].strip()

        if not s or not _NUMERIC_CHAR_RE.match(s):
            return None, unit

        normalized = self._normalize_number_string(s)
        try:
            num = float(normalized)
        except ValueError:
            return None, unit

        return (num, unit) if math.isfinite(num) else (None, unit)

    # ------------------------------------------------------------------
    # Dataset / summary building
    # ------------------------------------------------------------------

    def _build_dataset(
        self,
        document_id: int,
        sheet_name: str,
        columns: list[DatasetColumn],
        df_typed: pd.DataFrame,
    ) -> SheetDataset:
        true_row_count = len(df_typed)
        max_rows = settings.NEXUSRAG_SPREADSHEET_MAX_ROWS_PER_SHEET
        truncated = true_row_count > max_rows
        df_final = df_typed.iloc[:max_rows] if truncated else df_typed

        rows = self._df_to_native_rows(df_final, columns)

        return SheetDataset(
            document_id=document_id,
            sheet_name=sheet_name,
            columns=columns,
            row_count=true_row_count,
            rows=rows,
            truncated=truncated,
            truncated_at_row=max_rows if truncated else 0,
        )

    def _df_to_native_rows(self, df: pd.DataFrame, columns: list[DatasetColumn]) -> list[dict]:
        col_types = {c.name: c.col_type for c in columns}
        rows: list[dict] = []
        for _, row in df.iterrows():
            record: dict = {}
            for col_name in df.columns:
                record[str(col_name)] = self._to_native(row[col_name], col_types.get(str(col_name), "text"))
            rows.append(record)
        return rows

    @staticmethod
    def _to_native(val, col_type: str):
        if val is None:
            return None
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        if col_type in ("numeric", "percentage"):
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return str(val)

    def _build_summary_chunk_text(self, document_id: int, sheet_name: str, dataset: SheetDataset) -> str:
        col_lines = [
            f"- {c.name} ({c.col_type}" + (f", unit={c.unit})" if c.unit else ")")
            for c in dataset.columns
        ]
        sample_n = settings.NEXUSRAG_SPREADSHEET_SAMPLE_ROWS_IN_SUMMARY
        sample_rows = dataset.rows[:sample_n]
        preview_table = self._rows_to_markdown_table(dataset.columns, sample_rows)

        truncation_note = (
            f" (truncated to {dataset.truncated_at_row} rows during processing)"
            if dataset.truncated else ""
        )

        lines = [
            f"## Spreadsheet Sheet: {sheet_name}",
            f"document_id={document_id}",
            f'sheet_name="{sheet_name}"',
            f"Rows: {dataset.row_count}{truncation_note}",
            "",
            "Columns:",
            *col_lines,
            "",
            f"Sample rows (first {len(sample_rows)} of {dataset.row_count}):",
            preview_table,
            "",
            (
                f"To compute exact sums, averages, totals, or counts over this sheet, "
                f"call the aggregate_spreadsheet_data tool with document_id={document_id} "
                f'and sheet_name="{sheet_name}". Do NOT hand-calculate totals from this preview.'
            ),
        ]
        return "\n".join(lines)

    def _preview_markdown(self, dataset: SheetDataset) -> str:
        sample_n = settings.NEXUSRAG_SPREADSHEET_SAMPLE_ROWS_IN_SUMMARY
        return self._rows_to_markdown_table(dataset.columns, dataset.rows[:sample_n])

    @staticmethod
    def _rows_to_markdown_table(columns: list[DatasetColumn], rows: list[dict]) -> str:
        if not rows:
            return "_(no rows)_"
        headers = [c.name for c in columns]
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        body_lines = []
        for row in rows:
            cells = [SpreadsheetDocumentParser._format_cell(row.get(h)) for h in headers]
            body_lines.append("| " + " | ".join(cells) + " |")
        return "\n".join([header_line, sep_line, *body_lines])

    @staticmethod
    def _format_cell(val) -> str:
        if val is None:
            return ""
        if isinstance(val, float):
            return f"{val:g}"
        return str(val).replace("|", "\\|")
