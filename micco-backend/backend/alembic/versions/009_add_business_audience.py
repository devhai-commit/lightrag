"""add_business_audience — mark workspaces/documents as visible to the B2B portal

Revision ID: 009_add_business_audience
Revises: 008_add_business_account_fields
Create Date: 2026-09-07

Adds the two gates that decide whether external business users can see content.
Both must be satisfied (AND, never OR), so a single misconfiguration cannot
publish internal material:

- knowledge_bases.audience: "internal" (default) | "business". A new orthogonal
  column rather than a new value on the existing `visibility` column, because
  `visibility` drives _can_access_workspace/_can_modify_workspace/
  _can_delete_workspace (app/api/workspaces.py) for internal management —
  keeping them separate means zero regression risk to that logic.
- documents.is_business_visible: per-document opt-in, default false. Dropping a
  file into the business workspace must never auto-publish it.

"Only one business workspace" is enforced by a partial unique index rather than
an application check alone, so it holds even against direct SQL.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "009_add_business_audience"
down_revision: Union[str, None] = "008_add_business_account_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUSINESS_WORKSPACE_UNIQUE_INDEX = "uq_knowledge_bases_single_business_audience"
DOCUMENTS_BUSINESS_INDEX = "ix_documents_workspace_business_visible"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    kb_columns = {c["name"] for c in insp.get_columns("knowledge_bases")}
    if "audience" not in kb_columns:
        op.add_column(
            "knowledge_bases",
            sa.Column(
                "audience",
                sa.String(length=20),
                nullable=False,
                server_default="internal",
            ),
        )

    doc_columns = {c["name"] for c in insp.get_columns("documents")}
    if "is_business_visible" not in doc_columns:
        op.add_column(
            "documents",
            sa.Column(
                "is_business_visible",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    kb_indexes = {i["name"] for i in insp.get_indexes("knowledge_bases")}
    if BUSINESS_WORKSPACE_UNIQUE_INDEX not in kb_indexes:
        # At most one workspace may serve the business portal. Partial index so
        # the many "internal" rows stay unconstrained.
        op.create_index(
            BUSINESS_WORKSPACE_UNIQUE_INDEX,
            "knowledge_bases",
            ["audience"],
            unique=True,
            postgresql_where=sa.text("audience = 'business'"),
        )

    doc_indexes = {i["name"] for i in insp.get_indexes("documents")}
    if DOCUMENTS_BUSINESS_INDEX not in doc_indexes:
        # Covers the business allow-list query, which always filters on both.
        op.create_index(
            DOCUMENTS_BUSINESS_INDEX,
            "documents",
            ["workspace_id", "is_business_visible"],
        )


def downgrade() -> None:
    op.drop_index(DOCUMENTS_BUSINESS_INDEX, table_name="documents")
    op.drop_index(BUSINESS_WORKSPACE_UNIQUE_INDEX, table_name="knowledge_bases")
    op.drop_column("documents", "is_business_visible")
    op.drop_column("knowledge_bases", "audience")
