"""
Unit tests for PhoWhisperSTTProvider.
Tests transcribe_sync()/transcribe() with a mocked HF pipeline — no real
model download or audio decode.
"""
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from app.services.llm.phowhisper import PhoWhisperSTTProvider


class TestPhoWhisperSTTProvider:
    def test_transcribe_sync_returns_stripped_text(self):
        provider = PhoWhisperSTTProvider(model="vinai/PhoWhisper-medium", device="cpu")
        mock_pipeline = MagicMock(return_value={"text": "  xin chào  "})
        provider._pipeline = mock_pipeline  # bypass lazy-load property

        audio = np.zeros(16000, dtype=np.float32)
        result = provider.transcribe_sync(audio, sample_rate=16000)

        assert result == "xin chào"
        mock_pipeline.assert_called_once()

    def test_transcribe_sync_empty_audio_returns_empty_string(self):
        provider = PhoWhisperSTTProvider(device="cpu")
        provider._pipeline = MagicMock()  # should never be called

        result = provider.transcribe_sync(np.array([], dtype=np.float32))

        assert result == ""
        provider._pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcribe_runs_in_thread(self):
        provider = PhoWhisperSTTProvider(device="cpu")
        provider._pipeline = MagicMock(return_value={"text": "test"})

        audio = np.zeros(1600, dtype=np.float32)
        result = await provider.transcribe(audio, sample_rate=16000)

        assert result == "test"

    def test_pipeline_lazy_loads_with_correct_device(self):
        with patch("transformers.pipeline") as mock_hf_pipeline, \
             patch("torch.cuda.is_available", return_value=False):
            provider = PhoWhisperSTTProvider(model="vinai/PhoWhisper-medium", device="auto")
            _ = provider.pipeline  # trigger lazy load

            mock_hf_pipeline.assert_called_once()
            _, kwargs = mock_hf_pipeline.call_args
            assert kwargs["device"] == -1  # CPU fallback

    def test_unknown_stt_provider_raises(self):
        from app.services.llm import get_stt_provider
        from app.core.config import settings

        get_stt_provider.cache_clear()
        original = settings.STT_PROVIDER
        settings.STT_PROVIDER = "unknown_provider"
        try:
            with pytest.raises(ValueError, match="Unknown STT_PROVIDER"):
                get_stt_provider()
        finally:
            settings.STT_PROVIDER = original
            get_stt_provider.cache_clear()
