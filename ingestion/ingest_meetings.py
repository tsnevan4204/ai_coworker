"""Ingest transcript JSON files into Qdrant past_meetings + decisions."""

from __future__ import annotations

import argparse
import asyncio
import logging

from backend import embeddings, qdrant_search, transcript_cache

logger = logging.getLogger(__name__)


async def ingest_meeting(meeting_id: str) -> None:
    await qdrant_search.ensure_collections()
    transcript = transcript_cache.read(meeting_id)
    participants = transcript.participants

    for i, chunk_data in enumerate(transcript.chunks):
        text = chunk_data.get("text", "")
        if not text:
            continue
        from backend.models import TranscriptChunk

        chunk = TranscriptChunk.from_text(
            meeting_id,
            text,
            speaker=chunk_data.get("speaker"),
        )
        vector = await embeddings.embed(text)
        await qdrant_search.store_meeting_chunk(
            chunk,
            vector,
            meeting_title=transcript.title,
            participants=participants,
            chunk_index=i,
        )

    for decision in transcript.decisions:
        vector = await embeddings.embed(decision.decision_text)
        await qdrant_search.store_decision(decision, vector, meeting_id)

    logger.info("Ingested meeting %s (%d chunks)", meeting_id, len(transcript.chunks))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest transcripts into Qdrant")
    parser.add_argument("--id", dest="meeting_id", help="Single meeting ID")
    args = parser.parse_args()

    if args.meeting_id:
        asyncio.run(ingest_meeting(args.meeting_id))
        return

    for mid in transcript_cache.list_all():
        asyncio.run(ingest_meeting(mid))


if __name__ == "__main__":
    main()
