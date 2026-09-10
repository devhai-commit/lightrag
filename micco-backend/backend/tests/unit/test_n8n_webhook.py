"""Unit tests for the outbound n8n document-upload webhook.

External HTTP calls (httpx) and the DB session factory are mocked per
.claude/rules/testing.md — this module never opens a real DB connection.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.services import n8n_webhook
from app.models.document import Document, DocumentStatus
from app.models.user import User


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    """Dispatches select(Document)/select(User) to the staged fixtures."""

    def __init__(self, document=None, user=None):
        self._document = document
        self._user = user

    async def execute(self, stmt):
        target = stmt.column_descriptions[0]["type"]
        if target is Document:
            return _FakeResult(self._document)
        if target is User:
            return _FakeResult(self._user)
        return _FakeResult(None)


class _FakeSessionCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.test/webhook")
            raise httpx.HTTPStatusError("boom", request=request, response=self)


class _FakeAsyncClient:
    last_instance: "_FakeAsyncClient | None" = None

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")
        self.posted: list[tuple[str, dict]] = []
        self.response = _FakeResponse()
        _FakeAsyncClient.last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        self.posted.append((url, json))
        return self.response


def _fake_document(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=42,
        original_filename="report.pdf",
        file_type="pdf",
        file_size=1024,
        status=DocumentStatus.PENDING,
        workspace_id=1,
        department_id=2,
        visibility="internal",
        approval_status="pending",
        created_at=None,
        uploader_id=7,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_user(**overrides) -> SimpleNamespace:
    defaults = dict(id=7, name="Nguyen Van A", email="a@example.test")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _patch_http_client(monkeypatch):
    monkeypatch.setattr(n8n_webhook.httpx, "AsyncClient", _FakeAsyncClient)
    yield
    _FakeAsyncClient.last_instance = None


def _patch_db(monkeypatch, document=None, user=None):
    fake_db = _FakeDb(document=document, user=user)
    monkeypatch.setattr(
        "app.core.database.async_session_maker", lambda: _FakeSessionCM(fake_db)
    )
    return fake_db


async def test_notify_document_uploaded_noop_when_url_not_configured(monkeypatch):
    monkeypatch.setattr(n8n_webhook.settings, "N8N_WEBHOOK_URL", "")

    await n8n_webhook.notify_document_uploaded(42)

    assert _FakeAsyncClient.last_instance is None


async def test_notify_document_uploaded_skips_when_document_missing(monkeypatch):
    monkeypatch.setattr(n8n_webhook.settings, "N8N_WEBHOOK_URL", "https://example.test/webhook")
    _patch_db(monkeypatch, document=None, user=None)

    await n8n_webhook.notify_document_uploaded(999)

    assert _FakeAsyncClient.last_instance is None


async def test_notify_document_uploaded_posts_expected_payload(monkeypatch):
    monkeypatch.setattr(n8n_webhook.settings, "N8N_WEBHOOK_URL", "https://example.test/webhook")
    document = _fake_document()
    user = _fake_user()
    _patch_db(monkeypatch, document=document, user=user)

    await n8n_webhook.notify_document_uploaded(document.id)

    client = _FakeAsyncClient.last_instance
    assert client is not None
    assert len(client.posted) == 1
    url, payload = client.posted[0]
    assert url == "https://example.test/webhook"
    assert payload["event"] == "document.uploaded"
    assert payload["document"]["id"] == document.id
    assert payload["document"]["status"] == "pending"
    assert payload["document"]["approval_status"] == "pending"
    assert payload["uploader"] == {"id": user.id, "name": user.name, "email": user.email}


async def test_notify_document_uploaded_omits_uploader_when_none(monkeypatch):
    monkeypatch.setattr(n8n_webhook.settings, "N8N_WEBHOOK_URL", "https://example.test/webhook")
    document = _fake_document(uploader_id=None)
    _patch_db(monkeypatch, document=document, user=None)

    await n8n_webhook.notify_document_uploaded(document.id)

    _, payload = _FakeAsyncClient.last_instance.posted[0]
    assert payload["uploader"] is None


async def test_notify_document_uploaded_swallows_http_errors(monkeypatch):
    monkeypatch.setattr(n8n_webhook.settings, "N8N_WEBHOOK_URL", "https://example.test/webhook")
    document = _fake_document()
    _patch_db(monkeypatch, document=document, user=None)

    class _FailingClient(_FakeAsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.response = _FakeResponse(status_code=500)

    monkeypatch.setattr(n8n_webhook.httpx, "AsyncClient", _FailingClient)

    # Must not raise even though the webhook responds with an error.
    await n8n_webhook.notify_document_uploaded(document.id)
