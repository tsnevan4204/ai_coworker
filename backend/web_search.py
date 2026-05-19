"""Tavily web search with Redis cache."""

from __future__ import annotations

import json
import logging
import time

from tavily import AsyncTavilyClient

from backend.config import get_settings
from backend.session_state import get_redis

logger = logging.getLogger(__name__)


async def search_and_cache(topics: list[str], meeting_id: str) -> None:
    settings = get_settings()
    if not settings.tavily_api_key or not topics:
        return

    query = " ".join(topics[:5])
    try:
        client = AsyncTavilyClient(api_key=settings.tavily_api_key)
        results = await client.search(query, max_results=5)
        r = await get_redis()
        await r.set(
            f"session:{meeting_id}:web_cache",
            json.dumps({"query": query, "results": results, "cached_at": time.time()}),
            ex=3600,
        )
    except Exception:
        logger.exception("Tavily search failed")
