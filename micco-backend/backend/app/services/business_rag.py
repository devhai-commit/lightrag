"""Retrieval for the external B2B portal.

This module is the only place that decides what an external customer may read.
It is written to be narrow on purpose, and it deliberately does NOT reuse the
internal helpers:

- ``app.api.rag.get_allowed_document_ids`` widens its result based on the
  caller's identity (``or_(visibility == 'public', department_id == user.
  department_id)``), and an external account has ``department_id = None``,
  which SQL renders as ``IS NULL`` — it would match every department-less
  internal document.
- ``app.api.chat_agent._execute_search_documents`` performs no per-document
  filtering at all.

Rules that must hold for every function below:

1. No function takes a user argument. What a customer can read is a property of
   the published content, never of who is asking, so no caller can widen it.
2. Conditions are AND-ed. No ``or_``, no Admin escape hatch.
3. An empty allow-list short-circuits to "no published content". It must never
   degrade into an unfiltered query.
4. The allow-list is applied twice: once as the retriever's ``document_ids``
   filter, and again as a post-retrieval assertion (see ``business_search``).
5. The Knowledge Graph is never consulted. ``DeepRetriever._kg_query`` calls
   ``kg_service.get_relevant_context(question)`` with no document scoping, and
   its summary is merged into the LLM context by ``_assemble_context`` — so KG
   context can carry entities extracted from internal documents. We pass
   ``kg_service=None`` *and* ``mode="vector_only"``, so this holds even if a
   future caller passes a different mode.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.services.deep_retriever import DeepRetriever
from app.services.embedder import get_embedding_service
from app.services.reranker import get_reranker_service
from app.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)

BUSINESS_AUDIENCE = "business"
INTERNAL_AUDIENCE = "internal"

# Vector-only: see rule 5 in the module docstring.
BUSINESS_RETRIEVAL_MODE = "vector_only"

FALLBACK_LABEL = "Tài liệu Micco"


@dataclass(frozen=True)
class BusinessSource:
    """A citation safe to show a customer.

    Carries no chunk content, no internal document id, and no stored file path
    — only a label taken from the document an Admin explicitly published, plus
    a page number.
    """

    label: str
    page_no: int = 0


@dataclass(frozen=True)
class BusinessRetrievalResult:
    """What the portal chat is allowed to ground an answer in."""

    context: str
    sources: tuple[BusinessSource, ...] = ()
    allowed_document_ids: tuple[int, ...] = ()

    @property
    def has_published_content(self) -> bool:
        return bool(self.allowed_document_ids)

    @property
    def is_empty(self) -> bool:
        return not self.context


async def get_business_workspace(db: AsyncSession) -> KnowledgeBase | None:
    """The single workspace serving the portal, or None if none is configured.

    A partial unique index (migration 009) guarantees at most one row matches,
    so this cannot silently pick one of several.
    """
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.audience == BUSINESS_AUDIENCE)
    )
    return result.scalar_one_or_none()


async def get_business_document_ids(db: AsyncSession, workspace_id: int) -> list[int]:
    """Documents an external customer may be answered from.

    All four conditions AND-ed:
      - in the business workspace,
      - explicitly published by an Admin (is_business_visible),
      - fully indexed, so chunks actually exist in the vector store,
      - internally approved, so it never bypasses the normal review gate.
    """
    result = await db.execute(
        select(Document.id).where(
            Document.workspace_id == workspace_id,
            Document.is_business_visible.is_(True),
            Document.status == DocumentStatus.INDEXED,
            Document.approval_status == "approved",
        )
    )
    return [row[0] for row in result.all()]


async def get_business_document_labels(
    db: AsyncSession, document_ids: list[int]
) -> dict[int, str]:
    """Customer-facing label per document id.

    Labels come from the database rather than from the vector store's `source`
    metadata, which holds the stored file path.
    """
    if not document_ids:
        return {}

    result = await db.execute(
        select(Document.id, Document.original_filename).where(
            Document.id.in_(document_ids)
        )
    )
    return {doc_id: to_document_label(filename) for doc_id, filename in result.all()}


def to_document_label(filename: str | None) -> str:
    """Strip the extension off an uploaded filename for customer-facing display."""
    if not filename:
        return FALLBACK_LABEL
    return filename.rsplit(".", 1)[0].strip() or FALLBACK_LABEL


async def business_search(
    db: AsyncSession,
    question: str,
    top_k: int = 5,
) -> BusinessRetrievalResult:
    """Retrieve published business content for a customer question.

    Returns an empty result (never an unfiltered one) when nothing is
    published. The context is assembled here from the post-filtered chunks
    rather than reusing ``DeepRetrievalResult.context``, which is built before
    our second filter runs and would otherwise carry a dropped chunk's text.
    """
    workspace = await get_business_workspace(db)
    if workspace is None:
        logger.info("business_search: no workspace has audience=%r", BUSINESS_AUDIENCE)
        return BusinessRetrievalResult(context="")

    allowed_ids = await get_business_document_ids(db, workspace.id)
    if not allowed_ids:
        logger.info(
            "business_search: workspace %s has no published documents", workspace.id
        )
        return BusinessRetrievalResult(context="")

    retriever = DeepRetriever(
        workspace_id=workspace.id,
        kg_service=None,  # rule 5: KG context is not document-scoped
        vector_store=get_vector_store(workspace.id),
        embedder=get_embedding_service(),
        db=db,
        reranker=get_reranker_service(),
    )

    result = await retriever.query(
        question=question,
        mode=BUSINESS_RETRIEVAL_MODE,
        top_k=top_k,
        document_ids=allowed_ids,
        include_images=False,
    )

    kept = _drop_chunks_outside_allowlist(result.chunks, allowed_ids)
    labels = await get_business_document_labels(db, allowed_ids)

    return BusinessRetrievalResult(
        context=_assemble_business_context(kept, labels),
        sources=_to_sources(kept, labels),
        allowed_document_ids=tuple(allowed_ids),
    )


def _drop_chunks_outside_allowlist(chunks, allowed_ids: list[int]) -> list:
    """Second filter — the backstop if the retriever's filter ever regresses.

    The vector store applies ``{"document_id": {"$in": [...]}}`` as a hard
    filter today, so this should never drop anything. If it does, the retrieval
    layer or the Chroma metadata type has changed and the portal was one bug
    away from serving internal content, hence the ERROR log.
    """
    allowed = set(allowed_ids)
    kept = [chunk for chunk in chunks if chunk.document_id in allowed]

    dropped = len(chunks) - len(kept)
    if dropped:
        logger.error(
            "business_search dropped %d chunk(s) outside the allow-list "
            "(unexpected document_ids=%s, allowed=%s) — the retriever filter did not hold",
            dropped,
            sorted({c.document_id for c in chunks} - allowed),
            sorted(allowed),
        )
    return kept


def _to_sources(chunks, labels: dict[int, str]) -> tuple[BusinessSource, ...]:
    """One source per (document, page), in the order the chunks were ranked."""
    seen: set[tuple[int, int]] = set()
    sources: list[BusinessSource] = []
    for chunk in chunks:
        key = (chunk.document_id, chunk.page_no)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            BusinessSource(
                label=labels.get(chunk.document_id, FALLBACK_LABEL),
                page_no=chunk.page_no,
            )
        )
    return tuple(sources)


def _assemble_business_context(chunks, labels: dict[int, str]) -> str:
    """Numbered context for the LLM, citing labels instead of file paths."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        label = labels.get(chunk.document_id, FALLBACK_LABEL)
        heading = f" | {' > '.join(chunk.heading_path)}" if chunk.heading_path else ""
        page = f" | tr.{chunk.page_no}" if chunk.page_no else ""
        parts.append(f"[{i}] {label}{page}{heading}\n{chunk.content}")
    return "\n\n---\n\n".join(parts)
