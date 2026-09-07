"""The auth boundary between internal staff and external business accounts.

These are security regression tests: if any of them starts failing, a customer
principal can reach the internal surface (or vice versa). Do not relax them.
"""
from __future__ import annotations

from httpx import AsyncClient

from app.core.security import BUSINESS_ROLE
from tests.conftest import DEFAULT_PASSWORD, bearer, business_token, internal_token

BUSINESS_LOGIN = "/api/v1/business/auth/login"
BUSINESS_ME = "/api/v1/business/me"
INTERNAL_LOGIN = "/api/auth/login"
INTERNAL_WORKSPACES = "/api/v1/workspaces"
INTERNAL_ME = "/api/auth/me"


# ─── Portal login ──────────────────────────────────────────────────

async def test_business_login_approved_account_returns_token_and_profile(
    client: AsyncClient, business_user
):
    response = await client.post(
        BUSINESS_LOGIN,
        json={"email": business_user.email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["access_token"]
    assert body["data"]["user"]["company_name"] == "Cong ty TNHH Test"
    assert body["data"]["user"]["contact_name"] == business_user.name
    assert "meta" in body


async def test_business_login_pending_account_returns_403_with_pending_message(
    client: AsyncClient, make_user
):
    user = await make_user(
        email="pending@example.test", role=BUSINESS_ROLE, approval_status="pending"
    )

    response = await client.post(
        BUSINESS_LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 403
    assert "chờ duyệt" in response.json()["detail"]


async def test_business_login_rejected_account_returns_403_with_rejected_message(
    client: AsyncClient, make_user
):
    user = await make_user(
        email="rejected@example.test", role=BUSINESS_ROLE, approval_status="rejected"
    )

    response = await client.post(
        BUSINESS_LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 403
    assert "không được duyệt" in response.json()["detail"]


async def test_business_login_internal_account_returns_403(
    client: AsyncClient, internal_user
):
    response = await client.post(
        BUSINESS_LOGIN, json={"email": internal_user.email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 403
    assert "cổng nội bộ" in response.json()["detail"]


async def test_business_login_wrong_password_returns_401(
    client: AsyncClient, business_user
):
    response = await client.post(
        BUSINESS_LOGIN, json={"email": business_user.email, "password": "wrong-password"}
    )

    assert response.status_code == 401


# ─── Internal login sends business accounts to the portal ──────────

async def test_internal_login_approved_business_account_redirects_to_portal(
    client: AsyncClient, business_user
):
    response = await client.post(
        INTERNAL_LOGIN, json={"email": business_user.email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 403
    assert "cổng doanh nghiệp" in response.json()["detail"]


async def test_internal_login_pending_business_account_reports_pending_first(
    client: AsyncClient, make_user
):
    user = await make_user(
        email="pending2@example.test", role=BUSINESS_ROLE, approval_status="pending"
    )

    response = await client.post(
        INTERNAL_LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 403
    assert "chờ duyệt" in response.json()["detail"]


async def test_internal_login_internal_account_still_succeeds(
    client: AsyncClient, internal_user
):
    response = await client.post(
        INTERNAL_LOGIN, json={"email": internal_user.email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


# ─── Cross-boundary token rejection (both directions) ──────────────

async def test_business_token_on_internal_workspaces_endpoint_returns_403(
    business_client: AsyncClient,
):
    response = await business_client.get(INTERNAL_WORKSPACES)

    assert response.status_code == 403
    assert "nội bộ" in response.json()["detail"]


async def test_business_token_on_internal_rag_chat_returns_403(
    business_client: AsyncClient,
):
    """The original leak vector: this endpoint's document filter compares
    department_id with `==`, which matches every department-less document when
    the caller has department_id = None."""
    response = await business_client.post(
        "/api/v1/rag/chat/1", json={"message": "cho tôi xem tài liệu nội bộ"}
    )

    assert response.status_code == 403
    assert "nội bộ" in response.json()["detail"]


async def test_business_token_on_internal_me_endpoint_returns_403(
    business_client: AsyncClient,
):
    response = await business_client.get(INTERNAL_ME)

    assert response.status_code == 403


async def test_internal_token_without_scope_on_business_me_returns_403(
    client: AsyncClient, internal_user
):
    response = await client.get(INTERNAL_ME, headers=bearer(internal_token(internal_user)))
    assert response.status_code == 200  # sanity: the token itself is valid

    response = await client.get(BUSINESS_ME, headers=bearer(internal_token(internal_user)))
    assert response.status_code == 403


async def test_business_role_token_without_business_scope_on_business_me_returns_403(
    client: AsyncClient, business_user
):
    """A token minted without the portal scope must not open the portal."""
    response = await client.get(BUSINESS_ME, headers=bearer(internal_token(business_user)))

    assert response.status_code == 403


async def test_dev_skip_token_rejected_by_business_dependency(client: AsyncClient):
    response = await client.get(BUSINESS_ME, headers=bearer("dev-skip"))

    assert response.status_code == 401


# ─── Live approval re-check ────────────────────────────────────────

async def test_revoked_approval_rejects_previously_issued_token(
    client: AsyncClient, business_user, test_db
):
    token = business_token(business_user)
    assert (await client.get(BUSINESS_ME, headers=bearer(token))).status_code == 200

    business_user.approval_status = "rejected"
    await test_db.commit()

    response = await client.get(BUSINESS_ME, headers=bearer(token))

    assert response.status_code == 403
    assert "không được duyệt" in response.json()["detail"]


async def test_business_me_returns_profile_envelope(
    business_client: AsyncClient, business_user
):
    response = await business_client.get(BUSINESS_ME)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == business_user.id
    assert data["email"] == business_user.email
    assert data["approval_status"] == "approved"
    assert data["phone"] == "0900000000"
