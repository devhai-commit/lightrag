"""Package suggestions through the portal chat endpoint.

The Phase 4 promise is that a broad question comes back as prose plus at most
three cards, produced by the *same* LLM call as the answer. These tests hold
that promise to its two hard edges: the sentinel never reaches the customer,
and a card only ever describes a package that is really in the active
catalogue.
"""
from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.models.chat_message import ChatMessage
from app.services import business_chat
from app.services.business_rag import (
    BUSINESS_AUDIENCE,
    BusinessRetrievalResult,
    BusinessSource,
)
from app.services.llm.types import StreamChunk

STREAM_URL = "/api/v1/business/chat/stream"
HISTORY_URL = "/api/v1/business/chat/history"

_CONTEXT = "[1] Bang gia san pham | tr.3\nAnfo dùng cho mỏ đá lộ thiên."


@pytest.fixture
def stub_retrieval(monkeypatch):
    """Published content exists and is relevant, so the LLM path is taken."""

    async def _fake_search(db, question, top_k=5):
        return BusinessRetrievalResult(
            context=_CONTEXT,
            sources=(BusinessSource(label="Bang gia san pham", page_no=3),),
            allowed_document_ids=(11,),
        )

    monkeypatch.setattr(business_chat, "business_search", _fake_search)


@pytest.fixture
async def business_workspace(make_workspace):
    return await make_workspace(
        name="Cong khai doanh nghiep", audience=BUSINESS_AUDIENCE
    )


@pytest.fixture
async def catalog(make_package):
    return [
        await make_package(name="Cung ứng thuốc nổ", category="Vật liệu nổ", sort_order=10),
        await make_package(name="Dịch vụ nổ mìn trọn gói", category="Dịch vụ", sort_order=20),
        await make_package(name="Tư vấn an toàn", category="Tư vấn", sort_order=30),
        await make_package(name="Gói đã ngừng", category="Cũ", is_active=False),
    ]


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.split("\n\n"):
        name = payload = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                payload = json.loads(line[len("data:"):].strip())
        if name is not None and payload is not None:
            events.append((name, payload))
    return events


def names(events) -> list[str]:
    return [name for name, _ in events]


def payload_of(events, name: str) -> dict:
    for event_name, payload in events:
        if event_name == name:
            return payload
    raise AssertionError(f"no {name!r} event in {names(events)}")


def streamed_text(events) -> str:
    return "".join(p["text"] for n, p in events if n == "delta")


async def ask(client: AsyncClient, message: str = "Chúng tôi khai thác đá, nên chọn gì?"):
    response = await client.post(STREAM_URL, json={"message": message})
    assert response.status_code == 200, response.text
    return parse_sse(response.text), response.text


# ─── The happy path ────────────────────────────────────────────────

async def test_broad_question_returns_prose_and_cards(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    ids = ",".join(str(p.id) for p in catalog[:2])
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text="Với mỏ đá lộ thiên, Micco có hai hướng. "),
        StreamChunk(type="text", text=f"[[GOI_Y: {ids}]]"),
    ]

    events, _ = await ask(business_client)

    # Deltas carry the model's raw text minus the sentinel, so the whitespace
    # it wrote before the marker is still there; only the final answer is
    # stripped, and that is what the client renders once complete arrives.
    assert "GOI_Y" not in streamed_text(events)
    assert streamed_text(events).strip() == "Với mỏ đá lộ thiên, Micco có hai hướng."
    assert payload_of(events, "complete")["answer"] == (
        "Với mỏ đá lộ thiên, Micco có hai hướng."
    )
    cards = payload_of(events, "recommendations")["packages"]
    assert [c["name"] for c in cards] == ["Cung ứng thuốc nổ", "Dịch vụ nổ mìn trọn gói"]


async def test_recommendations_arrive_before_complete(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text=f"Gợi ý.[[GOI_Y: {catalog[0].id}]]"),
    ]

    events, _ = await ask(business_client)

    order = names(events)
    assert order.index("recommendations") < order.index("complete")
    assert order[-1] == "complete"


async def test_only_one_llm_call_is_made(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    """The whole point of the sentinel: no second round trip for suggestions."""
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text=f"Gợi ý.[[GOI_Y: {catalog[0].id}]]"),
    ]

    await ask(business_client)

    assert len(mock_llm_provider.calls) == 1


async def test_catalog_digest_reaches_the_prompt(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    await ask(business_client)

    prompt = mock_llm_provider.last_call["system_prompt"]
    assert "Cung ứng thuốc nổ" in prompt
    assert "[[GOI_Y:" in prompt


async def test_inactive_packages_never_enter_the_prompt(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    await ask(business_client)

    assert "Gói đã ngừng" not in mock_llm_provider.last_call["system_prompt"]


# ─── The sentinel must not leak ────────────────────────────────────

async def test_sentinel_never_appears_in_the_response_body(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text="Trả lời."),
        StreamChunk(type="text", text="[[GOI"),
        StreamChunk(type="text", text=f"_Y: {catalog[0].id}]]"),
    ]

    events, raw = await ask(business_client)

    assert "GOI_Y" not in raw
    assert streamed_text(events) == "Trả lời."
    assert payload_of(events, "complete")["answer"] == "Trả lời."


async def test_truncated_sentinel_leaves_a_clean_answer_and_no_cards(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    mock_llm_provider.chunks = [StreamChunk(type="text", text="Trả lời.[[GOI_Y: 1")]

    events, raw = await ask(business_client)

    assert "GOI_Y" not in raw
    assert streamed_text(events) == "Trả lời."
    assert "recommendations" not in names(events)


# ─── Invalid or absent suggestions ────────────────────────────────

async def test_hallucinated_ids_produce_no_cards(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text="Trả lời.[[GOI_Y: 9998,9999]]")
    ]

    events, _ = await ask(business_client)

    assert "recommendations" not in names(events)
    assert payload_of(events, "complete")["recommendations"] == []


async def test_inactive_package_cannot_be_recommended(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    """Even if the model names it, a withdrawn offer must not be suggested."""
    inactive = catalog[-1]
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text=f"Trả lời.[[GOI_Y: {inactive.id}]]")
    ]

    events, raw = await ask(business_client)

    assert "recommendations" not in names(events)
    assert "Gói đã ngừng" not in raw


async def test_more_than_three_ids_are_capped(
    business_client: AsyncClient,
    business_workspace,
    make_package,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    extra = [await make_package(name=f"Gói {i}", sort_order=100 + i) for i in range(4)]
    all_ids = ",".join(str(p.id) for p in catalog[:3] + extra)
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text=f"Trả lời.[[GOI_Y: {all_ids}]]")
    ]

    events, _ = await ask(business_client)

    assert len(payload_of(events, "recommendations")["packages"]) == 3


async def test_no_sentinel_means_no_recommendations_event(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    """A specific question answered from the documents gets no cards."""
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text="Anfo dùng cho mỏ đá lộ thiên.")
    ]

    events, _ = await ask(business_client)

    assert "recommendations" not in names(events)


async def test_empty_catalog_leaves_the_contract_out_of_the_prompt(
    business_client: AsyncClient,
    business_workspace,
    stub_retrieval,
    mock_llm_provider,
):
    """No packages means the model is never taught a syntax it cannot fill."""
    events, _ = await ask(business_client)

    assert "GOI_Y" not in mock_llm_provider.last_call["system_prompt"]
    assert "recommendations" not in names(events)


async def test_cards_carry_no_internal_document_id(
    business_client: AsyncClient,
    business_workspace,
    make_package,
    make_document,
    stub_retrieval,
    mock_llm_provider,
):
    document = await make_document(workspace_id=business_workspace.id)
    package = await make_package(name="Gói có tài liệu", document_id=document.id)
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text=f"Trả lời.[[GOI_Y: {package.id}]]")
    ]

    events, raw = await ask(business_client)

    card = payload_of(events, "recommendations")["packages"][0]
    assert "document_id" not in card
    assert "document_id" not in raw


# ─── Surviving a reload ────────────────────────────────────────────

async def test_cards_are_persisted_and_read_back_from_history(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    mock_llm_provider.chunks = [
        StreamChunk(type="text", text=f"Trả lời.[[GOI_Y: {catalog[0].id}]]")
    ]
    await ask(business_client)

    messages = (await business_client.get(HISTORY_URL)).json()["data"]["messages"]

    assert messages[-1]["recommendations"][0]["name"] == "Cung ứng thuốc nổ"


async def test_history_returns_no_cards_for_a_turn_without_suggestions(
    business_client: AsyncClient,
    business_workspace,
    catalog,
    stub_retrieval,
    mock_llm_provider,
):
    mock_llm_provider.chunks = [StreamChunk(type="text", text="Trả lời cụ thể.")]
    await ask(business_client)

    messages = (await business_client.get(HISTORY_URL)).json()["data"]["messages"]

    assert messages[-1]["recommendations"] == []


async def test_history_drops_extra_fields_from_a_stored_card(
    business_client: AsyncClient,
    business_workspace,
    business_user,
    test_db,
):
    """A row written with more than the card fields must not leak them."""
    test_db.add(
        ChatMessage(
            workspace_id=business_workspace.id,
            user_id=business_user.id,
            message_id="seeded-pkg",
            role="assistant",
            content="Câu trả lời",
            recommended_packages=[
                {
                    "id": 1,
                    "name": "Gói A",
                    "category": "X",
                    "summary": "Y",
                    "document_id": 13,
                    "internal_margin": "35%",
                }
            ],
        )
    )
    await test_db.commit()

    response = await business_client.get(HISTORY_URL)

    assert response.status_code == 200
    assert "internal_margin" not in response.text
    assert "35%" not in response.text


# ─── Failure keeps the answer ─────────────────────────────────────

async def test_catalog_failure_degrades_to_no_suggestions(
    business_client: AsyncClient,
    business_workspace,
    stub_retrieval,
    mock_llm_provider,
    monkeypatch,
):
    """Suggestions are an addition; losing them must not lose the answer."""

    async def _boom(db):
        raise RuntimeError("catalogue table is gone")

    monkeypatch.setattr(business_chat, "get_active_packages", _boom)
    mock_llm_provider.chunks = [StreamChunk(type="text", text="Vẫn trả lời được.")]

    events, _ = await ask(business_client)

    assert streamed_text(events) == "Vẫn trả lời được."
    assert names(events)[-1] == "complete"
    assert "recommendations" not in names(events)
