"""External B2B portal API (/api/v1/business/...).

Kept in its own module on purpose: every endpoint here is reachable by
customers, so the whole external surface stays reviewable in one place. It must
never depend on the internal document-scoping helpers in app.api.rag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_deps import (
    BUSINESS_TOKEN_SCOPE,
    assert_business_account_active,
    assert_is_business_account,
    get_current_business_user,
)
from app.core.deps import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.business import (
    BusinessEnvelope,
    BusinessLoginData,
    BusinessLoginRequest,
    BusinessProfile,
)

router = APIRouter(prefix="/business", tags=["Business Portal"])


def _to_profile(user: User) -> BusinessProfile:
    return BusinessProfile(
        id=user.id,
        company_name=user.company_name,
        contact_name=user.name,
        email=user.email,
        phone=user.phone,
        industry=user.industry,
        tax_code=user.tax_code,
        approval_status=user.approval_status,
    )


@router.post("/auth/login", response_model=BusinessEnvelope[BusinessLoginData])
async def business_login(
    req: BusinessLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Portal login for external business accounts."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không đúng",
        )

    assert_is_business_account(user)
    assert_business_account_active(user)

    token = create_access_token(data={"sub": user.id, "scope": BUSINESS_TOKEN_SCOPE})
    return BusinessEnvelope(
        data=BusinessLoginData(access_token=token, user=_to_profile(user)),
    )


@router.get("/me", response_model=BusinessEnvelope[BusinessProfile])
async def business_me(current_user: User = Depends(get_current_business_user)):
    return BusinessEnvelope(data=_to_profile(current_user))
