"""Auth boundary for the external B2B portal.

Everything that identifies a customer principal lives in this one file so the
whole externally-reachable auth surface can be reviewed in a single place.
Internal (staff) auth stays in app.core.security.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import BUSINESS_ROLE, decode_access_token, security
from app.models.user import User

# Custom claim marking a token as issued by the business portal login.
# Not the standard `aud` claim: decode_access_token() calls jwt.decode() without
# an audience argument, and python-jose validates `aud` whenever it is present,
# so an `aud` claim would make every business token fail to decode.
BUSINESS_TOKEN_SCOPE = "business"

_PENDING_DETAIL = "Tài khoản đang chờ duyệt. Vui lòng quay lại sau."
_NOT_APPROVED_DETAIL = "Tài khoản không được duyệt. Liên hệ Micco để biết thêm chi tiết."
_NOT_A_BUSINESS_ACCOUNT_DETAIL = (
    "Tài khoản này không phải tài khoản doanh nghiệp. Vui lòng đăng nhập tại cổng nội bộ."
)
_INVALID_TOKEN_DETAIL = "Invalid or expired token"


def assert_business_account_active(user: User) -> None:
    """Block a business account an Admin has not approved.

    Shared by both login entrances so the internal gate and the portal gate
    cannot drift apart. Default-deny: only an explicit "approved" passes.
    """
    if user.role != BUSINESS_ROLE:
        return
    if user.approval_status == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_PENDING_DETAIL)
    if user.approval_status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NOT_APPROVED_DETAIL)


def assert_is_business_account(user: User) -> None:
    if user.role != BUSINESS_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_NOT_A_BUSINESS_ACCOUNT_DETAIL,
        )


async def get_current_business_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials

    # The dev-skip bypass in get_current_user hands out an internal Admin.
    # It must never open a customer-facing endpoint, in any environment.
    if token == "dev-skip":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if payload.get("scope") != BUSINESS_TOKEN_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_NOT_A_BUSINESS_ACCOUNT_DETAIL,
        )

    try:
        user_id = int(payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    assert_is_business_account(user)
    # Re-checked per request, so revoking approval takes effect immediately
    # instead of waiting out the token TTL (24h by default).
    assert_business_account_active(user)
    return user
