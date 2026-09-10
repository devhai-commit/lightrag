"""
BusinessPackage model — the offers the B2B portal may suggest to a customer.

Read by app.services.business_packages, which is the only place that decides
which rows reach a prompt or a customer. Nothing here is customer-facing on its
own: the portal serves a projection (see BusinessPackageCard), never the row.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BusinessPackage(Base):
    __tablename__ = "business_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Who the offer is for. Drives the match when a customer describes their
    # work rather than naming a product.
    target_customer: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Short bullet points for the card. List of strings.
    highlights: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Free text on purpose, never a number: real prices are negotiated, and the
    # portal has no authority to quote a figure.
    price_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Withdrawn offers are deactivated rather than deleted, so packages already
    # referenced by past conversations keep resolving.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Optional link to the published document describing this offer.
    document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
