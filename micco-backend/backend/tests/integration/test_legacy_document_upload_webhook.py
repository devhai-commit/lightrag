"""The legacy /api/documents/upload endpoint must also notify n8n on upload.

This is the endpoint the frontend actually calls (app.api_compat.documents,
mounted at /api/documents, distinct from /api/v1/documents/upload/{workspace_id}
in app.api.documents). It is not mounted on the shared `test_app` fixture, so
tests here build a slim app of their own, mirroring
tests/integration/test_approvals_document.py.
"""
from __future__ import annotations

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.api_compat.documents as legacy_documents_module
from app.core.deps import get_db
from app.core.security import create_access_token

UPLOAD_URL = "/api/documents/upload"


@pytest_asyncio.fixture
async def legacy_documents_client(test_db: AsyncSession) -> AsyncClient:
    from app.api_compat.documents import router as documents_router

    application = FastAPI()
    application.include_router(documents_router)

    async def _override_get_db():
        yield test_db

    application.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as async_client:
        yield async_client


class _RecordingNotifier:
    def __init__(self):
        self.calls: list[int] = []

    async def __call__(self, document_id: int) -> None:
        self.calls.append(document_id)


async def test_legacy_upload_schedules_n8n_notification_for_pending_document(
    legacy_documents_client: AsyncClient, internal_user, monkeypatch
):
    """A regular employee's upload needs approval, so it stays PENDING."""
    notifier = _RecordingNotifier()
    monkeypatch.setattr(legacy_documents_module, "notify_document_uploaded", notifier)

    token = create_access_token(data={"sub": internal_user.id})
    legacy_documents_client.headers.update({"Authorization": f"Bearer {token}"})

    response = await legacy_documents_client.post(
        UPLOAD_URL,
        files={"files": ("bao_cao.txt", b"noi dung tai lieu", "text/plain")},
    )

    assert response.status_code == 200
    document_id = response.json()[0]["id"]
    assert notifier.calls == [document_id]


async def test_legacy_upload_rejects_batches_over_the_file_cap(
    legacy_documents_client: AsyncClient, internal_user, monkeypatch
):
    """A single request can't fan out an unbounded number of webhook calls."""
    notifier = _RecordingNotifier()
    monkeypatch.setattr(legacy_documents_module, "notify_document_uploaded", notifier)

    token = create_access_token(data={"sub": internal_user.id})
    legacy_documents_client.headers.update({"Authorization": f"Bearer {token}"})

    too_many = legacy_documents_module.MAX_FILES_PER_UPLOAD + 1
    files = [
        ("files", (f"bao_cao_{i}.txt", b"noi dung", "text/plain")) for i in range(too_many)
    ]

    response = await legacy_documents_client.post(UPLOAD_URL, files=files)

    assert response.status_code == 400
    assert notifier.calls == []


async def test_legacy_upload_schedules_n8n_notification_for_auto_approved_document(
    legacy_documents_client: AsyncClient, admin_user, monkeypatch
):
    """Admin uploads are auto-approved and skip straight to PROCESSING, but
    should still raise the document.uploaded notification."""
    notifier = _RecordingNotifier()
    monkeypatch.setattr(legacy_documents_module, "notify_document_uploaded", notifier)

    token = create_access_token(data={"sub": admin_user.id})
    legacy_documents_client.headers.update({"Authorization": f"Bearer {token}"})

    response = await legacy_documents_client.post(
        UPLOAD_URL,
        files={"files": ("bao_cao.txt", b"noi dung tai lieu", "text/plain")},
    )

    assert response.status_code == 200
    document_id = response.json()[0]["id"]
    assert notifier.calls == [document_id]
