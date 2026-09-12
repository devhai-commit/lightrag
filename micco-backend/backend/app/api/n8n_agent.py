"""n8n AI Agent tool endpoints — email-reply flow for pending documents.

Independent of app.api.documents.approval_callback: these endpoints never
touch approval_status. They let an n8n AI Agent (1) read a pending
document's raw text and (2) render its generated answer as a PDF to attach
to the reply email. Authenticated the same way as approval-callback: a
shared secret in X-Webhook-Secret (see app.core.deps.verify_n8n_webhook_secret).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import UPLOAD_DIR
from app.core.deps import get_db, verify_n8n_webhook_secret
from app.core.exceptions import ConflictError, NotFoundError
from app.models.document import Document, DocumentStatus
from app.services.document_text_extractor import extract_full_text

router = APIRouter(prefix="/documents", tags=["n8n-agent"])


@router.get(
    "/{document_id}/agent-content",
    dependencies=[Depends(verify_n8n_webhook_secret)],
)
async def get_agent_content(document_id: int, db: AsyncSession = Depends(get_db)):
    """Raw text of a PENDING document, for the n8n AI Agent to reason over."""
    document = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document", document_id)

    if document.status != DocumentStatus.PENDING:
        raise ConflictError("Document is no longer pending")

    file_path = UPLOAD_DIR / document.filename
    if not file_path.exists():
        raise NotFoundError("Document file", document_id)

    extracted = await extract_full_text(file_path, document.file_type)

    return {
        "id": document.id,
        "filename": document.original_filename,
        "file_type": document.file_type,
        "supported": extracted.supported,
        "content": extracted.content,
        "truncated": extracted.truncated,
        "message": None if extracted.supported else "Preview not supported for this file type",
    }
