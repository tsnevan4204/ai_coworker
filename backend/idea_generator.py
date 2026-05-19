"""Six stuck states → verbal_intro + chat_message."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.models import IdeaResult

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


async def generate(
    stuck_type: str,
    *,
    transcript_window: str,
    qdrant_context: dict | None = None,
    web_results: dict | None = None,
    decision_log: list | None = None,
) -> IdeaResult:
    settings = get_settings()
    prompt_path = PROMPTS_DIR / "idea_generator.txt"
    system = (
        prompt_path.read_text(encoding="utf-8")
        if prompt_path.exists()
        else "Generate verbal_intro (max 40 words) and plain-text chat_message with 3 options."
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user = json.dumps(
        {
            "stuck_type": stuck_type,
            "transcript_window": transcript_window,
            "qdrant_context": _serialize_hits(qdrant_context),
            "web_results": web_results,
            "decision_log": [d.model_dump() if hasattr(d, "model_dump") else d for d in (decision_log or [])],
        }
    )

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    return IdeaResult(
        verbal_intro=data.get("verbal_intro", "Let me offer a few options."),
        chat_message=data.get("chat_message", ""),
        intent=stuck_type,
    )


def _serialize_hits(qdrant_context: dict | None) -> list:
    if not qdrant_context:
        return []
    out = []
    for collection, hits in qdrant_context.items():
        for h in hits[:3]:
            payload = getattr(h, "payload", None) or {}
            out.append({"collection": collection, "payload": payload})
    return out
