"""Core orchestrator — parallel gather on each flushed chunk."""

from __future__ import annotations

import asyncio
import logging

from backend import embeddings, intent_classifier, qdrant_search, session_state, transcript_cache
from backend.config import get_settings
from backend.models import STUCK_STATES, IntentResult, Session, TranscriptChunk

logger = logging.getLogger(__name__)


async def process_chunk(chunk: TranscriptChunk, session: Session) -> None:
    settings = get_settings()
    if chunk.word_count < settings.min_chunk_words:
        await session_state.update_word_counts_only(chunk)
        return

    results = await asyncio.gather(
        embeddings.embed(chunk.text),
        intent_classifier.classify(chunk, session),
        session_state.update_session(chunk, session),
        return_exceptions=True,
    )

    embedding = results[0] if not isinstance(results[0], Exception) else None
    intent_result = results[1] if not isinstance(results[1], Exception) else None

    qdrant_results: dict = {}
    if embedding:
        try:
            qdrant_results = await qdrant_search.search(chunk.text, embedding)
        except Exception:
            logger.exception("Qdrant search failed")

    web_results = await session_state.get_web_cache(session.meeting_id)

    if isinstance(intent_result, IntentResult) and intent_result.external_topic:
        from backend import web_search

        asyncio.create_task(
            web_search.search_and_cache(intent_result.key_topics, session.meeting_id)
        )

    ir = intent_result if isinstance(intent_result, IntentResult) else None
    transcript_cache.append_chunk(session.meeting_id, chunk, ir)

    await route(chunk, session, ir, qdrant_results, embedding, web_results)


async def route(
    chunk: TranscriptChunk,
    session: Session,
    intent_result: IntentResult | None,
    qdrant_results: dict,
    embedding: list[float] | None,
    web_results: dict | None,
) -> None:
    intent = intent_result.intent if intent_result else "AMBIENT"

    if intent in STUCK_STATES:
        from backend import voice_gate
        from backend.recall_client import get_recall_client

        state = await voice_gate.evaluate_stuck(
            session.meeting_id,
            intent,
            qdrant_results=qdrant_results,
            web_results=web_results,
            decision_log=session.decision_log,
            transcript_window=session.last_3_min_transcript,
        )
        if state == "CONFIRMED":
            idea = await session_state.get_precomputed_idea(session.meeting_id)
            if idea and session.bot_id:
                recall = get_recall_client()
                await recall.output_audio(session.bot_id, idea.verbal_intro)
                await recall.send_chat_message(session.bot_id, idea.chat_message)
                await voice_gate.record_spoke(session.meeting_id)
                if embedding:
                    await qdrant_search.store_idea(
                        idea.verbal_intro, embedding, session.meeting_id
                    )
