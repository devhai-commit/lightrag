"""Schemas for the external B2B portal (/api/v1/business/...).

This surface follows the response envelope documented in
.claude/rules/api-design.md: {"data": ..., "meta": {...}}.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class BusinessEnvelope(BaseModel, Generic[DataT]):
    data: DataT
    meta: dict[str, Any] = Field(default_factory=dict)


class BusinessLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=200)


class BusinessProfile(BaseModel):
    id: int
    company_name: str | None = None
    contact_name: str
    email: str
    phone: str | None = None
    industry: str | None = None
    tax_code: str | None = None
    approval_status: str | None = None


class BusinessLoginData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: BusinessProfile


# ─── Admin: publishing content to the portal ───────────────────────
# These are staff-only (require_admin). They shape what the portal can serve,
# so they live beside the customer schemas they govern.


class WorkspaceAudienceRequest(BaseModel):
    audience: Literal["internal", "business"]


class BusinessWorkspaceSummary(BaseModel):
    id: int
    name: str
    audience: str
    document_count: int = 0
    published_document_count: int = 0


class DocumentPublishRequest(BaseModel):
    is_business_visible: bool


class BusinessDocumentSummary(BaseModel):
    """A document in the business workspace, from the Admin's point of view."""

    id: int
    label: str
    original_filename: str
    status: str
    approval_status: str
    is_business_visible: bool
    is_publishable: bool
    page_count: int = 0
    chunk_count: int = 0
    created_at: datetime | None = None
