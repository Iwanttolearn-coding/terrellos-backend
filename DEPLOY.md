# TerrellOS Backend — Deployment Guide

## Production Deploy (Fly.io)

Run this from your Kali laptop after any backend code change:

```bash
/home/tmills/.fly/bin/flyctl deploy -a terrellos-backend
```

Or if fly is in your PATH:
```bash
flyctl deploy -a terrellos-backend
```

## What was deployed in v9.0.0-orchestration

- `app.py` — Universal orchestration core with app identity middleware
- `routers/core.py` — `/v1/core/*` — AI chat per app identity
- `routers/memory.py` — `/v1/memory/*` — Session, fragments, profiles
- `routers/voice.py` — `/v1/voice/*` — TTS, transcription, voice list
- `routers/pastor.py` — `/v1/pastor/*` — Sermon, theology, discipleship
- `routers/echo.py` — `/v1/echo/*` — Companion AI, grief support, legacy
- `routers/design.py` — `/v1/design/*` — Image gen, print quotes, vectorize
- `routers/founder.py` — `/v1/founder/*` — Founder verify, audit logs
- `routers/admin.py` — `/v1/admin/*` — Stats, grants
- `routers/uploads.py` — `/v1/uploads/*` — File vault

## App Identity Middleware

Every request is resolved via `X-App-ID` header:

| App | Header Value |
|-----|-------------|
| TerrellOS | `terrellos` |
| Pastor AI Connect | `pastor-ai-connect` |
| Heavenly Eternal Echoes | `heavenly-eternal-echo` |
| All Around Customs | `all-around-customs` |

## Environment Variables (Fly.io secrets)

```
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
```

Set via: `flyctl secrets set OPENAI_API_KEY=sk-... -a terrellos-backend`

## CORS Allowed Origins

- https://app.tm-dezigns.com
- https://pastoraiconnect.com
- https://heavenlyeternalechoes.com
- https://allaroundcustoms.com
- https://kindredlovebirds.com
- https://residentsyncai.com
- http://localhost:5173
- http://localhost:3000

## Quick Health Check

```bash
curl https://terrellos-backend.fly.dev/health
curl https://terrellos-backend.fly.dev/v1/ecosystem
```
