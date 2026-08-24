"""
STT (Speech-to-Text) Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel


class TranscribeResponse(BaseModel):
    """Response schema for speech-to-text transcription."""
    text: str
    language: str = "vi"
    duration_seconds: float
