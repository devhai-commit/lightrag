"""add_business_account_fields — add company/approval fields to users for external business accounts

Revision ID: 008_add_business_account_fields
Revises: 007_add_document_datasets
Create Date: 2026-09-07

Adds:
- users.company_name, users.tax_code, users.phone, users.industry: nullable,
  only populated for role == "Doanh nghiệp" (external business self-signup).
- users.approval_status: nullable, "pending"/"approved"/"rejected" for
  business accounts, None (not applicable) for internal roles — mirrors the
  documents.approval_status convention (see 005_add_workspace_visibility).
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_add_business_account_fields"
down_revision: Union[str, None] = "007_add_document_datasets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_columns = {c["name"] for c in insp.get_columns("users")}

    if "company_name" not in existing_columns:
        op.add_column("users", sa.Column("company_name", sa.String(length=255), nullable=True))
    if "tax_code" not in existing_columns:
        op.add_column("users", sa.Column("tax_code", sa.String(length=50), nullable=True))
    if "phone" not in existing_columns:
        op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    if "industry" not in existing_columns:
        op.add_column("users", sa.Column("industry", sa.String(length=100), nullable=True))
    if "approval_status" not in existing_columns:
        op.add_column("users", sa.Column("approval_status", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "approval_status")
    op.drop_column("users", "industry")
    op.drop_column("users", "phone")
    op.drop_column("users", "tax_code")
    op.drop_column("users", "company_name")
