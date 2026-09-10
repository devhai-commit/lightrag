"""The package catalogue: what reaches the prompt, and what reaches a customer.

Two boundaries matter here. The digest is prepended to every question, so it
must stay small. The card is the customer-facing projection, so it must be an
explicit field list rather than a row dump.
"""
from __future__ import annotations

from app.models.business_package import BusinessPackage
from app.services.business_packages import (
    MAX_RECOMMENDATIONS,
    build_catalog_digest,
    first_sentence,
    resolve_recommendations,
    to_card,
)


def package(**overrides) -> BusinessPackage:
    defaults = {
        "id": 1,
        "name": "Dịch vụ nổ mìn trọn gói",
        "category": "Dịch vụ nổ mìn",
        "summary": "Micco đảm nhận toàn bộ công tác nổ mìn. Bao gồm giám sát an toàn.",
        "target_customer": "Nhà thầu không có giấy phép vật liệu nổ.",
        "highlights": ["Trọn gói", "Có giám sát"],
        "price_note": "Khảo sát trước khi báo giá.",
        "is_active": True,
        "sort_order": 0,
    }
    return BusinessPackage(**{**defaults, **overrides})


# ─── Digest ────────────────────────────────────────────────────────

def test_digest_carries_id_name_category_and_first_sentence():
    digest = build_catalog_digest([package(id=7)])

    assert "[7]" in digest
    assert "Dịch vụ nổ mìn trọn gói" in digest
    assert "Micco đảm nhận toàn bộ công tác nổ mìn." in digest


def test_digest_omits_the_rest_of_the_summary():
    """It is prepended to every question, so only the first sentence goes in."""
    digest = build_catalog_digest([package()])

    assert "Bao gồm giám sát an toàn" not in digest


def test_digest_omits_the_price_note():
    """Price is negotiated; the model must not see a figure to repeat."""
    digest = build_catalog_digest([package(price_note="Từ 100 triệu đồng")])

    assert "100 triệu" not in digest


def test_digest_is_one_line_per_package():
    digest = build_catalog_digest([package(id=1), package(id=2), package(id=3)])

    assert len(digest.splitlines()) == 3


def test_empty_catalog_gives_an_empty_digest():
    """The prompt builder uses this to leave the suggestion contract out."""
    assert build_catalog_digest([]) == ""


def test_first_sentence_handles_missing_and_unpunctuated_text():
    assert first_sentence(None) == ""
    assert first_sentence("") == ""
    assert first_sentence("Không có dấu chấm") == "Không có dấu chấm"
    assert first_sentence("Câu một. Câu hai.") == "Câu một."


def test_first_sentence_is_truncated():
    assert len(first_sentence("x" * 500)) <= 220


# ─── Resolving the model's chosen ids ──────────────────────────────

def test_unknown_ids_are_dropped():
    """The model writes these ids from a digest, so it can invent one."""
    catalog = [package(id=1), package(id=2)]

    resolved = resolve_recommendations([1, 99, 2], catalog)

    assert [p.id for p in resolved] == [1, 2]


def test_duplicate_ids_are_collapsed():
    catalog = [package(id=1), package(id=2)]

    resolved = resolve_recommendations([1, 1, 2], catalog)

    assert [p.id for p in resolved] == [1, 2]


def test_recommendations_are_capped():
    catalog = [package(id=i) for i in range(1, 8)]

    resolved = resolve_recommendations([1, 2, 3, 4, 5, 6, 7], catalog)

    assert len(resolved) == MAX_RECOMMENDATIONS


def test_model_order_is_preserved():
    """The contract asks for descending relevance, so order carries meaning."""
    catalog = [package(id=1), package(id=2), package(id=3)]

    resolved = resolve_recommendations([3, 1], catalog)

    assert [p.id for p in resolved] == [3, 1]


def test_no_ids_gives_no_recommendations():
    assert resolve_recommendations([], [package()]) == []


def test_ids_are_resolved_against_the_given_catalog_only():
    """An inactive package never enters the catalogue list, so it cannot match."""
    assert resolve_recommendations([1], []) == []


# ─── Card projection ───────────────────────────────────────────────

def test_card_exposes_only_the_customer_facing_fields():
    card = to_card(package(id=4, document_id=13))

    assert set(card) == {
        "id",
        "name",
        "category",
        "summary",
        "target_customer",
        "highlights",
        "price_note",
    }


def test_card_never_carries_the_linked_document_id():
    """document_id is an internal handle; a card must not reveal it."""
    card = to_card(package(document_id=13))

    assert "document_id" not in card
    assert 13 not in card.values()


def test_card_copies_highlights_rather_than_sharing_the_list():
    original = package(highlights=["a"])

    card = to_card(original)
    card["highlights"].append("b")

    assert original.highlights == ["a"]


def test_card_handles_missing_optional_fields():
    card = to_card(package(target_customer=None, highlights=None, price_note=None))

    assert card["highlights"] == []
    assert card["target_customer"] is None
