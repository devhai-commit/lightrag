"""add_document_datasets — create document_datasets table for structured spreadsheet data

Revision ID: 007_add_document_datasets
Revises: 006_add_rejected_status
Create Date: 2026-08-25

Adds:
- document_datasets table: typed row data extracted from one sheet of a
  spreadsheet (.xlsx/.csv), consumed by the aggregate_spreadsheet_data
  chat tool for exact arithmetic over spreadsheet data.
- documents.dataset_count column: parity with image_count/table_count.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "007_add_document_datasets"
down_revision: Union[str, None] = "006_add_rejected_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create document_datasets table and add documents.dataset_count.

    Idempotent: both may already exist if the app's AUTO_CREATE_TABLES
    startup ran before this migration (they're part of the current ORM
    models), so guard both creations. No RLS policy is added here — mirrors
    document_images/document_tables, which also have none (see
    002_add_rls_policies.py).
    """
    bind = op.get_bind()
    insp = inspect(bind)

    if "document_datasets" not in insp.get_table_names():
        op.create_table(
            "document_datasets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("dataset_id", sa.String(length=100), nullable=False),
            sa.Column("sheet_name", sa.String(length=255), nullable=False),
            sa.Column("columns", sa.JSON(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False, default=0),
            sa.Column("rows", sa.JSON(), nullable=False),
            sa.Column("truncated", sa.Boolean(), nullable=False, default=False),
            sa.Column("truncated_at_row", sa.Integer(), nullable=False, default=0),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dataset_id"),
        )
        op.create_index(
            "ix_document_datasets_document_id", "document_datasets", ["document_id"]
        )

    if "documents" in insp.get_table_names():
        existing_columns = {c["name"] for c in insp.get_columns("documents")}
        if "dataset_count" not in existing_columns:
            op.add_column(
                "documents", sa.Column("dataset_count", sa.Integer(), nullable=True, server_default="0")
            )


def downgrade() -> None:
    """Drop document_datasets table and documents.dataset_count column."""
    op.drop_index("ix_document_datasets_document_id", table_name="document_datasets")
    op.drop_table("document_datasets")
    op.drop_column("documents", "dataset_count")
