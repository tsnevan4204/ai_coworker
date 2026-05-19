"""Recall.ai API wrapper — bot, chat, audio output."""

from __future__ import annotations

import logging

import httpx

from backend.config import get_settings
from backend.tts import generate_mp3_b64

logger = logging.getLogger(__name__)

# Minimal valid silent MP3 (placeholder until startup generates one)
SILENT_MP3_B64 = (
    "//uQxAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAACcQCA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


class RecallClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._silent_b64 = SILENT_MP3_B64

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.settings.recall_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_bot(
        self,
        zoom_url: str,
        meeting_id: str,
        *,
        greeting_b64: str | None = None,
    ) -> str:
        settings = self.settings
        b64 = greeting_b64 or self._silent_b64
        payload = {
            "meeting_url": zoom_url,
            "bot_name": settings.bot_name,
            "metadata": {"meeting_id": meeting_id},
            "recording_config": {
                "transcript": {
                    "provider": {
                        "recallai_streaming": {
                            "mode": "prioritize_low_latency",
                            "language_code": "en",
                        }
                    }
                },
                "realtime_endpoints": [
                    {
                        "type": "webhook",
                        "url": f"{settings.public_base_url.rstrip('/')}/webhook/transcript",
                        "events": ["transcript.data"],
                    }
                ],
            },
            "automatic_audio_output": {
                "in_call_recording": {
                    "data": {"kind": "mp3", "b64_data": b64},
                }
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.recall_base_url}/bot/",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        bot_id = data.get("id")
        if not bot_id:
            raise ValueError(f"Recall create_bot missing id: {data}")
        logger.info("Created Recall bot %s for meeting %s", bot_id, meeting_id)
        return bot_id

    async def send_chat_message(self, bot_id: str, text: str, to: str = "everyone") -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.settings.recall_base_url}/bot/{bot_id}/send_chat_message/",
                headers=self._headers(),
                json={"message": text[:4096], "to": to},
            )
            resp.raise_for_status()

    async def output_audio(self, bot_id: str, text: str) -> None:
        b64_data = await generate_mp3_b64(text)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.settings.recall_base_url}/bot/{bot_id}/output_audio/",
                headers=self._headers(),
                json={"kind": "mp3", "b64_data": b64_data},
            )
            resp.raise_for_status()

    async def remove_bot(self, bot_id: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{self.settings.recall_base_url}/bot/{bot_id}/",
                headers=self._headers(),
            )
            resp.raise_for_status()


_recall_client: RecallClient | None = None


def get_recall_client() -> RecallClient:
    global _recall_client
    if _recall_client is None:
        _recall_client = RecallClient()
    return _recall_client
