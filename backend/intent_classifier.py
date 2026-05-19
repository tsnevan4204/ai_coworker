"""GPT-4o intent classification per transcript chunk."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.models import IntentResult, Session, TranscriptChunk

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_prompt_cache: dict[str, str] = {}


def load_prompts() -> dict[str, str]:
    global _prompt_cache
    if _prompt_cache:
        return _prompt_cache
    if PROMPTS_DIR.exists():
        for p in PROMPTS_DIR.glob("*.txt"):
            _prompt_cache[p.stem] = p.read_text(encoding="utf-8")
    return _prompt_cache


async def classify(chunk: TranscriptChunk, session: Session) -> IntentResult:
    settings = get_settings()
    if not settings.openai_api_key:
        return IntentResult()

    prompts = load_prompts()
    system = prompts.get(
        "intent_classifier",
        "Classify meeting transcript chunk intent. Respond JSON only.",
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_content = json.dumps(
        {
            "transcript": chunk.text,
            "speaker": chunk.speaker,
            "recent_context": session.last_3_min_transcript[-2000:],
            "agenda": [a.title for a in session.agenda],
        }
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return IntentResult.model_validate(data)
    except Exception:
        logger.exception("Intent classification failed")
        return IntentResult()
