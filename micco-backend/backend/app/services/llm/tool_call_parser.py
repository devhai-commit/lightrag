"""
Tool-call Stream Parser
========================
Shared incremental parser for prompt-based tool calling (used by providers
that don't have native function-calling support, e.g. Ollama, DeepSeek).

Models following ``OLLAMA_TOOL_SYSTEM`` / ``chat_agent.py`` conventions emit
``<tool_call>{"name": ..., "arguments": {...}}</tool_call>`` inline in their
text output. This parser buffers streamed text deltas, detects the tag pair,
and turns them into a StreamChunk(type="function_call") — everything else
passes through as StreamChunk(type="text").
"""
from __future__ import annotations

import json
import logging
import re

from app.services.llm.types import StreamChunk

logger = logging.getLogger(__name__)

_OPEN_TAG = "<tool_call>"
_CLOSE_TAG = "</tool_call>"
_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)


class ToolCallStreamParser:
    """Stateful `<tool_call>` tag detector for a single streaming response.

    Token streams can split the tag across arbitrary chunk boundaries (e.g.
    ``"<tool"`` then ``"_call>"``), so plain text is held back whenever its
    trailing edge could be the start of ``<tool_call>`` until enough of the
    next delta arrives to confirm or rule it out.
    """

    def __init__(self) -> None:
        self._pending = ""
        self._in_tool_call = False

    def feed(self, content: str) -> list[StreamChunk]:
        """Feed the next text delta; returns zero or more StreamChunks."""
        if not content:
            return []

        self._pending += content

        if self._in_tool_call:
            return self._flush_tool_call() if _CLOSE_TAG in self._pending else []

        if _OPEN_TAG in self._pending:
            before, rest = self._pending.split(_OPEN_TAG, 1)
            chunks: list[StreamChunk] = []
            if before:
                chunks.append(StreamChunk(type="text", text=before))
            self._in_tool_call = True
            self._pending = _OPEN_TAG + rest
            if _CLOSE_TAG in self._pending:
                chunks.extend(self._flush_tool_call())
            return chunks

        # No open tag yet — hold back any trailing text that could still
        # become the start of "<tool_call>" once more content arrives.
        safe_len = self._safe_prefix_length(self._pending, _OPEN_TAG)
        if safe_len == 0:
            return []
        emit, self._pending = self._pending[:safe_len], self._pending[safe_len:]
        return [StreamChunk(type="text", text=emit)]

    @staticmethod
    def _safe_prefix_length(buf: str, tag: str) -> int:
        """Length of `buf` that is guaranteed not to be part of `tag`."""
        max_suffix = min(len(tag) - 1, len(buf))
        for length in range(max_suffix, 0, -1):
            if buf[-length:] == tag[:length]:
                return len(buf) - length
        return len(buf)

    def _flush_tool_call(self) -> list[StreamChunk]:
        # Split off anything the model streamed after </tool_call> up front —
        # both the match and fallback-to-text branches below must only cover
        # the tagged span itself, not text following it.
        tagged, after = self._pending.split(_CLOSE_TAG, 1)
        tagged += _CLOSE_TAG
        self._pending = ""
        self._in_tool_call = False

        chunks: list[StreamChunk] = []
        match = _TOOL_CALL_RE.search(tagged)
        if match:
            try:
                tool_data = json.loads(match.group(1).strip())
                chunks.append(StreamChunk(
                    type="function_call",
                    function_call={
                        "name": tool_data.get("name", ""),
                        "args": tool_data.get("arguments", {}),
                    },
                ))
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool call JSON: %s", match.group(1))
                chunks.append(StreamChunk(type="text", text=tagged))
        else:
            chunks.append(StreamChunk(type="text", text=tagged))

        if after:
            chunks.extend(self.feed(after))
        return chunks

    def flush(self) -> list[StreamChunk]:
        """Call once the stream ends — any leftover buffer is emitted as text."""
        if self._pending:
            buffered = self._pending
            self._pending = ""
            self._in_tool_call = False
            return [StreamChunk(type="text", text=buffered)]
        return []
