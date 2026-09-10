"""What external business users are allowed to be answered from.

These are security regression tests. Every one of them exists because a
specific mistake would expose internal documents to customers. Do not relax
them; if one fails, assume content is leaking until proven otherwise.
"""
from __future__ import annotations

import inspect
import logging
from types import SimpleNamespace

import pytest

from app.models.document import DocumentStatus
from app.services import business_rag
from app.services.business_rag import (
    BUSINESS_AUDIENCE,
    business_search,
    get_business_document_ids,
    get_business_workspace,
)
from app.services.models.parsed_document import EnrichedChunk


# ─── Fakes ─────────────────────────────────────────────────────────

def _chunk(document_id: int, content: str, page_no: int = 1) -> EnrichedChunk:
    return EnrichedChunk(
        content=content,
        chunk_index=0,
        source_file="/srv/uploads/kb_1/stored_internal_salaries.pdf",
        document_id=document_id,
        page_no=page_no,
    )


@pytest.fixture
def fake_retriever(monkeypatch):
    """Replace the retrieval stack so no Chroma/embedding call is made.

    Records the constructor and query arguments so tests can assert on how
    business_search drives the retriever, and returns whatever chunks the test
    stages via `.returns`.
    """
    recorder = SimpleNamespace(init_kwargs=None, query_kwargs=None, returns=[])

    class FakeRetriever:
        def __init__(self, **kwargs):
            recorder.init_kwargs = kwargs

        async def query(self, **kwargs):
            recorder.query_kwargs = kwargs
            return SimpleNamespace(
                chunks=list(recorder.returns),
                citations=[],
                context="UNFILTERED CONTEXT MUST NOT BE REUSED",
            )

    monkeypatch.setattr(business_rag, "DeepRetriever", FakeRetriever)
    monkeypatch.setattr(business_rag, "get_vector_store", lambda ws: SimpleNamespace())
    monkeypatch.setattr(business_rag, "get_embedding_service", lambda: SimpleNamespace())
    monkeypatch.setattr(business_rag, "get_reranker_service", lambda: SimpleNamespace())
    return recorder


@pytest.fixture
async def business_workspace(make_workspace):
    return await make_workspace(name="Cong khai doanh nghiep", audience=BUSINESS_AUDIENCE)


# ─── The allow-list ────────────────────────────────────────────────

async def test_get_business_document_ids_includes_fully_published_document(
    test_db, business_workspace, make_document
):
    document = await make_document(
        workspace_id=business_workspace.id, is_business_visible=True
    )

    allowed = await get_business_document_ids(test_db, business_workspace.id)

    assert allowed == [document.id]


async def test_get_business_document_ids_excludes_unpublished_document(
    test_db, business_workspace, make_document
):
    await make_document(workspace_id=business_workspace.id, is_business_visible=False)

    allowed = await get_business_document_ids(test_db, business_workspace.id)

    assert allowed == []


async def test_get_business_document_ids_excludes_non_indexed_document(
    test_db, business_workspace, make_document
):
    await make_document(
        workspace_id=business_workspace.id,
        is_business_visible=True,
        status=DocumentStatus.PROCESSING,
    )

    allowed = await get_business_document_ids(test_db, business_workspace.id)

    assert allowed == []


async def test_get_business_document_ids_excludes_unapproved_document(
    test_db, business_workspace, make_document
):
    await make_document(
        workspace_id=business_workspace.id,
        is_business_visible=True,
        approval_status="pending",
    )

    allowed = await get_business_document_ids(test_db, business_workspace.id)

    assert allowed == []


async def test_get_business_document_ids_excludes_other_workspace_document(
    test_db, business_workspace, make_workspace, make_document
):
    internal = await make_workspace(name="Noi bo", audience="internal")
    await make_document(workspace_id=internal.id, is_business_visible=True)

    allowed = await get_business_document_ids(test_db, business_workspace.id)

    assert allowed == []


async def test_get_business_document_ids_takes_no_user_argument():
    """The allow-list must not depend on who is asking.

    get_allowed_document_ids (app/api/rag.py) widens its result from
    current_user, which is exactly how a department-less business account came
    to match every department-less internal document. This one has no such
    parameter, so no caller can widen it.
    """
    params = set(inspect.signature(get_business_document_ids).parameters)

    assert params == {"db", "workspace_id"}


async def test_get_business_workspace_returns_none_when_none_configured(
    test_db, make_workspace
):
    await make_workspace(name="Noi bo", audience="internal")

    assert await get_business_workspace(test_db) is None


# ─── Retrieval: empty allow-list must never widen ──────────────────

async def test_business_search_returns_empty_when_no_business_workspace(
    test_db, make_workspace, fake_retriever
):
    await make_workspace(name="Noi bo", audience="internal")

    result = await business_search(test_db, "gia thuoc no cong nghiep")

    assert result.context == ""
    assert result.sources == ()
    assert not result.has_published_content
    assert fake_retriever.query_kwargs is None, "must not query the vector store at all"


async def test_business_search_returns_empty_when_nothing_published(
    test_db, business_workspace, make_document, fake_retriever
):
    await make_document(workspace_id=business_workspace.id, is_business_visible=False)

    result = await business_search(test_db, "gia thuoc no cong nghiep")

    assert result.context == ""
    assert not result.has_published_content
    assert fake_retriever.query_kwargs is None, (
        "an empty allow-list must short-circuit, never run an unfiltered query"
    )


# ─── Retrieval: the double filter ──────────────────────────────────

async def test_business_search_passes_allowlist_as_retriever_filter(
    test_db, business_workspace, make_document, fake_retriever
):
    published = await make_document(
        workspace_id=business_workspace.id,
        original_filename="Catalogue san pham.pdf",
        is_business_visible=True,
    )
    fake_retriever.returns = [_chunk(published.id, "Noi dung cong khai")]

    await business_search(test_db, "san pham nao phu hop")

    assert fake_retriever.query_kwargs["document_ids"] == [published.id]


async def test_business_search_drops_chunk_outside_allowlist(
    test_db, business_workspace, make_document, fake_retriever, caplog
):
    """The single most important test in this feature.

    Simulates the retriever's own filter failing (a Chroma metadata type
    change, a regression in _vector_query) by returning a chunk from a
    document that is not on the allow-list. The post-retrieval filter must
    drop it, and its text must not survive anywhere in the result.
    """
    published = await make_document(
        workspace_id=business_workspace.id,
        original_filename="Catalogue san pham.pdf",
        is_business_visible=True,
    )
    internal_document_id = published.id + 5000
    fake_retriever.returns = [
        _chunk(published.id, "Thuoc no cong nghiep ANFO gia niem yet."),
        _chunk(internal_document_id, "BANG LUONG NOI BO 2026 - tuyet doi khong cong bo."),
    ]

    with caplog.at_level(logging.ERROR, logger=business_rag.__name__):
        result = await business_search(test_db, "bang gia")

    assert "ANFO" in result.context
    assert "BANG LUONG NOI BO" not in result.context
    assert "khong cong bo" not in result.context
    assert len(result.sources) == 1
    assert any(
        "dropped 1 chunk(s) outside the allow-list" in record.getMessage()
        for record in caplog.records
        if record.levelname == "ERROR"
    ), "dropping a chunk means the retriever filter regressed and must be logged"


async def test_business_search_ignores_retriever_assembled_context(
    test_db, business_workspace, make_document, fake_retriever
):
    """The context must be rebuilt from the filtered chunks.

    DeepRetrievalResult.context is assembled before our second filter runs, so
    reusing it would carry a dropped chunk's text straight into the prompt.
    """
    published = await make_document(
        workspace_id=business_workspace.id, is_business_visible=True
    )
    fake_retriever.returns = [_chunk(published.id, "Noi dung cong khai")]

    result = await business_search(test_db, "bang gia")

    assert "UNFILTERED CONTEXT MUST NOT BE REUSED" not in result.context
    assert "Noi dung cong khai" in result.context


# ─── Retrieval: no knowledge graph, no internal paths ──────────────

async def test_business_search_never_consults_the_knowledge_graph(
    test_db, business_workspace, make_document, fake_retriever
):
    """KG context is not document-scoped, so it can carry internal entities.

    DeepRetriever._kg_query calls kg_service.get_relevant_context(question)
    with no document filter, and _assemble_context merges the summary into the
    LLM context. Both belts must hold: no kg_service, and vector_only mode.
    """
    published = await make_document(
        workspace_id=business_workspace.id, is_business_visible=True
    )
    fake_retriever.returns = [_chunk(published.id, "Noi dung cong khai")]

    await business_search(test_db, "cong ty co nhung san pham gi")

    assert fake_retriever.init_kwargs["kg_service"] is None
    assert fake_retriever.query_kwargs["mode"] == "vector_only"
    assert fake_retriever.query_kwargs["include_images"] is False


async def test_business_search_sources_hide_stored_file_path(
    test_db, business_workspace, make_document, fake_retriever
):
    """Labels come from the database, not from the chunk's `source` metadata,
    which holds the stored path on disk."""
    published = await make_document(
        workspace_id=business_workspace.id,
        original_filename="Catalogue san pham 2026.pdf",
        is_business_visible=True,
    )
    fake_retriever.returns = [_chunk(published.id, "Noi dung cong khai")]

    result = await business_search(test_db, "catalogue")

    assert result.sources[0].label == "Catalogue san pham 2026"
    assert result.sources[0].page_no == 1
    assert "stored_" not in result.context
    assert "/srv/uploads" not in result.context
    assert "internal_salaries" not in result.context


async def test_business_search_deduplicates_sources_per_page(
    test_db, business_workspace, make_document, fake_retriever
):
    published = await make_document(
        workspace_id=business_workspace.id, is_business_visible=True
    )
    fake_retriever.returns = [
        _chunk(published.id, "Doan 1", page_no=3),
        _chunk(published.id, "Doan 2", page_no=3),
        _chunk(published.id, "Doan 3", page_no=4),
    ]

    result = await business_search(test_db, "bang gia")

    assert [s.page_no for s in result.sources] == [3, 4]
