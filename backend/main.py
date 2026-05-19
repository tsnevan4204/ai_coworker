"""FastAPI app — Recall webhooks, meeting join, health."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel

from backend.config import get_settings
from backend.intent_classifier import load_prompts
from backend.models import TranscriptChunk
from backend import pipeline, qdrant_search, session_state, transcript_cache
from backend.recall_client import get_recall_client
from backend.webhook_verify import normalize_headers, verify_recall_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_flusher_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_prompts()
    if qdrant_search.is_configured():
        if await qdrant_search.ensure_collections():
            logger.info("Qdrant collections ready")
        else:
            logger.warning(
                "Qdrant configured but unreachable — fix QDRANT_URL in .env or use Qdrant Cloud. "
                "Recall POC works without it."
            )
    else:
        logger.info(
            "Qdrant not configured (QDRANT_URL empty) — vector search disabled. OK for Recall POC."
        )
    yield
    for task in _flusher_tasks.values():
        task.cancel()


app = FastAPI(title="Yaco", description="Your AI coworker at every meeting", lifespan=lifespan)


class JoinMeetingRequest(BaseModel):
    meeting_id: str
    zoom_url: str
    title: str | None = None


@app.get("/health")
async def health():
    qdrant_configured = qdrant_search.is_configured()
    qdrant_ok = await qdrant_search.is_available() if qdrant_configured else False
    return {
        "status": "ok",
        "product": "Yaco",
        "qdrant": {
            "configured": qdrant_configured,
            "available": qdrant_ok,
        },
    }


def _verify_or_400(request: Request, raw_body: bytes) -> None:
    settings = get_settings()
    if not settings.recall_verification_secret:
        logger.warning("RECALL_VERIFICATION_SECRET not set — skipping verification")
        return
    headers = normalize_headers(dict(request.headers))
    if not verify_recall_request(headers, raw_body, settings.recall_verification_secret):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")


def _extract_meeting_id(payload: dict[str, Any]) -> str | None:
    bot = payload.get("data", {}).get("bot") or {}
    metadata = bot.get("metadata") or {}
    if isinstance(metadata, dict):
        mid = metadata.get("meeting_id")
        if mid:
            return str(mid)
    return None


def _parse_transcript_payload(payload: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """Returns meeting_id, text, speaker."""
    meeting_id = _extract_meeting_id(payload)
    inner = payload.get("data", {}).get("data", {})
    words = inner.get("words") or []
    if isinstance(words, dict):
        words = [words]
    text = " ".join(w.get("text", "") for w in words if w.get("text")).strip()
    participant = inner.get("participant") or {}
    speaker = participant.get("name")
    return meeting_id, text, speaker


async def buffer_flusher(meeting_id: str) -> None:
    while await session_state.is_session_active(meeting_id):
        await asyncio.sleep(10)
        utterances = await session_state.drain_buffer(meeting_id)
        if not utterances:
            continue
        text = " ".join(u.text for u in utterances if u.text).strip()
        if not text:
            continue
        speaker = utterances[-1].speaker if utterances else None
        chunk = TranscriptChunk.from_text(
            meeting_id,
            text,
            speaker=speaker,
            timestamp=datetime.now(timezone.utc),
        )
        session = await session_state.get_session(meeting_id)
        try:
            await pipeline.process_chunk(chunk, session)
        except Exception:
            logger.exception("pipeline.process_chunk failed for %s", meeting_id)


def _ensure_flusher(meeting_id: str) -> None:
    if meeting_id in _flusher_tasks and not _flusher_tasks[meeting_id].done():
        return
    _flusher_tasks[meeting_id] = asyncio.create_task(buffer_flusher(meeting_id))


async def _handle_transcript(payload: dict[str, Any]) -> None:
    meeting_id, text, speaker = _parse_transcript_payload(payload)
    if not meeting_id or not text:
        logger.debug("Skipping transcript event: missing meeting_id or text")
        return
    await session_state.append_utterance(meeting_id, text, speaker)
    _ensure_flusher(meeting_id)


async def _handle_recall_event(payload: dict[str, Any]) -> None:
    event = payload.get("event", "")
    meeting_id = _extract_meeting_id(payload)

    if event == "bot.done" and meeting_id:
        await session_state.deactivate_session(meeting_id)
        task = _flusher_tasks.pop(meeting_id, None)
        if task:
            task.cancel()
        try:
            from ingestion.ingest_meetings import ingest_meeting

            await ingest_meeting(meeting_id)
        except Exception:
            logger.exception("Post-meeting ingest failed for %s", meeting_id)
        await session_state.clear_meeting_keys(meeting_id)
        logger.info("Meeting ended: %s", meeting_id)


@app.get("/webhook/transcript")
async def webhook_transcript_get():
    return {
        "ok": True,
        "message": "Yaco transcript webhook is up. Recall POSTs transcript.data here per bot.",
    }


@app.post("/webhook/transcript")
async def webhook_transcript(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    _verify_or_400(request, raw_body)
    payload = json.loads(raw_body)
    background_tasks.add_task(_handle_transcript, payload)
    return {"ok": True}


@app.get("/webhook/recall")
async def webhook_recall_get():
    """Browser sanity check — Recall sends POST with signed body, not GET."""
    return {
        "ok": True,
        "message": "Yaco webhook endpoint is up. Recall will POST bot.done and related events here.",
    }


@app.post("/webhook/recall")
async def webhook_recall(request: Request, background_tasks: BackgroundTasks):
    """Dashboard webhooks: bot.done, bot.call_ended, transcript.done, transcript.failed."""
    raw_body = await request.body()
    _verify_or_400(request, raw_body)
    payload = json.loads(raw_body)
    background_tasks.add_task(_handle_recall_event, payload)
    return {"ok": True}


@app.post("/webhook/status")
async def webhook_status_alias(request: Request, background_tasks: BackgroundTasks):
    """Alias for dashboard status webhooks."""
    return await webhook_recall(request, background_tasks)


@app.post("/meetings/join")
async def meetings_join(body: JoinMeetingRequest):
    settings = get_settings()
    recall = get_recall_client()
    bot_id = await recall.create_bot(body.zoom_url, body.meeting_id)
    await session_state.set_bot_id(body.meeting_id, bot_id)
    transcript_cache.create(
        body.meeting_id,
        title=body.title,
    )
    _ensure_flusher(body.meeting_id)

    agenda_msg = (
        f"Hi, I'm {settings.bot_name} — your AI coworker. "
        "Here's what we need to cover today: (agenda loading…)"
    )
    try:
        await recall.send_chat_message(bot_id, agenda_msg)
    except Exception:
        logger.warning("Failed to post agenda chat", exc_info=True)

    return {"bot_id": bot_id, "meeting_id": body.meeting_id}
