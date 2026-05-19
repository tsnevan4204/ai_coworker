"""Local JSON transcript files."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_settings
from backend.models import FullTranscript, IntentResult, TranscriptChunk

logger = logging.getLogger(__name__)


def _path(meeting_id: str) -> Path:
    settings = get_settings()
    settings.transcripts_dir.mkdir(parents=True, exist_ok=True)
    return settings.transcripts_dir / f"{meeting_id}.json"


def create(
    meeting_id: str,
    *,
    title: str | None = None,
    participants: list[str] | None = None,
) -> FullTranscript:
    transcript = FullTranscript(
        meeting_id=meeting_id,
        title=title,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        participants=participants or [],
    )
    _path(meeting_id).write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    return transcript


def read(meeting_id: str) -> FullTranscript:
    p = _path(meeting_id)
    if not p.exists():
        raise FileNotFoundError(f"No transcript for {meeting_id}")
    return FullTranscript.model_validate_json(p.read_text(encoding="utf-8"))


def append_chunk(
    meeting_id: str,
    chunk: TranscriptChunk,
    intent_result: IntentResult | None,
) -> None:
    p = _path(meeting_id)
    if not p.exists():
        create(meeting_id)

    data = json.loads(p.read_text(encoding="utf-8"))
    entry = {
        "timestamp": (chunk.timestamp or datetime.now(timezone.utc)).isoformat(),
        "speaker": chunk.speaker,
        "text": chunk.text,
        "intent": intent_result.intent if intent_result else "AMBIENT",
        "tasks_detected": [],
        "decisions_detected": [],
        "docs_surfaced": [],
    }
    data.setdefault("chunks", []).append(entry)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_all() -> list[str]:
    settings = get_settings()
    if not settings.transcripts_dir.exists():
        return []
    return [f.stem for f in settings.transcripts_dir.glob("*.json")]
