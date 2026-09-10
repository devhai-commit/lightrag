"""add_business_packages — catalogue the offers the portal may suggest

Revision ID: 010_add_business_packages
Revises: 009_add_business_audience
Create Date: 2026-09-08

Adds:

- business_packages: the offers a customer may be pointed at when their need is
  still broad. Deliberately a flat list with a `category` string rather than a
  category tree — nothing needs a hierarchy yet, and a tree would have to be
  flattened again for the prompt digest.
  `price_note` is free text, not a number, because real prices at Micco are
  negotiated; a numeric column would invite the portal to quote a figure it has
  no authority to quote.
  `is_active` rather than deleting rows, so an offer can be withdrawn from the
  portal without losing the packages already referenced by past conversations.
  `document_id` is a nullable FK so an offer can point at the published document
  that describes it, and survives that document being deleted.

- chat_messages.recommended_packages: which packages were suggested on an
  assistant turn, so the cards survive a history reload instead of vanishing
  the moment the stream ends.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010_add_business_packages"
down_revision: Union[str, None] = "009_add_business_audience"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PACKAGES_TABLE = "business_packages"
ACTIVE_SORT_INDEX = "ix_business_packages_active_sort"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if PACKAGES_TABLE not in insp.get_table_names():
        op.create_table(
            PACKAGES_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=100), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("target_customer", sa.Text(), nullable=True),
            sa.Column("highlights", sa.JSON(), nullable=True),
            sa.Column("price_note", sa.Text(), nullable=True),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "document_id",
                sa.Integer(),
                sa.ForeignKey("documents.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    pkg_indexes = {i["name"] for i in insp.get_indexes(PACKAGES_TABLE)} \
        if PACKAGES_TABLE in insp.get_table_names() else set()
    if ACTIVE_SORT_INDEX not in pkg_indexes:
        # Covers the only read path: the active catalogue in display order.
        op.create_index(ACTIVE_SORT_INDEX, PACKAGES_TABLE, ["is_active", "sort_order"])

    chat_columns = {c["name"] for c in insp.get_columns("chat_messages")}
    if "recommended_packages" not in chat_columns:
        op.add_column(
            "chat_messages",
            sa.Column("recommended_packages", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("chat_messages", "recommended_packages")
    op.drop_index(ACTIVE_SORT_INDEX, table_name=PACKAGES_TABLE)
    op.drop_table(PACKAGES_TABLE)
