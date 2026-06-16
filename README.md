# AI Voice Orchestration System

A production-style MVP that turns a text prompt into spoken audio:

1. `POST /generate` accepts a prompt and enqueues a job on RabbitMQ.
2. A worker pulls the job, asks an LLM (Ollama / Groq / HuggingFace) for a
   response, sends that text to ElevenLabs TTS, persists the audio, and
   updates the job record.
3. Clients poll `GET /status/{job_id}` and fetch the audio via
   `GET /result/{job_id}` once the job is `completed`.

The codebase is structured so each external integration is isolated behind a
small interface, retries are centralized, and the API and worker scale
independently.

## Architecture

```
            ┌───────────────┐     publish (durable, persistent)
 client ──▶ │  FastAPI API  │ ───────────────────────────────┐
            │  /generate    │                                 ▼
            │  /status      │                       ┌──────────────────┐
            │  /result      │                       │     RabbitMQ     │
            │  /audio/*     │ ◀────── read ──────── │  voice.jobs  +   │
            └───────┬───────┘                       │  dead-letter DLX │
                    │ read/write                    └─────────┬────────┘
                    ▼                                         │ consume
            ┌───────────────┐                                 ▼
            │  Job store    │◀──────── read/write ────┌──────────────┐
            │ (JSON files,  │                         │   Worker     │
            │  shared vol)  │                         │  pipeline    │
            └───────────────┘                         │              │
                    ▲                                 │  1. LLM      │──▶ Ollama / Groq / HF
            ┌───────┴───────┐                         │  2. TTS      │──▶ ElevenLabs
            │ Audio storage │◀──── write audio ───────│  3. Storage  │
            │ (shared vol)  │                         └──────────────┘
            └───────────────┘
```

Key design choices:

- **Pluggable LLM provider** via `LLM_PROVIDER` (`ollama` | `groq` | `huggingface`).
  Each provider implements `LLMService` (`app/llm/base.py`); a factory wires
  the configured one (`app/llm/factory.py`).
- **Pluggable storage** behind `AudioStorage` (`app/storage/base.py`) — the
  local implementation can be swapped for S3/MinIO without touching the
  pipeline.
- **Centralized retry** with exponential backoff for all outbound HTTP calls
  (`app/retry.py`, built on `tenacity`). 429/5xx/timeouts/transport errors
  are retried; everything else fails fast.
- **Durable queue + DLQ**: messages are persistent, the work queue is
  declared with a dead-letter exchange so poisoned jobs do not loop forever
  (`app/messaging/rabbitmq.py`).
- **Idempotent worker**: jobs already `completed` are skipped; audio files
  are keyed by `job_id` so retries overwrite cleanly.
- **Horizontal scale**: workers are stateless — run as many as you want
  (`docker compose up --scale worker=4`); RabbitMQ load-balances delivery
  and `prefetch=1` keeps work evenly distributed.
- **Structured logging** with `job_id` bound into every log line emitted
  during a job's lifecycle (`app/logging_config.py`).

## Project layout

```
app/
├── api/                  # FastAPI app + routes
│   ├── main.py
│   └── routes/{generate,jobs}.py
├── worker/               # async consumer + per-message handler
│   ├── main.py
│   └── handler.py
├── messaging/            # RabbitMQ client + topology (aio-pika)
├── llm/                  # LLM provider interface + ollama/groq/huggingface
├── tts/                  # ElevenLabs TTS wrapper
├── storage/              # Audio storage abstraction (local fs impl)
├── jobs/                 # File-backed JobStore (atomic writes)
├── config.py             # pydantic-settings env config
├── logging_config.py     # structured logging
├── models.py             # pydantic schemas + job record
└── retry.py              # shared tenacity retry policy
```

## Running locally

Requirements: Docker + Docker Compose. Nothing else.

```bash
cp .env.example .env
# Fill in at minimum:
#   ELEVENLABS_API_KEY=...
# If using Groq or HuggingFace, also set the matching keys and
# LLM_PROVIDER=groq | huggingface.

docker compose up --build
```

The first boot of the `ollama` service downloads the model defined by
`OLLAMA_MODEL` (default `llama3.2:1b`, ~1 GB). Subsequent boots reuse the
volume.

Services on the host:

| Service       | URL                                |
|---------------|------------------------------------|
| API           | http://localhost:8000              |
| API docs      | http://localhost:8000/docs         |
| Audio files   | http://localhost:8000/audio/<file> |
| RabbitMQ UI   | http://localhost:15672 (guest/guest) |
| Ollama        | http://localhost:11434             |

## API

### `POST /generate`

```bash
curl -s -X POST http://localhost:8000/generate \
  -H 'content-type: application/json' \
  -d '{"prompt": "Explain what a webhook is in one sentence."}'
# {"job_id":"a1b2...","status":"queued"}
```

Optional `voice_id` overrides the server-default ElevenLabs voice:

```bash
curl -s -X POST http://localhost:8000/generate \
  -H 'content-type: application/json' \
  -d '{"prompt": "Thanks for calling.", "voice_id": "EXAVITQu4vr4xnSDxMaL"}'
```

### `GET /status/{job_id}`

```bash
curl -s http://localhost:8000/status/a1b2...
# {"job_id":"a1b2...","status":"processing","error":null,"updated_at":"..."}
```

Status values: `queued`, `processing`, `completed`, `failed`.

### `GET /result/{job_id}`

```bash
curl -s http://localhost:8000/result/a1b2...
# {"job_id":"...","status":"completed",
#  "generated_text":"...",
#  "audio_url":"http://localhost:8000/audio/a1b2....mp3"}

curl -O http://localhost:8000/audio/a1b2....mp3
```

Returns `409 Conflict` if the job is still `queued`/`processing` and `500`
with the error message if it `failed`.

## Scaling & operations

- **More workers**: `docker compose up -d --scale worker=4`.
- **Switching LLM provider**: set `LLM_PROVIDER` in `.env` and restart the
  worker (`docker compose restart worker`). No code change required.
- **Dead-letter inspection**: poisoned messages land on the `voice.jobs.dead`
  queue and can be browsed in the RabbitMQ management UI.
- **Stateless services**: the only shared state is the `app_data` volume
  (job records + audio files). Replace it with Redis/Postgres and S3 for a
  fully horizontal deployment.

## Local development without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' .env | xargs)   # or use direnv / dotenv
# Terminal 1
uvicorn app.api.main:app --reload
# Terminal 2
python -m app.worker.main
```

You still need a running RabbitMQ (`docker run -p 5672:5672 -p 15672:15672 rabbitmq:3.13-management`)
and either a running Ollama or valid Groq/HF credentials.
