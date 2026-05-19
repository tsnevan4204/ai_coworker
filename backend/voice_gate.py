"""Confirmation window state machine + speak cooldown."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from backend import session_state
from backend.models import STUCK_STATES

logger = logging.getLogger(__name__)

CONFIRMATION_WINDOWS: dict[str, int] = {
    "ARGUING": 30,
    "STUCK": 20,
    "CIRCULAR": 20,
    "PARALYZED": 20,
    "CONFUSED": 15,
    "CRASH": 15,
}

COOLDOWN_SECS = 90


async def _redis():
    return await session_state.get_redis()


def _key(meeting_id: str, suffix: str) -> str:
    return f"session:{meeting_id}:{suffix}"


async def evaluate_stuck(
    meeting_id: str,
    intent: str,
    *,
    qdrant_results: dict | None = None,
    web_results: dict | None = None,
    decision_log: list | None = None,
    transcript_window: str = "",
) -> str:
    if intent not in STUCK_STATES:
        return "NONE"

    if await _in_cooldown(meeting_id):
        return "COOLDOWN"

    r = await _redis()
    pending_intent = await r.get(_key(meeting_id, "confirm_intent"))
    confidence_raw = await r.get(_key(meeting_id, "confirm_confidence"))
    detected_at_raw = await r.get(_key(meeting_id, "confirm_detected_at"))
    confidence = int(confidence_raw) if confidence_raw else 0
    now = time.time()

    if not pending_intent:
        await r.set(_key(meeting_id, "confirm_intent"), intent)
        await r.set(_key(meeting_id, "confirm_detected_at"), str(now))
        await r.set(_key(meeting_id, "confirm_confidence"), "1")
        asyncio.create_task(
            precompute_idea(
                meeting_id,
                intent,
                qdrant_results=qdrant_results,
                web_results=web_results,
                decision_log=decision_log,
                transcript_window=transcript_window,
            )
        )
        return "PENDING"

    window = CONFIRMATION_WINDOWS.get(intent, 20)
    detected_at = float(detected_at_raw) if detected_at_raw else now

    if pending_intent != intent:
        await r.set(_key(meeting_id, "confirm_intent"), intent)
        await r.set(_key(meeting_id, "confirm_detected_at"), str(now))
        await r.set(_key(meeting_id, "confirm_confidence"), "1")
        asyncio.create_task(
            precompute_idea(
                meeting_id,
                intent,
                qdrant_results=qdrant_results,
                web_results=web_results,
                decision_log=decision_log,
                transcript_window=transcript_window,
            )
        )
        return "PENDING"

    if intent == pending_intent:
        confidence += 1
        await r.set(_key(meeting_id, "confirm_confidence"), str(confidence))

    if now - detected_at >= window:
        if confidence >= 1:
            await r.delete(_key(meeting_id, "confirm_intent"))
            await r.delete(_key(meeting_id, "confirm_detected_at"))
            await r.delete(_key(meeting_id, "confirm_confidence"))
            return "CONFIRMED"
        await _clear_pending(meeting_id)
        return "NONE"

    return "PENDING"


async def decay_pending(meeting_id: str) -> None:
    """Call when AMBIENT/TASK/DECISION chunk arrives during PENDING."""
    r = await _redis()
    if not await r.get(_key(meeting_id, "confirm_intent")):
        return
    confidence_raw = await r.get(_key(meeting_id, "confirm_confidence"))
    confidence = int(confidence_raw) if confidence_raw else 0
    confidence -= 1
    if confidence <= 0:
        await _clear_pending(meeting_id)
    else:
        await r.set(_key(meeting_id, "confirm_confidence"), str(confidence))


async def _clear_pending(meeting_id: str) -> None:
    r = await _redis()
    await r.delete(_key(meeting_id, "confirm_intent"))
    await r.delete(_key(meeting_id, "confirm_detected_at"))
    await r.delete(_key(meeting_id, "confirm_confidence"))


async def _in_cooldown(meeting_id: str) -> bool:
    r = await _redis()
    last = await r.get(_key(meeting_id, "last_spoke"))
    if not last:
        return False
    return time.time() - float(last) < COOLDOWN_SECS


async def record_spoke(meeting_id: str) -> None:
    r = await _redis()
    await r.set(_key(meeting_id, "last_spoke"), str(time.time()))
    await _clear_pending(meeting_id)


async def precompute_idea(
    meeting_id: str,
    intent: str,
    *,
    qdrant_results: dict | None = None,
    web_results: dict | None = None,
    decision_log: list | None = None,
    transcript_window: str = "",
) -> None:
    from backend import idea_generator

    try:
        idea = await idea_generator.generate(
            intent,
            transcript_window=transcript_window,
            qdrant_context=qdrant_results,
            web_results=web_results,
            decision_log=decision_log or [],
        )
        await session_state.set_precomputed_idea(meeting_id, idea)
    except Exception:
        logger.exception("precompute_idea failed for %s", meeting_id)
