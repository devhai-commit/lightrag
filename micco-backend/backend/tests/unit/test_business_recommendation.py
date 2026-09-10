"""Stripping the package-suggestion sentinel out of a streaming answer.

The sentinel is a control marker travelling down the same channel as the prose
a customer is reading, and streamed text cannot be taken back. So the property
these tests defend is: the marker never appears in displayed output, no matter
where the chunk boundaries fall.
"""
from __future__ import annotations

import pytest

from app.services.business_recommendation import (
    SENTINEL_OPEN,
    RecommendationSentinelFilter,
    _safe_prefix_length,
)


def run(chunks: list[str]) -> tuple[str, list[int]]:
    """Feed `chunks` through the filter; return (displayed text, ids)."""
    sentinel = RecommendationSentinelFilter()
    shown = "".join(sentinel.feed(chunk) for chunk in chunks)
    trailing, ids = sentinel.finish()
    return shown + trailing, ids


# ─── The marker never reaches the screen ───────────────────────────

def test_sentinel_is_stripped_from_a_single_chunk():
    shown, ids = run(["Micco có anfo.[[GOI_Y: 3,7]]"])

    assert shown == "Micco có anfo."
    assert ids == [3, 7]


def test_sentinel_split_across_every_possible_boundary_never_leaks():
    """The decisive test: a chunk boundary can fall anywhere in the marker."""
    answer = "Micco có anfo."
    full = f"{answer}[[GOI_Y: 3,7,12]]"

    for split in range(len(full) + 1):
        shown, ids = run([full[:split], full[split:]])
        assert shown == answer, f"leaked at split {split}: {shown!r}"
        assert ids == [3, 7, 12], f"lost ids at split {split}"


def test_sentinel_fed_one_character_at_a_time_never_leaks():
    shown, ids = run(list("Xin chào.[[GOI_Y: 1,2]]"))

    assert shown == "Xin chào."
    assert ids == [1, 2]


def test_partial_marker_is_held_back_until_it_is_disproved():
    """Mid-stream, a trailing "[[GOI" must not be shown — it may still grow."""
    sentinel = RecommendationSentinelFilter()

    assert sentinel.feed("Trả lời xong.[[GOI") == "Trả lời xong."
    # Nothing more is emitted while the marker is still possible.
    assert sentinel.feed("_Y: 5]]") == ""
    trailing, ids = sentinel.finish()
    assert trailing == ""
    assert ids == [5]


def test_text_that_looked_like_a_marker_is_released_at_finish():
    """Held-back text that never became a marker is real prose, not lost."""
    shown, ids = run(["Giá theo m[[3", ""])

    assert shown == "Giá theo m[[3"
    assert ids == []


def test_truncated_sentinel_is_dropped_not_shown():
    """A stream cut mid-marker must not print the fragment."""
    shown, ids = run(["Trả lời.[[GOI_Y: 3"])

    assert shown == "Trả lời."
    assert ids == []


# ─── Parsing ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "body,expected",
    [
        (" 3,7,12", [3, 7, 12]),
        ("3, 7 , 12", [3, 7, 12]),
        ("3", [3]),
        ("", []),
        ("abc", []),
        ("3;7|12", [3, 7, 12]),
    ],
)
def test_ids_are_parsed_loosely(body, expected):
    """Separators vary between model runs; digits are what matter."""
    _, ids = run([f"Xong.[[GOI_Y:{body}]]"])

    assert ids == expected


def test_text_after_the_sentinel_still_streams():
    """The contract says nothing follows it, but the model may disobey."""
    shown, ids = run(["A.[[GOI_Y: 1]] Còn nữa."])

    assert shown == "A. Còn nữa."
    assert ids == [1]


def test_two_sentinels_accumulate_ids_and_neither_leaks():
    shown, ids = run(["A.[[GOI_Y: 1]]B.[[GOI_Y: 2]]"])

    assert shown == "A.B."
    assert ids == [1, 2]


def test_runaway_marker_is_released_as_text_rather_than_buffered_forever():
    """A stray "[[GOI_Y:" in prose must not swallow the rest of the answer."""
    tail = "x" * 400
    shown, ids = run([f"Mở ngoặc [[GOI_Y: {tail}"])

    assert tail in shown
    assert ids == []


def test_answer_without_a_sentinel_passes_through_untouched():
    text = "Micco cung cấp thuốc nổ công nghiệp cho mỏ đá lộ thiên."

    shown, ids = run([text])

    assert shown == text
    assert ids == []


# ─── The borrowed technique ────────────────────────────────────────

@pytest.mark.parametrize(
    "buf,expected_held",
    [
        ("abc", 0),
        ("abc[", 1),
        ("abc[[", 2),
        ("abc[[GOI_Y", 7),
        ("abc[[x", 0),
    ],
)
def test_safe_prefix_length_holds_back_only_a_possible_marker_start(buf, expected_held):
    safe = _safe_prefix_length(buf, SENTINEL_OPEN)

    assert len(buf) - safe == expected_held
