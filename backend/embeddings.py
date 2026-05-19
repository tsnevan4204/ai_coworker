"""OpenAI text-embedding-3-small with optional Redis cache."""

from __future__ import annotations

import hashlib
import json
import logging

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.session_state import get_redis

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


async def embed(text: str, *, use_cache: bool = True) -> list[float]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()}"
    if use_cache:
        try:
            r = await get_redis()
            cached = await r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            logger.debug("Embedding cache miss or redis unavailable", exc_info=True)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    vector = response.data[0].embedding

    if use_cache:
        try:
            r = await get_redis()
            await r.set(cache_key, json.dumps(vector), ex=86400 * 7)
        except Exception:
            pass

    return vector
