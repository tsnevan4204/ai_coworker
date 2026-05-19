# Yaco — Your AI Coworker at Every Meeting

### "Think Outside the Bot" Hackathon — Qdrant Vector Space Day 2026

> **Product:** **Yaco** (Your AI Coworker)  
> **Tagline:** Your AI coworker at every meeting  
> **Repo:** `ai_coworker` — flat layout (`backend/`, `ingestion/` at root)

---

## Vision

An ambient AI agent that joins live Zoom meetings and acts as a silent analyst in the room. It listens continuously, thinks in the background, and decides on its own when to interject — via voice or Zoom chat. All thinking is invisible. Only its output is heard.

**Core principle:** The bot is another employee in the meeting. It anticipates, not responds.

---

## Locked decisions

| Question | Answer |
|---|---|
| Branding | **Yaco** — bot name in Zoom: `Yaco` |
| Meeting platform | Zoom via Recall.ai |
| `meeting_id` | **Google Calendar event ID** in `metadata.meeting_id` on Create Bot |
| Audio | Recall `output_audio` + `automatic_audio_output` (silent MP3 minimum) |
| Transcription | `recallai_streaming`, `prioritize_low_latency` |
| Webhook verify | Workspace secret `whsec_...` (not raw body HMAC hex) |
| Language | Pure Python, single FastAPI process |
| Storage | Qdrant + Redis + local JSON transcripts |
| Ideas collection | Upsert to Qdrant `ideas` when STUCK synthesis fires |
| Strike voice | Two sequential `output_audio` calls |
| CIRCULAR / ARGUING | GPT classifier only (no Redis heuristics) |

---

## API integration corrections (implemented)

1. **Webhook verification:** `webhook-id`, `webhook-timestamp`, `webhook-signature`; sign `{id}.{ts}.{body}` with `whsec_` key → see `backend/webhook_verify.py`
2. **Meeting end:** event `bot.done` (not `bot_status == done`)
3. **Two webhook routes:** `/webhook/transcript` (realtime) + `/webhook/recall` (dashboard)
4. **Create Bot:** `metadata.meeting_id`, `realtime_endpoints`, `automatic_audio_output`
5. **`transcript.data`:** `words` is an array — join `text` fields
6. **Qdrant:** four `search()` calls with `score_threshold=0.82`

---

## Directory structure

```
ai_coworker/
├── backend/
│   ├── main.py
│   ├── pipeline.py
│   ├── recall_client.py
│   ├── webhook_verify.py
│   ├── intent_classifier.py
│   ├── qdrant_search.py
│   ├── embeddings.py
│   ├── voice_gate.py
│   ├── idea_generator.py
│   ├── session_state.py
│   ├── transcript_cache.py
│   ├── tts.py
│   ├── web_search.py
│   ├── config.py
│   └── models.py
├── ingestion/
│   ├── ingest_docs.py
│   └── ingest_meetings.py
├── transcripts/
├── prompts/
├── plan.md
├── .env.example
├── docker-compose.yml
└── requirements.txt
```

---

## Core features (summary)

1. **Live transcription** — Recall `transcript.data` → buffer → 10s flush → pipeline (≥15 words)
2. **Parallel pipeline** — embed, Qdrant search, intent, Redis update (`asyncio.gather`, `return_exceptions=True`)
3. **Document surfacing** — similarity > 0.82, GPT score, Zoom chat (Week 2)
4. **Decision + drift** — Qdrant `decisions`, voice on contradiction (Week 2)
5. **Tasks** — chat `✅ Task: owner — description` (Week 2)
6. **Idea mode** — 6 stuck states, confirmation window, precompute during PENDING
7. **Agenda** — GCal description → GPT tasks → chat on join (Week 2)
8. **Pre/post email** — Resend + APScheduler (Week 2)

---

## Confirmation window (voice_gate)

States: NONE → PENDING → CONFIRMED → COOLDOWN (90s global).

| State | Window (s) |
|---|---|
| ARGUING | 30 |
| STUCK / CIRCULAR / PARALYZED | 20 |
| CONFUSED / CRASH | 15 |

DECISION_DRIFT and WRAP_UP bypass confirmation (Week 2).

---

## Environment variables

See [`.env.example`](.env.example). Use `RECALL_VERIFICATION_SECRET=whsec_...` from Recall dashboard (API Keys → Create Workspace Secret).

---

## Python version

**3.11 only** — use `python3.11 -m venv .venv` (see `.python-version`). `llvmlite==0.43.0` is pinned for prebuilt macOS wheels (no Homebrew LLVM required).

## Human setup checklist

- Recall.ai: API key, region, workspace secret, enable Recall.ai Transcription
- Qdrant Cloud cluster + Redis (`docker compose up -d` locally)
- Google OAuth refresh token for Calendar + Drive
- Resend domain or verified recipient emails
- Deploy or ngrok static URL → `PUBLIC_BASE_URL`
- Dashboard webhook → `/webhook/recall` subscribed to `bot.done`
- Per-bot realtime URL → `/webhook/transcript`

---

## Build timeline

### Week 1 — Foundation (in progress)
- [x] Project scaffold + corrected Recall webhooks
- [x] `transcript_cache`, `embeddings`, `qdrant_search`, `ingest_docs` / `ingest_meetings`
- [ ] Recall POC: join Zoom, chat, `output_audio`
- [ ] Intent classifier tuning

### Week 2 — Intelligence
- Full `pipeline.route`, document_surfer, decision_tracker, task_tracker
- `scheduler.py`, `email_sender`, agenda_builder

### June 1 — Demo polish

---

*Full feature tables, demo script (9 beats), and Qdrant schemas are in the original hackathon spec — preserved here in summary form. Implementation follows this document + README.*
