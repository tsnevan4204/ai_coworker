"""OpenAI TTS → base64 MP3 for Recall output_audio."""

from __future__ import annotations

import base64

from openai import AsyncOpenAI

from backend.config import get_settings


async def generate_mp3_b64(text: str) -> str:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
        response_format="mp3",
    )
    mp3_bytes = response.content
    return base64.b64encode(mp3_bytes).decode("utf-8")
