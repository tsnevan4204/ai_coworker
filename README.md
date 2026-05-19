# Yaco

**Your AI coworker at every meeting.**

Ambient AI agent for Zoom: listens via Recall.ai, thinks in the background, and interjects via voice or chat when it matters.

## Quick start

**Requires Python 3.11** (see `.python-version`). Python 3.12 is not supported.

`llvmlite` is pinned to **0.43.0** so pip installs a prebuilt wheel on macOS. You do **not** need Homebrew LLVM unless that pin is removed.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
docker compose up -d
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Qdrant (optional until doc search / ingest)

For the **Recall join + transcript POC**, leave `QDRANT_URL` empty in `.env`.

When ready, create a free cluster at [cloud.qdrant.io](https://cloud.qdrant.io) and set:

```bash
QDRANT_URL=https://YOUR-CLUSTER.cloud.qdrant.io:6333
QDRANT_API_KEY=your-api-key
```

Restart the server and check `GET /health` — `qdrant.available` should be `true`.

## Webhooks (Recall dashboard)

| URL | Events |
|-----|--------|
| `{PUBLIC_BASE_URL}/webhook/transcript` | Per-bot `transcript.data` (set in Create Bot `realtime_endpoints`) |
| `{PUBLIC_BASE_URL}/webhook/recall` | Dashboard: `bot.done`, `transcript.done`, `transcript.failed` |

Create a **workspace verification secret** (`whsec_...`) in Recall → API Keys → set `RECALL_VERIFICATION_SECRET`.

## Ingest company docs

```bash
python ingestion/ingest_docs.py --folder-id YOUR_DRIVE_FOLDER_ID
```

## Google OAuth (one-time)

```bash
# Download OAuth client JSON from Google Cloud Console as credentials.json
python scripts/get_google_token.py
```

## Project layout

See [plan.md](plan.md) for the full hackathon spec and architecture.
