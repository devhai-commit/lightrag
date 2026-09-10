"""Upload should schedule the n8n notification as a background task.

The actual HTTP call to n8n (and its own error handling) is covered in
tests/unit/test_n8n_webhook.py; here we only verify the upload endpoint wires
it in with the right document id.
"""
from __future__ import annotations

from httpx import AsyncClient

import app.api.documents as documents_module

UPLOAD_URL = "/api/v1/documents/upload/{workspace_id}"


class _RecordingNotifier:
    def __init__(self):
        self.calls: list[int] = []

    async def __call__(self, document_id: int) -> None:
        self.calls.append(document_id)


async def test_upload_document_schedules_n8n_notification(
    internal_client: AsyncClient, make_workspace, monkeypatch
):
    workspace = await make_workspace(name="KB Notify Test")
    notifier = _RecordingNotifier()
    monkeypatch.setattr(documents_module, "notify_document_uploaded", notifier)

    response = await internal_client.post(
        UPLOAD_URL.format(workspace_id=workspace.id),
        files={"file": ("bao_cao.txt", b"noi dung tai lieu", "text/plain")},
    )

    assert response.status_code == 200
    document_id = response.json()["id"]
    assert notifier.calls == [document_id]
