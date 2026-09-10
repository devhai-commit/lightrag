"""Admin endpoints that decide what the B2B portal may serve.

Publishing is the action that exposes internal content to customers, so these
cover both the happy path and every refusal. The cross-boundary tests at the
bottom are security regression tests — do not relax them.
"""
from __future__ import annotations

from httpx import AsyncClient

from app.models.document import DocumentStatus
from app.services.business_rag import BUSINESS_AUDIENCE

AUDIENCE_URL = "/api/v1/business/admin/workspaces/{id}/audience"
PUBLISH_URL = "/api/v1/business/admin/documents/{id}/publish"
DOCUMENTS_URL = "/api/v1/business/admin/documents"


# ─── Choosing the business workspace ───────────────────────────────

async def test_set_workspace_audience_promotes_workspace_to_business(
    admin_client: AsyncClient, make_workspace
):
    workspace = await make_workspace(name="Cong khai doanh nghiep")

    response = await admin_client.put(
        AUDIENCE_URL.format(id=workspace.id), json={"audience": "business"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["audience"] == BUSINESS_AUDIENCE
    assert data["name"] == "Cong khai doanh nghiep"


async def test_set_workspace_audience_rejects_second_business_workspace(
    admin_client: AsyncClient, make_workspace
):
    """Only one workspace may serve the portal.

    Enforced twice: this application check for a clear message, and a partial
    unique index from migration 009 as the real invariant. The test database is
    built from the models via create_all, which does not carry the partial
    index, so this exercises the application check specifically.
    """
    await make_workspace(name="Da la business", audience=BUSINESS_AUDIENCE)
    other = await make_workspace(name="Ung vien thu hai")

    response = await admin_client.put(
        AUDIENCE_URL.format(id=other.id), json={"audience": "business"}
    )

    assert response.status_code == 400
    assert "Da la business" in response.json()["detail"]


async def test_set_workspace_audience_repromoting_same_workspace_succeeds(
    admin_client: AsyncClient, make_workspace
):
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)

    response = await admin_client.put(
        AUDIENCE_URL.format(id=workspace.id), json={"audience": "business"}
    )

    assert response.status_code == 200


async def test_set_workspace_audience_demote_reports_no_published_documents(
    admin_client: AsyncClient, make_workspace, make_document
):
    """Demoting stops the portal serving the workspace immediately.

    The per-document flags are intentionally left alone, so re-promoting later
    restores what was published rather than silently publishing nothing.
    """
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    await make_document(workspace_id=workspace.id, is_business_visible=True)

    response = await admin_client.put(
        AUDIENCE_URL.format(id=workspace.id), json={"audience": "internal"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["audience"] == "internal"
    assert data["published_document_count"] == 0
    assert data["document_count"] == 1


async def test_set_workspace_audience_unknown_workspace_returns_404(
    admin_client: AsyncClient,
):
    response = await admin_client.put(
        AUDIENCE_URL.format(id=999999), json={"audience": "business"}
    )

    assert response.status_code == 404


async def test_set_workspace_audience_rejects_unknown_audience_value(
    admin_client: AsyncClient, make_workspace
):
    workspace = await make_workspace(name="Cong khai")

    response = await admin_client.put(
        AUDIENCE_URL.format(id=workspace.id), json={"audience": "everyone"}
    )

    assert response.status_code == 422


# ─── Publishing a document ─────────────────────────────────────────

async def test_publish_document_marks_it_business_visible(
    admin_client: AsyncClient, make_workspace, make_document
):
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    document = await make_document(
        workspace_id=workspace.id, original_filename="Catalogue 2026.pdf"
    )

    response = await admin_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_business_visible"] is True
    assert data["label"] == "Catalogue 2026"


async def test_publish_document_not_indexed_returns_400(
    admin_client: AsyncClient, make_workspace, make_document
):
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    document = await make_document(
        workspace_id=workspace.id, status=DocumentStatus.PROCESSING
    )

    response = await admin_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )

    assert response.status_code == 400
    assert "index" in response.json()["detail"]


async def test_publish_document_not_approved_returns_400(
    admin_client: AsyncClient, make_workspace, make_document
):
    """Publishing must never bypass the internal approval gate."""
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    document = await make_document(workspace_id=workspace.id, approval_status="pending")

    response = await admin_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )

    assert response.status_code == 400


async def test_publish_document_outside_business_workspace_returns_400(
    admin_client: AsyncClient, make_workspace, make_document
):
    await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    internal = await make_workspace(name="Noi bo")
    document = await make_document(workspace_id=internal.id)

    response = await admin_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )

    assert response.status_code == 400
    assert "workspace doanh nghiệp" in response.json()["detail"]


async def test_publish_document_without_any_business_workspace_returns_400(
    admin_client: AsyncClient, make_workspace, make_document
):
    internal = await make_workspace(name="Noi bo")
    document = await make_document(workspace_id=internal.id)

    response = await admin_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )

    assert response.status_code == 400


async def test_unpublish_document_is_allowed_even_when_not_publishable(
    admin_client: AsyncClient, make_workspace, make_document
):
    """Withdrawing content must never be blocked by a validation rule."""
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    document = await make_document(
        workspace_id=workspace.id,
        is_business_visible=True,
        status=DocumentStatus.FAILED,
        approval_status="rejected",
    )

    response = await admin_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": False}
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_business_visible"] is False


async def test_publish_unknown_document_returns_404(admin_client: AsyncClient):
    response = await admin_client.put(
        PUBLISH_URL.format(id=999999), json={"is_business_visible": True}
    )

    assert response.status_code == 404


# ─── Listing what is publishable ───────────────────────────────────

async def test_list_business_documents_reports_publish_state(
    admin_client: AsyncClient, make_workspace, make_document
):
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    await make_document(
        workspace_id=workspace.id,
        original_filename="Da cong khai.pdf",
        is_business_visible=True,
    )
    await make_document(
        workspace_id=workspace.id,
        original_filename="Chua index.pdf",
        status=DocumentStatus.PROCESSING,
    )

    response = await admin_client.get(DOCUMENTS_URL)

    assert response.status_code == 200
    body = response.json()
    by_label = {doc["label"]: doc for doc in body["data"]}
    assert by_label["Da cong khai"]["is_business_visible"] is True
    assert by_label["Da cong khai"]["is_publishable"] is True
    assert by_label["Chua index"]["is_publishable"] is False
    assert body["meta"]["workspace"]["published_document_count"] == 1


async def test_list_business_documents_excludes_other_workspaces(
    admin_client: AsyncClient, make_workspace, make_document
):
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    await make_document(workspace_id=workspace.id, original_filename="Cua business.pdf")
    internal = await make_workspace(name="Noi bo")
    await make_document(workspace_id=internal.id, original_filename="Cua noi bo.pdf")

    response = await admin_client.get(DOCUMENTS_URL)

    labels = [doc["label"] for doc in response.json()["data"]]
    assert labels == ["Cua business"]


async def test_list_business_documents_without_business_workspace_returns_empty(
    admin_client: AsyncClient, make_workspace
):
    await make_workspace(name="Noi bo")

    response = await admin_client.get(DOCUMENTS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["workspace"] is None


# ─── Cross-boundary rejection ──────────────────────────────────────

async def test_business_token_rejected_on_admin_publish_endpoints(
    business_client: AsyncClient, make_workspace, make_document
):
    """A customer must not be able to publish content to themselves."""
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    document = await make_document(workspace_id=workspace.id)

    listed = await business_client.get(DOCUMENTS_URL)
    published = await business_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )
    promoted = await business_client.put(
        AUDIENCE_URL.format(id=workspace.id), json={"audience": "business"}
    )

    assert listed.status_code == 403
    assert published.status_code == 403
    assert promoted.status_code == 403
    assert "nội bộ" in listed.json()["detail"]


async def test_non_admin_internal_token_rejected_on_admin_publish_endpoints(
    internal_client: AsyncClient, make_workspace, make_document
):
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    document = await make_document(workspace_id=workspace.id)

    listed = await internal_client.get(DOCUMENTS_URL)
    published = await internal_client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )

    assert listed.status_code == 403
    assert published.status_code == 403
    assert listed.json()["detail"] == "Admin access required"


async def test_publish_endpoints_require_authentication(
    client: AsyncClient, make_workspace, make_document
):
    workspace = await make_workspace(name="Cong khai", audience=BUSINESS_AUDIENCE)
    document = await make_document(workspace_id=workspace.id)

    listed = await client.get(DOCUMENTS_URL)
    published = await client.put(
        PUBLISH_URL.format(id=document.id), json={"is_business_visible": True}
    )

    assert listed.status_code == 401  # HTTPBearer: no Authorization header
    assert published.status_code == 401
