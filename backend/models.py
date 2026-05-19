from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StuckIntent = Literal[
    "STUCK",
    "CIRCULAR",
    "ARGUING",
    "CONFUSED",
    "PARALYZED",
    "CRASH",
]
Intent = Literal[
    "STUCK",
    "CIRCULAR",
    "ARGUING",
    "CONFUSED",
    "PARALYZED",
    "CRASH",
    "DECISION_DRIFT",
    "DECISION",
    "TASK",
    "OFF_TOPIC",
    "AMBIENT",
    "WRAP_UP",
]
Urgency = Literal["low", "medium", "high"]

STUCK_STATES: frozenset[str] = frozenset(
    {"STUCK", "CIRCULAR", "ARGUING", "CONFUSED", "PARALYZED", "CRASH"}
)


class TranscriptChunk(BaseModel):
    meeting_id: str
    text: str
    speaker: str | None = None
    timestamp: datetime | None = None
    word_count: int = 0

    @classmethod
    def from_text(
        cls,
        meeting_id: str,
        text: str,
        speaker: str | None = None,
        timestamp: datetime | None = None,
    ) -> TranscriptChunk:
        words = len(text.split())
        return cls(
            meeting_id=meeting_id,
            text=text,
            speaker=speaker,
            timestamp=timestamp,
            word_count=words,
        )


class IntentResult(BaseModel):
    intent: Intent = "AMBIENT"
    urgency: Urgency = "low"
    key_topics: list[str] = Field(default_factory=list)
    topic_repeat: bool = False
    external_topic: bool = False
    speaker_count: int = 1


class Task(BaseModel):
    owner: str
    description: str
    created_at: datetime | None = None


class Decision(BaseModel):
    decision_text: str
    speaker: str | None = None
    created_at: datetime | None = None
    confidence: float = 0.0


class AgendaItem(BaseModel):
    title: str
    addressed: bool = False


class IdeaResult(BaseModel):
    verbal_intro: str
    chat_message: str
    intent: str | None = None


class Session(BaseModel):
    meeting_id: str
    bot_id: str | None = None
    title: str | None = None
    participants: list[str] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    decision_log: list[Decision] = Field(default_factory=list)
    agenda: list[AgendaItem] = Field(default_factory=list)
    docs_surfaced: list[str] = Field(default_factory=list)
    last_3_min_transcript: str = ""


class Utterance(BaseModel):
    text: str
    speaker: str | None = None
    received_at: float


class FullTranscript(BaseModel):
    meeting_id: str
    title: str | None = None
    date: str | None = None
    participants: list[str] = Field(default_factory=list)
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    docs_surfaced: list[str] = Field(default_factory=list)
