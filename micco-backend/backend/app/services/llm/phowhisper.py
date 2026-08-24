"""
PhoWhisper STT Provider
========================
Concrete STTProvider using vinai/PhoWhisper-medium (Whisper architecture,
fine-tuned for Vietnamese) via the HuggingFace transformers ASR pipeline.

Usage::

    STT_PROVIDER=phowhisper
    STT_MODEL=vinai/PhoWhisper-medium
"""
from __future__ import annotations

import logging

import numpy as np

from app.services.llm.base import STTProvider

logger = logging.getLogger(__name__)


class PhoWhisperSTTProvider(STTProvider):
    """Local Vietnamese ASR provider using PhoWhisper via transformers.pipeline."""

    def __init__(self, model: str = "vinai/PhoWhisper-medium", device: str = "auto"):
        self._model_name = model
        self._device_setting = device
        self._pipeline = None

    # -- lazy load to avoid importing torch/transformers or downloading
    #    the model at import time / app startup --

    @property
    def pipeline(self):
        if self._pipeline is None:
            import torch
            from transformers import pipeline as hf_pipeline

            if self._device_setting == "auto":
                device = 0 if torch.cuda.is_available() else -1
            elif self._device_setting == "cuda":
                device = 0
            else:
                device = -1

            logger.info(
                "Loading PhoWhisper STT model: %s (device=%s)",
                self._model_name,
                "cuda" if device == 0 else "cpu",
            )
            self._pipeline = hf_pipeline(
                "automatic-speech-recognition",
                model=self._model_name,
                device=device,
            )
            logger.info("PhoWhisper STT model loaded.")
        return self._pipeline

    def transcribe_sync(
        self,
        audio: np.ndarray,
        *,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        if audio.size == 0:
            return ""
        result = self.pipeline({"raw": audio.astype(np.float32), "sampling_rate": sample_rate})
        return (result.get("text") or "").strip()
