"""
DeepSeek LLM Provider
======================
Concrete implementation using DeepSeek's OpenAI-compatible Chat Completions
API (``https://api.deepseek.com``).

Supports ``deepseek-chat`` (V3.2) and ``deepseek-reasoner`` (R1, thinking
mode via the ``reasoning_content`` field). DeepSeek has no vision input and
no public embedding endpoint, so only an ``LLMProvider`` is exposed here.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from app.services.llm.base import LLMProvider
from app.services.llm.tool_call_parser import ToolCallStreamParser
from app.services.llm.types import LLMMessage, LLMResult, StreamChunk

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class DeepSeekLLMProvider(LLMProvider):
    """DeepSeek text generation via the OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = _DEFAULT_BASE_URL,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _to_openai_messages(
        messages: list[LLMMessage],
        system_prompt: Optional[str] = None,
    ) -> list[dict]:
        result: list[dict] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for msg in messages:
            if msg.images:
                logger.warning("DeepSeek provider does not support image inputs — ignoring images")
            result.append({"role": msg.role, "content": msg.content})
        return result

    def _build_payload(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
        stream: bool,
    ) -> dict:
        return {
            "model": self._model,
            "messages": self._to_openai_messages(messages, system_prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        think: bool = False,
    ) -> str | LLMResult:
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            stream=False,
        )
        use_think = think and self.supports_thinking()
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
            content = message.get("content") or ""
            thinking = message.get("reasoning_content") or ""
            return LLMResult(content=content, thinking=thinking) if use_think else content
        except Exception as e:
            logger.error(f"DeepSeek LLM call failed: {e}")
            return LLMResult(content="") if use_think else ""

    async def acomplete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        think: bool = False,
    ) -> str | LLMResult:
        """Native async via httpx.AsyncClient (avoids the base class's thread-pool fallback)."""
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            stream=False,
        )
        use_think = think and self.supports_thinking()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
            content = message.get("content") or ""
            thinking = message.get("reasoning_content") or ""
            return LLMResult(content=content, thinking=thinking) if use_think else content
        except Exception as e:
            logger.error(f"DeepSeek async LLM call failed: {e}")
            return LLMResult(content="") if use_think else ""

    async def astream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        think: bool = False,
        tools: list | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            stream=True,
        )
        use_think = think and self.supports_thinking()
        tool_parser = ToolCallStreamParser()

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        if use_think and delta.get("reasoning_content"):
                            yield StreamChunk(type="thinking", text=delta["reasoning_content"])
                        if delta.get("content"):
                            for stream_chunk in tool_parser.feed(delta["content"]):
                                yield stream_chunk
            for stream_chunk in tool_parser.flush():
                yield stream_chunk
        except Exception as e:
            logger.error(f"DeepSeek streaming failed: {e}")
            yield StreamChunk(type="text", text="")

    def supports_vision(self) -> bool:
        return False

    def supports_thinking(self) -> bool:
        """Only ``deepseek-reasoner`` (R1) exposes reasoning_content."""
        return "reasoner" in self._model.lower()
