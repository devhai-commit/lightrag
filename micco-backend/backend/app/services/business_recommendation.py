"""Extracting package suggestions from a streaming answer.

The model is asked to end its answer with a sentinel — ``[[GOI_Y: 3,7,12]]`` —
when the customer's need is still broad. That keeps suggestions inside the one
answer call instead of costing a second round trip, but it means a control
marker travels down the same channel as the prose the customer is reading.

So the marker must never reach the screen, not even briefly. A chunk boundary
can fall anywhere, including in the middle of ``[[GOI_Y:``, and text already
streamed cannot be taken back. This filter therefore holds back any trailing
text that could still turn out to be the start of the sentinel, using the
same trailing-prefix technique as
``ToolCallStreamParser._safe_prefix_length`` (``app/services/llm/
tool_call_parser.py``). That class is not reused: its tags are specific to tool
calls, and this needs to fail closed on a truncated marker rather than fall
back to emitting it as text.

Failure is always in the direction of "no suggestions": a malformed, truncated
or unparseable sentinel yields an empty id list and the answer streams
normally. Suggestions are an addition, never a precondition.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

SENTINEL_OPEN = "[[GOI_Y:"
SENTINEL_CLOSE = "]]"

# Ids inside the sentinel. Anything else in there is ignored.
_ID_RE = re.compile(r"\d+")

# A sentinel longer than this is not a sentinel; the model has run away and the
# buffer must not grow without bound.
_MAX_SENTINEL_BODY = 200


class RecommendationSentinelFilter:
    """Strips the suggestion sentinel out of a streaming answer.

    Feed each text delta to :meth:`feed` and stream what it returns. Call
    :meth:`finish` once the stream ends to get any held-back text plus the ids
    the model chose.
    """

    def __init__(self) -> None:
        self._pending = ""
        self._in_sentinel = False
        self._overflowed = False
        self._package_ids: list[int] = []

    @property
    def package_ids(self) -> list[int]:
        """Ids parsed so far. Order is the model's; validity is not checked here."""
        return list(self._package_ids)

    def feed(self, text: str) -> str:
        """Consume a delta, return the part that is safe to display now."""
        if not text:
            return ""

        self._pending += text
        emitted: list[str] = []

        while True:
            if self._in_sentinel:
                if SENTINEL_CLOSE not in self._pending:
                    if len(self._pending) > _MAX_SENTINEL_BODY:
                        # Never a real sentinel. Give up on it and treat what we
                        # are holding as text, so a stray "[[GOI_Y:" in prose
                        # cannot swallow the rest of the answer.
                        logger.warning(
                            "business chat: sentinel exceeded %d chars, "
                            "treating it as text",
                            _MAX_SENTINEL_BODY,
                        )
                        emitted.append(self._pending)
                        self._pending = ""
                        self._in_sentinel = False
                        self._overflowed = True
                    break

                body, self._pending = self._pending.split(SENTINEL_CLOSE, 1)
                self._in_sentinel = False
                self._package_ids.extend(_parse_ids(body))
                continue

            if SENTINEL_OPEN in self._pending:
                before, rest = self._pending.split(SENTINEL_OPEN, 1)
                if before:
                    emitted.append(before)
                self._pending = rest
                self._in_sentinel = True
                continue

            # No open marker yet. Hold back a trailing run that could still
            # become one once the next chunk arrives.
            safe = _safe_prefix_length(self._pending, SENTINEL_OPEN)
            if safe:
                emitted.append(self._pending[:safe])
                self._pending = self._pending[safe:]
            break

        return "".join(emitted)

    def finish(self) -> tuple[str, list[int]]:
        """End of stream: return leftover displayable text and the chosen ids.

        Text held back as a possible sentinel start is released here, because
        it never became one. Text held back *inside* an unterminated sentinel is
        dropped: a truncated marker is not something a customer should read.
        """
        leftover = ""
        if self._in_sentinel:
            if self._pending:
                logger.info(
                    "business chat: dropping unterminated sentinel (%d chars held)",
                    len(self._pending),
                )
        else:
            leftover = self._pending

        self._pending = ""
        self._in_sentinel = False
        return leftover, self.package_ids


def _parse_ids(body: str) -> list[int]:
    """Ids out of a sentinel body such as " 3, 7, 12"."""
    return [int(match.group()) for match in _ID_RE.finditer(body)]


def _safe_prefix_length(buf: str, marker: str) -> int:
    """Length of `buf` guaranteed not to be the start of `marker`.

    Technique borrowed from ToolCallStreamParser._safe_prefix_length.
    """
    max_suffix = min(len(marker) - 1, len(buf))
    for length in range(max_suffix, 0, -1):
        if buf[-length:] == marker[:length]:
            return len(buf) - length
    return len(buf)
