"""Qdrant vector search and upserts across four collections."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from backend.config import get_settings
from backend.embeddings import EMBEDDING_DIM
from backend.models import Decision, TranscriptChunk

logger = logging.getLogger(__name__)

COLLECTIONS = ("company_docs", "past_meetings", "decisions", "ideas")

_client: AsyncQdrantClient | None = None
_available: bool | None = None  # None = not checked yet


def is_configured() -> bool:
    url = get_settings().qdrant_url.strip()
    if not url:
        return False
    # Ignore obvious placeholders
    lowered = url.lower()
    if lowered in ("none", "null", "skip", "disabled"):
        return False
    return True


async def is_available() -> bool:
    """Cached check: configured and reachable."""
    global _available
    if _available is not None:
        return _available
    if not is_configured():
        _available = False
        return False
    try:
        client = await get_qdrant()
        await client.get_collections()
        _available = True
        logger.info("Qdrant connected at %s", get_settings().qdrant_url)
    except Exception as e:
        _available = False
        logger.warning(
            "Qdrant unreachable (%s). Vector search disabled until URL is fixed and server restarted.",
            e,
        )
    return _available


async def get_qdrant() -> AsyncQdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.qdrant_url.strip():
            raise RuntimeError("QDRANT_URL is not set")
        _client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _client


async def ensure_collections() -> bool:
    """Create collections if missing. Returns True if Qdrant is ready."""
    if not await is_available():
        return False
    client = await get_qdrant()
    for name in COLLECTIONS:
        exists = await client.collection_exists(name)
        if not exists:
            await client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=EMBEDDING_DIM,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection %s", name)
    return True


async def search(
    text: str,
    vector: list[float],
    *,
    limit: int = 5,
) -> dict[str, list[Any]]:
    if not await is_available():
        return {c: [] for c in COLLECTIONS}

    settings = get_settings()
    client = await get_qdrant()
    threshold = settings.doc_relevance_threshold
    results: dict[str, list[Any]] = {}

    for collection in COLLECTIONS:
        try:
            hits = await client.search(
                collection_name=collection,
                query_vector=vector,
                limit=limit,
                score_threshold=threshold,
                with_payload=True,
            )
            results[collection] = hits
        except Exception as e:
            logger.warning("Qdrant search failed for %s: %s", collection, e)
            results[collection] = []

    return results


async def store_meeting_chunk(
    chunk: TranscriptChunk,
    embedding: list[float],
    *,
    meeting_title: str | None,
    participants: list[str],
    chunk_index: int,
) -> None:
    if not await is_available():
        return
    client = await get_qdrant()
    await client.upsert(
        collection_name="past_meetings",
        points=[
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "meeting_id": chunk.meeting_id,
                    "meeting_title": meeting_title or "",
                    "date": chunk.timestamp.isoformat() if chunk.timestamp else "",
                    "participants": participants,
                    "speaker": chunk.speaker or "",
                    "chunk_index": chunk_index,
                    "text": chunk.text,
                },
            )
        ],
    )


async def store_decision(decision: Decision, embedding: list[float], meeting_id: str) -> None:
    if not await is_available():
        return
    client = await get_qdrant()
    await client.upsert(
        collection_name="decisions",
        points=[
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "decision_text": decision.decision_text,
                    "meeting_id": meeting_id,
                    "confidence": decision.confidence,
                    "reversed": False,
                },
            )
        ],
    )


async def store_idea(
    idea_text: str,
    embedding: list[float],
    meeting_id: str,
    *,
    status: str = "floated",
) -> None:
    if not await is_available():
        return
    client = await get_qdrant()
    await client.upsert(
        collection_name="ideas",
        points=[
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "idea_text": idea_text,
                    "meeting_id": meeting_id,
                    "status": status,
                },
            )
        ],
    )


async def upsert_company_doc_chunk(
    embedding: list[float],
    payload: dict[str, Any],
) -> None:
    if not await is_available():
        raise RuntimeError("Qdrant is not available — set QDRANT_URL and QDRANT_API_KEY")
    client = await get_qdrant()
    await client.upsert(
        collection_name="company_docs",
        points=[
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload=payload,
            )
        ],
    )
