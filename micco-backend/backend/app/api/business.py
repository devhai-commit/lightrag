"""External B2B portal API (/api/v1/business/...).

Kept in its own module on purpose: every endpoint here is reachable by
customers, so the whole external surface stays reviewable in one place. It must
never depend on the internal document-scoping helpers in app.api.rag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_deps import (
    BUSINESS_TOKEN_SCOPE,
    assert_business_account_active,
    assert_is_business_account,
    get_current_business_user,
)
from app.core.deps import get_db
from app.core.security import create_access_token, require_admin, verify_password
from app.models.document import Document, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.business import (
    BusinessDocumentSummary,
    BusinessEnvelope,
    BusinessLoginData,
    BusinessLoginRequest,
    BusinessProfile,
    BusinessWorkspaceSummary,
    DocumentPublishRequest,
    WorkspaceAudienceRequest,
)
from app.services.business_rag import (
    BUSINESS_AUDIENCE,
    get_business_document_ids,
    get_business_workspace,
    to_document_label,
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


# ─── Admin: publishing content to the portal ───────────────────────
# Staff-only. get_current_user (behind require_admin) already rejects business
# accounts, so a customer token cannot reach any of these.

_PUBLISH_REQUIREMENTS_DETAIL = (
    "Chỉ có thể công khai tài liệu đã được duyệt và đã index xong."
)


def _is_publishable(document: Document) -> bool:
    """Whether a document may be exposed to customers.

    Mirrors two of the four conditions in get_business_document_ids; the other
    two (workspace and the flag itself) are properties of where it lives and
    what the Admin decided.
    """
    return (
        document.status == DocumentStatus.INDEXED
        and document.approval_status == "approved"
    )


@router.put(
    "/admin/workspaces/{workspace_id}/audience",
    response_model=BusinessEnvelope[BusinessWorkspaceSummary],
)
async def set_workspace_audience(
    workspace_id: int,
    req: WorkspaceAudienceRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Promote a workspace to serve the portal, or demote it back to internal.

    Demoting stops the portal serving it immediately, but leaves each
    document's is_business_visible flag alone, so a later re-promotion restores
    exactly what was published before rather than silently publishing nothing.
    """
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace không tồn tại")

    if req.audience == BUSINESS_AUDIENCE:
        existing = await get_business_workspace(db)
        if existing is not None and existing.id != workspace.id:
            # Belt to the partial unique index from migration 009, so the
            # caller gets a clear message instead of an IntegrityError.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Workspace '{existing.name}' đang là workspace doanh nghiệp. "
                    "Chuyển workspace đó về nội bộ trước."
                ),
            )

    workspace.audience = req.audience
    await db.commit()
    await db.refresh(workspace)

    return BusinessEnvelope(data=await _to_workspace_summary(db, workspace))


@router.get(
    "/admin/documents",
    response_model=BusinessEnvelope[list[BusinessDocumentSummary]],
)
async def list_business_documents(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Documents in the business workspace, with their publish state.

    Returns an empty list (not a 404) when no workspace serves the portal yet,
    so the admin UI can render the "not configured" state from meta.
    """
    workspace = await get_business_workspace(db)
    if workspace is None:
        return BusinessEnvelope(data=[], meta={"workspace": None})

    result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace.id)
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()

    return BusinessEnvelope(
        data=[_to_document_summary(doc) for doc in documents],
        meta={"workspace": (await _to_workspace_summary(db, workspace)).model_dump()},
    )


@router.put(
    "/admin/documents/{document_id}/publish",
    response_model=BusinessEnvelope[BusinessDocumentSummary],
)
async def set_document_published(
    document_id: int,
    req: DocumentPublishRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Publish or unpublish one document to the portal.

    Publishing requires the document to be INDEXED and internally approved, so
    it can never bypass the normal review gate. Unpublishing is always allowed:
    withdrawing content must never be blocked by a validation rule.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài liệu không tồn tại")

    if req.is_business_visible:
        workspace = await get_business_workspace(db)
        if workspace is None or document.workspace_id != workspace.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tài liệu không nằm trong workspace doanh nghiệp.",
            )
        if not _is_publishable(document):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_PUBLISH_REQUIREMENTS_DETAIL,
            )

    document.is_business_visible = req.is_business_visible
    await db.commit()
    await db.refresh(document)

    return BusinessEnvelope(data=_to_document_summary(document))


def _to_document_summary(document: Document) -> BusinessDocumentSummary:
    return BusinessDocumentSummary(
        id=document.id,
        label=to_document_label(document.original_filename),
        original_filename=document.original_filename,
        status=document.status.value if document.status else "",
        approval_status=document.approval_status,
        is_business_visible=document.is_business_visible,
        is_publishable=_is_publishable(document),
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
    )


async def _to_workspace_summary(
    db: AsyncSession, workspace: KnowledgeBase
) -> BusinessWorkspaceSummary:
    total = await db.scalar(
        select(func.count(Document.id)).where(Document.workspace_id == workspace.id)
    )
    published = (
        len(await get_business_document_ids(db, workspace.id))
        if workspace.audience == BUSINESS_AUDIENCE
        else 0
    )
    return BusinessWorkspaceSummary(
        id=workspace.id,
        name=workspace.name,
        audience=workspace.audience,
        document_count=total or 0,
        published_document_count=published,
    )
