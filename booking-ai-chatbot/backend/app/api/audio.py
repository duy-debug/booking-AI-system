from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import AppError
from app.integrations.groq import get_groq_client

router = APIRouter(prefix="/api/v1/audio", tags=["audio"])

SUPPORTED_AUDIO_TYPES = {
    "audio/flac",
    "audio/m4a",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
}

KNOWN_SILENCE_HALLUCINATIONS = (
    "hãy subscribe",
    "đừng quên đăng ký",
    "không bỏ lỡ những video",
    "cảm ơn các bạn đã xem",
    "hẹn gặp lại các bạn",
)


class TranscriptionResponse(BaseModel):
    text: str


def _transcribe(filename: str, content: bytes) -> str:
    client = get_groq_client()
    result = client.audio.transcriptions.create(
        file=(filename, content),
        model=settings.GROQ_TRANSCRIPTION_MODEL,
        language="vi",
        response_format="json",
        temperature=0,
    )
    return result.text.strip()


@router.post("/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(file: Annotated[UploadFile, File()]) -> TranscriptionResponse:
    content_type = (file.content_type or "").split(";")[0].lower()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise AppError(415, "UNSUPPORTED_AUDIO_TYPE", "Định dạng âm thanh không được hỗ trợ.")

    content = await file.read(settings.MAX_AUDIO_UPLOAD_BYTES + 1)
    await file.close()
    if not content:
        raise AppError(422, "EMPTY_AUDIO", "Bản ghi âm đang trống.")
    if len(content) > settings.MAX_AUDIO_UPLOAD_BYTES:
        raise AppError(413, "AUDIO_TOO_LARGE", "Bản ghi âm vượt quá giới hạn 10 MB.")

    suffix = Path(file.filename or "").suffix or ".webm"
    try:
        text = await asyncio.to_thread(_transcribe, f"recording{suffix}", content)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            502,
            "TRANSCRIPTION_UNAVAILABLE",
            "Không thể nhận dạng giọng nói lúc này. Vui lòng thử lại.",
        ) from exc

    if not text:
        raise AppError(422, "SPEECH_NOT_RECOGNIZED", "Không nhận diện được lời nói trong bản ghi.")
    normalized = text.casefold()
    if any(phrase in normalized for phrase in KNOWN_SILENCE_HALLUCINATIONS):
        raise AppError(
            422,
            "SPEECH_NOT_RECOGNIZED",
            "Không phát hiện được giọng nói rõ ràng trong bản ghi.",
        )
    return TranscriptionResponse(text=text)
