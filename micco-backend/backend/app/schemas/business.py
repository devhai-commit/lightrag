"""Schemas for the external B2B portal (/api/v1/business/...).

This surface follows the response envelope documented in
.claude/rules/api-design.md: {"data": ..., "meta": {...}}.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

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
