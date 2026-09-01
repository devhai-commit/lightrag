"""
STT (Speech-to-Text) API — transcribe short voice recordings to Vietnamese text.
"""
from __future__ import annotations

import asyncio
import io
import logging

import av
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.stt import TranscribeResponse
from app.services.llm import get_stt_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stt", tags=["stt"])

TARGET_SAMPLE_RATE = 16000


def _decode_audio(content: bytes, target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Decode any browser-recorded container/codec (webm/opus, ogg, wav, mp3, ...)
    into a mono float32 waveform, using PyAV's bundled FFmpeg libraries.

    Needed because libsndfile (soundfile/librosa's backend) can't open WebM
    containers at all, and librosa dropped its automatic audioread/ffmpeg
    fallback in 0.10+, so decoding no longer happened transparently.
    """
    container = av.open(io.BytesIO(content))
    try:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=target_sr)
        chunks = [f.to_ndarray() for frame in container.decode(stream) for f in resampler.resample(frame)]
        chunks += [f.to_ndarray() for f in resampler.resample(None)]
    finally:
        container.close()

    if not chunks:
        return np.array([], dtype=np.float32)

    pcm16 = np.concatenate(chunks, axis=1).reshape(-1)
    return pcm16.astype(np.float32) / 32768.0


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Transcribe a short Vietnamese voice recording to text (PhoWhisper)."""
    content = await file.read()

    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio file")

    max_bytes = settings.STT_MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Audio file too large. Max size: {settings.STT_MAX_FILE_SIZE_MB}MB",
        )

    try:
        audio = await asyncio.to_thread(_decode_audio, content)
    except Exception:
        logger.exception("Failed to decode uploaded audio")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Could not decode audio. Supported formats: webm, ogg, wav, mp3.",
        )

    sr = TARGET_SAMPLE_RATE
    duration = len(audio) / sr
    if duration <= 0.05:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No speech detected (audio too short)")

    if duration > settings.STT_MAX_AUDIO_SECONDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Audio too long. Max duration: {settings.STT_MAX_AUDIO_SECONDS}s",
        )

    stt = get_stt_provider()
    try:
        text = await stt.transcribe(audio, sample_rate=sr, language="vi")
    except Exception:
        logger.exception("STT transcription failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Transcription failed")

    return TranscribeResponse(text=text, language="vi", duration_seconds=round(duration, 2))
