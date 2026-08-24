"""
LLM Provider Package
=====================
Factory functions to create LLM and embedding providers based on config.

Usage::

    from app.services.llm import get_llm_provider, get_embedding_provider, get_stt_provider

    llm = get_llm_provider()          # uses LLM_PROVIDER from .env
    emb = get_embedding_provider()    # uses KG_EMBEDDING_PROVIDER from .env
    stt = get_stt_provider()          # uses STT_PROVIDER from .env
"""
from __future__ import annotations

from functools import lru_cache

from app.services.llm.base import EmbeddingProvider, LLMProvider, STTProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Create (and cache) the LLM provider configured via ``LLM_PROVIDER``."""
    from app.core.config import settings

    provider = settings.LLM_PROVIDER.lower()

    if provider == "gemini":
        from app.services.llm.gemini import GeminiLLMProvider

        if not settings.GOOGLE_AI_API_KEY:
            raise ValueError("GOOGLE_AI_API_KEY is required when LLM_PROVIDER=gemini")
        return GeminiLLMProvider(
            api_key=settings.GOOGLE_AI_API_KEY,
            model=settings.LLM_MODEL_FAST,
            thinking_level=settings.LLM_THINKING_LEVEL,
        )

    if provider == "ollama":
        from app.services.llm.ollama import OllamaLLMProvider

        return OllamaLLMProvider(
            host=settings.OLLAMA_HOST,
            model=settings.OLLAMA_MODEL,
        )

    if provider == "deepseek":
        from app.services.llm.deepseek import DeepSeekLLMProvider

        if not settings.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        return DeepSeekLLMProvider(
            api_key=settings.DEEPSEEK_API_KEY,
            model=settings.DEEPSEEK_MODEL,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Supported: gemini, ollama, deepseek")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Create (and cache) the embedding provider for KG (LightRAG)."""
    from app.core.config import settings

    provider = settings.KG_EMBEDDING_PROVIDER.lower()

    if provider == "gemini":
        from app.services.llm.gemini import GeminiEmbeddingProvider

        if not settings.GOOGLE_AI_API_KEY:
            raise ValueError("GOOGLE_AI_API_KEY is required when KG_EMBEDDING_PROVIDER=gemini")
        return GeminiEmbeddingProvider(
            api_key=settings.GOOGLE_AI_API_KEY,
            model=settings.KG_EMBEDDING_MODEL,
        )

    if provider == "ollama":
        from app.services.llm.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(
            host=settings.OLLAMA_HOST,
            model=settings.KG_EMBEDDING_MODEL,
        )

    if provider == "sentence_transformers":
        from app.services.llm.sentence_transformer import SentenceTransformerEmbeddingProvider

        return SentenceTransformerEmbeddingProvider(
            model=settings.KG_EMBEDDING_MODEL,
        )

    raise ValueError(
        f"Unknown KG_EMBEDDING_PROVIDER: {provider!r}. "
        "Supported: gemini, ollama, sentence_transformers"
    )


@lru_cache
def get_stt_provider() -> STTProvider:
    """Create (and cache) the STT provider configured via ``STT_PROVIDER``."""
    from app.core.config import settings

    provider = settings.STT_PROVIDER.lower()

    if provider == "phowhisper":
        from app.services.llm.phowhisper import PhoWhisperSTTProvider

        return PhoWhisperSTTProvider(
            model=settings.STT_MODEL,
            device=settings.STT_DEVICE,
        )

    raise ValueError(f"Unknown STT_PROVIDER: {provider!r}. Supported: phowhisper")


__all__ = [
    "get_llm_provider",
    "get_embedding_provider",
    "get_stt_provider",
    "LLMProvider",
    "EmbeddingProvider",
    "STTProvider",
]
