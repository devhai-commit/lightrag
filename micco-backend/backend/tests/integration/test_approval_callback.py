"""n8n's approval-email callback: approve -> ingest, deny -> stop, no forgeries.

This endpoint has no user JWT — it is authenticated solely by a shared secret
in the X-Webhook-Secret header, so the auth-failure cases here are security
regression tests. Ingestion itself is mocked; app/services/rag_service.py has
its own tests.
"""
from __future__ import annotations

from httpx import AsyncClient

import app.api.documents as documents_module
from app.models.document import DocumentStatus

CALLBACK_URL = "/api/v1/documents/{document_id}/approval-callback"
SECRET = "test-n8n-secret"


class _RecordingIngest:
    def __init__(self):
        self.calls: list[tuple[int, str, int]] = []

    async def __call__(self, document_id: int, file_path: str, workspace_id: int) -> None:
        self.calls.append((document_id, file_path, workspace_id))


def _configure_secret(monkeypatch, secret: str | None = SECRET):
    monkeypatch.setattr(documents_module.settings, "N8N_CALLBACK_SECRET", secret or "")


def _mock_ingest(monkeypatch) -> _RecordingIngest:
    recorder = _RecordingIngest()
    monkeypatch.setattr(documents_module, "process_document_background", recorder)
    return recorder


async def test_approval_callback_rejects_missing_secret_header(
    client: AsyncClient, make_workspace, make_document, monkeypatch
):
    _configure_secret(monkeypatch)
    workspace = await make_workspace()
    doc = await make_document(workspace_id=workspace.id, status=DocumentStatus.PENDING)

    response = await client.post(
        CALLBACK_URL.format(document_id=doc.id), json={"approved": True}
    )

    assert response.status_code == 401


async def test_approval_callback_rejects_wrong_secret(
    client: AsyncClient, make_workspace, make_document, monkeypatch
):
    _configure_secret(monkeypatch)
    workspace = await make_workspace()
    doc = await make_document(workspace_id=workspace.id, status=DocumentStatus.PENDING)

    response = await client.post(
        CALLBACK_URL.format(document_id=doc.id),
        json={"approved": True},
        headers={"X-Webhook-Secret": "not-the-secret"},
    )

    assert response.status_code == 401


async def test_approval_callback_rejects_when_secret_not_configured(
    client: AsyncClient, make_workspace, make_document, monkeypatch
):
    """An empty N8N_CALLBACK_SECRET must never act as a wildcard match."""
    _configure_secret(monkeypatch, secret="")
    workspace = await make_workspace()
    doc = await make_document(workspace_id=workspace.id, status=DocumentStatus.PENDING)

    response = await client.post(
        CALLBACK_URL.format(document_id=doc.id),
        json={"approved": True},
        headers={"X-Webhook-Secret": ""},
    )

    assert response.status_code == 401


async def test_approval_callback_404_for_unknown_document(client: AsyncClient, monkeypatch):
    _configure_secret(monkeypatch)

    response = await client.post(
        CALLBACK_URL.format(document_id=999999),
        json={"approved": True},
        headers={"X-Webhook-Secret": SECRET},
    )

    assert response.status_code == 404


async def test_approval_callback_approved_triggers_ingest(
    client: AsyncClient, make_workspace, make_document, monkeypatch, test_db
):
    _configure_secret(monkeypatch)
    recorder = _mock_ingest(monkeypatch)
    workspace = await make_workspace()
    doc = await make_document(workspace_id=workspace.id, status=DocumentStatus.PENDING, approval_status="pending")

    response = await client.post(
        CALLBACK_URL.format(document_id=doc.id),
        json={"approved": True},
        headers={"X-Webhook-Secret": SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "approved"
    assert len(recorder.calls) == 1
    ingested_document_id, _file_path, _workspace_id = recorder.calls[0]
    assert ingested_document_id == doc.id

    await test_db.refresh(doc)
    assert doc.approval_status == "approved"
    assert doc.status == DocumentStatus.PROCESSING


async def test_approval_callback_denied_marks_rejected_without_ingest(
    client: AsyncClient, make_workspace, make_document, monkeypatch, test_db
):
    _configure_secret(monkeypatch)
    recorder = _mock_ingest(monkeypatch)
    workspace = await make_workspace()
    doc = await make_document(workspace_id=workspace.id, status=DocumentStatus.PENDING, approval_status="pending")

    response = await client.post(
        CALLBACK_URL.format(document_id=doc.id),
        json={"approved": False, "note": "Khong dung dinh dang"},
        headers={"X-Webhook-Secret": SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "rejected"
    assert recorder.calls == []

    await test_db.refresh(doc)
    assert doc.approval_status == "rejected"
    assert doc.status == DocumentStatus.REJECTED
    assert doc.approval_note == "Khong dung dinh dang"


async def test_approval_callback_is_idempotent_on_retry(
    client: AsyncClient, make_workspace, make_document, monkeypatch
):
    """A second n8n delivery of the same callback must not re-trigger ingestion."""
    _configure_secret(monkeypatch)
    recorder = _mock_ingest(monkeypatch)
    workspace = await make_workspace()
    doc = await make_document(workspace_id=workspace.id, status=DocumentStatus.PENDING, approval_status="pending")

    headers = {"X-Webhook-Secret": SECRET}
    first = await client.post(
        CALLBACK_URL.format(document_id=doc.id), json={"approved": True}, headers=headers
    )
    second = await client.post(
        CALLBACK_URL.format(document_id=doc.id), json={"approved": True}, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "already finalized" in second.json()["message"]
    assert len(recorder.calls) == 1


async def test_finalize_approval_and_ingest_is_race_safe(
    make_workspace, make_document, monkeypatch, test_db
):
    """The PENDING -> PROCESSING transition is a single conditional UPDATE.

    Simulates two callbacks racing on the same document by invoking the shared
    helper twice back-to-back on a document still loaded as PENDING in memory:
    only the first should win and enqueue ingestion.
    """
    from fastapi import BackgroundTasks

    recorder = _mock_ingest(monkeypatch)
    workspace = await make_workspace()
    doc = await make_document(workspace_id=workspace.id, status=DocumentStatus.PENDING, approval_status="pending")

    bg1, bg2 = BackgroundTasks(), BackgroundTasks()
    first_ws = await documents_module._finalize_approval_and_ingest(test_db, doc, bg1)
    second_ws = await documents_module._finalize_approval_and_ingest(test_db, doc, bg2)

    assert first_ws is not None
    assert second_ws is None
    assert len(recorder.calls) == 0  # BackgroundTasks weren't run yet, just enqueued
    assert len(bg1.tasks) == 1
    assert len(bg2.tasks) == 0
