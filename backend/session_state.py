"""Redis-backed live session state."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis.asyncio as redis

from backend.config import get_settings
from backend.models import IdeaResult, Session, TranscriptChunk, Utterance

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _key(meeting_id: str, suffix: str) -> str:
    return f"session:{meeting_id}:{suffix}"


async def set_bot_id(meeting_id: str, bot_id: str) -> None:
    r = await get_redis()
    await r.set(_key(meeting_id, "bot_id"), bot_id)
    await r.set(_key(meeting_id, "active"), "true")


async def get_bot_id(meeting_id: str) -> str | None:
    r = await get_redis()
    return await r.get(_key(meeting_id, "bot_id"))


async def is_session_active(meeting_id: str) -> bool:
    r = await get_redis()
    val = await r.get(_key(meeting_id, "active"))
    return val == "true"


async def deactivate_session(meeting_id: str) -> None:
    r = await get_redis()
    await r.set(_key(meeting_id, "active"), "false")


async def append_utterance(
    meeting_id: str,
    text: str,
    speaker: str | None,
) -> None:
    r = await get_redis()
    utterance = Utterance(text=text, speaker=speaker, received_at=time.time())
    await r.rpush(_key(meeting_id, "utterance_buffer"), utterance.model_dump_json())

    if speaker:
        counts_raw = await r.get(_key(meeting_id, "speaker_words"))
        counts: dict[str, int] = json.loads(counts_raw) if counts_raw else {}
        counts[speaker] = counts.get(speaker, 0) + len(text.split())
        await r.set(_key(meeting_id, "speaker_words"), json.dumps(counts))


async def drain_buffer(meeting_id: str) -> list[Utterance]:
    r = await get_redis()
    key = _key(meeting_id, "utterance_buffer")
    items = await r.lrange(key, 0, -1)
    if items:
        await r.delete(key)
    return [Utterance.model_validate_json(item) for item in items]


async def update_word_counts_only(chunk: TranscriptChunk) -> None:
    if not chunk.speaker:
        return
    r = await get_redis()
    counts_raw = await r.get(_key(chunk.meeting_id, "speaker_words"))
    counts: dict[str, int] = json.loads(counts_raw) if counts_raw else {}
    counts[chunk.speaker] = counts.get(chunk.speaker, 0) + chunk.word_count
    await r.set(_key(chunk.meeting_id, "speaker_words"), json.dumps(counts))


async def update_session(chunk: TranscriptChunk, session: Session) -> None:
    r = await get_redis()
    mid = chunk.meeting_id

    # Rolling last-3-min transcript (approximate by char budget ~4500 chars)
    prev = await r.get(_key(mid, "last_3_min")) or ""
    combined = f"{prev}\n{chunk.speaker or 'Unknown'}: {chunk.text}".strip()
    if len(combined) > 4500:
        combined = combined[-4500:]
    await r.set(_key(mid, "last_3_min"), combined)
    session.last_3_min_transcript = combined


async def get_session(meeting_id: str) -> Session:
    r = await get_redis()
    bot_id = await r.get(_key(meeting_id, "bot_id"))
    last_3 = await r.get(_key(meeting_id, "last_3_min")) or ""

    tasks_raw = await r.get(_key(meeting_id, "tasks"))
    decisions_raw = await r.get(_key(meeting_id, "decision_log"))
    agenda_raw = await r.get(_key(meeting_id, "agenda"))
    docs_raw = await r.get(_key(meeting_id, "docs_surfaced"))
    title = await r.get(_key(meeting_id, "title"))

    from backend.models import AgendaItem, Decision, Task

    tasks = [Task.model_validate(t) for t in json.loads(tasks_raw)] if tasks_raw else []
    decisions = (
        [Decision.model_validate(d) for d in json.loads(decisions_raw)]
        if decisions_raw
        else []
    )
    agenda = (
        [AgendaItem.model_validate(a) for a in json.loads(agenda_raw)]
        if agenda_raw
        else []
    )
    docs = json.loads(docs_raw) if docs_raw else []

    return Session(
        meeting_id=meeting_id,
        bot_id=bot_id,
        title=title,
        tasks=tasks,
        decision_log=decisions,
        agenda=agenda,
        docs_surfaced=docs,
        last_3_min_transcript=last_3,
    )


async def get_web_cache(meeting_id: str) -> dict[str, Any] | None:
    r = await get_redis()
    raw = await r.get(_key(meeting_id, "web_cache"))
    return json.loads(raw) if raw else None


async def set_precomputed_idea(meeting_id: str, idea: IdeaResult) -> None:
    r = await get_redis()
    await r.set(_key(meeting_id, "precomputed_idea"), idea.model_dump_json(), ex=600)


async def get_precomputed_idea(meeting_id: str) -> IdeaResult | None:
    r = await get_redis()
    raw = await r.get(_key(meeting_id, "precomputed_idea"))
    return IdeaResult.model_validate_json(raw) if raw else None


async def set_scheduled(meeting_id: str, ttl_secs: int = 86400) -> bool:
    """Returns False if already scheduled (dedup)."""
    r = await get_redis()
    key = f"scheduled:{meeting_id}"
    ok = await r.set(key, "true", nx=True, ex=ttl_secs)
    return bool(ok)


async def clear_meeting_keys(meeting_id: str) -> None:
    r = await get_redis()
    pattern = f"session:{meeting_id}:*"
    keys = [k async for k in r.scan_iter(match=pattern)]
    if keys:
        await r.delete(*keys)
