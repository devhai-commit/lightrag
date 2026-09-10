"""Outbound notification to the n8n approval-email workflow.

Called as a FastAPI BackgroundTasks target right after a document upload is
committed. Best-effort: any failure is logged and swallowed so it never
affects the upload response, and a missing N8N_WEBHOOK_URL makes the call a
no-op (n8n integration is optional).
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 5.0


async def notify_document_uploaded(document_id: int) -> None:
    """Post a document.uploaded event to the configured n8n webhook."""
    if not settings.N8N_WEBHOOK_URL:
        return

    try:
        from sqlalchemy import select

        from app.core.database import async_session_maker
        from app.models.document import Document
        from app.models.user import User

        async with async_session_maker() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document is None:
                logger.warning(f"n8n webhook: document {document_id} not found, skipping notify")
                return

            uploader = None
            if document.uploader_id:
                uploader_result = await db.execute(select(User).where(User.id == document.uploader_id))
                uploader = uploader_result.scalar_one_or_none()

            payload = {
                "event": "document.uploaded",
                "document": {
                    "id": document.id,
                    "filename": document.original_filename,
                    "file_type": document.file_type,
                    "file_size": document.file_size,
                    "status": document.status.value if hasattr(document.status, "value") else document.status,
                    "workspace_id": document.workspace_id,
                    "department_id": document.department_id,
                    "visibility": document.visibility,
                    "created_at": document.created_at.isoformat() if document.created_at else None,
                },
                "uploader": {
                    "id": uploader.id,
                    "name": uploader.name,
                    "email": uploader.email,
                } if uploader else None,
            }

        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(settings.N8N_WEBHOOK_URL, json=payload)
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"n8n webhook call failed for document {document_id}: {e}")
