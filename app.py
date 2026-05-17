from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from openai import OpenAI
import httpx
import os
import uuid
from datetime import datetime, timezone

app = FastAPI(title="TerrellOS Backend", version="7.1.0-voice")
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ELEVENLABS VOICE ROUTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import os
import base64
import httpx
from fastapi import HTTPException

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv(
    "ELEVENLABS_VOICE_ID",
    "EXAVITQu4vr4xnSDxMaL"
)

@app.post("/v1/voice/speak")
async def voice_speak(payload: dict):

    text = payload.get("text", "").strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Missing text"
        )

    if not ELEVENLABS_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ELEVENLABS_API_KEY missing"
        )

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }

    body = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.85,
            "style": 0.35,
            "use_speaker_boost": True
        }
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            url,
            headers=headers,
            json=body
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    audio_base64 = base64.b64encode(
        response.content
    ).decode("utf-8")

    return {
        "success": True,
        "provider": "elevenlabs",
        "voice_id": ELEVENLABS_VOICE_ID,
        "audio_mime_type": "audio/mpeg",
        "audio_base64": audio_base64
    }
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# ── ElevenLabs TTS ────────────────────────────────────────────────────────────
ELEVEN_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVEN_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel
ELEVEN_MODEL    = os.environ.get("ELEVENLABS_MODEL",    "eleven_turbo_v2")
ELEVEN_BASE     = "https://api.elevenlabs.io/v1"

async def elevenlabs_tts(text: str, voice_id: str | None = None) -> bytes | None:
    """Call ElevenLabs TTS. Returns raw MP3 bytes or None if unconfigured/failed."""
    if not ELEVEN_API_KEY:
        return None
    vid = voice_id or ELEVEN_VOICE_ID
    async with httpx.AsyncClient(timeout=20.0) as hc:
        r = await hc.post(
            f"{ELEVEN_BASE}/text-to-speech/{vid}",
            headers={"xi-api-key": ELEVEN_API_KEY, "Accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": ELEVEN_MODEL,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
        )
    if r.status_code == 200:
        return r.content
    print(f"[ElevenLabs] TTS error {r.status_code}: {r.text[:200]}", flush=True)
    return None

def audio_to_data_url(audio_bytes: bytes) -> str:
    """Base64-encode MP3 bytes as an inline data URL for direct <audio> playback."""
    import base64
    return "data:audio/mpeg;base64," + base64.b64encode(audio_bytes).decode()


SESSIONS_DB: Dict[str, Dict[str, Any]] = {}
PROFILES_DB: Dict[str, Dict[str, Any]] = {}
CONSENTS_DB: Dict[str, Dict[str, Any]] = {}
FRAGMENTS_DB: List[Dict[str, Any]] = []
VOICE_DB: Dict[str, Dict[str, Any]] = {}
UPLOADS_DB: List[Dict[str, Any]] = []


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return str(uuid.uuid4())


class ChatMessage(BaseModel):
    role: Optional[str] = "user"
    content: Optional[str] = ""


class ChatRequest(BaseModel):
    message: Optional[str] = None
    prompt: Optional[str] = None
    messages: Optional[List[ChatMessage]] = []
    history: Optional[List[Dict[str, Any]]] = []
    tool_type: Optional[str] = "general"
    project_name: Optional[str] = "Untitled"
    save: Optional[bool] = True


class SessionStartReq(BaseModel):
    memory_profile_id: Optional[str] = None
    user_id: Optional[str] = None
    started_at: Optional[str] = None
    camera_active: Optional[bool] = False
    voice_active: Optional[bool] = False
    consent_confirmed: Optional[bool] = False
    device_type: Optional[str] = None


class SessionEndReq(BaseModel):
    session_id: str
    ended_at: Optional[str] = None
    duration_sec: Optional[int] = 0
    prompts_answered: Optional[int] = 0
    prompts_skipped: Optional[int] = 0
    notes: Optional[str] = None


class FrameReq(BaseModel):
    session_id: str
    timestamp: Optional[str] = None
    frame_data: Optional[str] = None
    emotion_hint: Optional[str] = None


class AudioChunkReq(BaseModel):
    session_id: str
    timestamp: Optional[str] = None
    audio_data: Optional[str] = None
    duration_ms: Optional[int] = 0
    provider: Optional[str] = "pending"


class TranscriptReq(BaseModel):
    session_id: Optional[str] = None
    memory_profile_id: Optional[str] = None
    user_id: Optional[str] = None
    prompt: Optional[str] = None
    response_text: Optional[str] = None
    audio_ref: Optional[str] = None
    video_ref: Optional[str] = None
    duration_sec: Optional[int] = 0
    emotion_detected: Optional[str] = None
    confidence: Optional[float] = None
    category: Optional[str] = "other"
    is_pinned: Optional[bool] = False


class TranscribeReq(BaseModel):
    session_id: Optional[str] = None
    memory_profile_id: Optional[str] = None
    audio_url: Optional[str] = None
    prompt_context: Optional[str] = None


class ConsentReq(BaseModel):
    user_id: Optional[str] = None
    memory_profile_id: Optional[str] = None
    consent_timestamp: Optional[str] = None
    consent_version: Optional[str] = "1.0"
    camera_approved: Optional[bool] = False
    mic_approved: Optional[bool] = False
    voice_analysis: Optional[bool] = False
    memory_storage: Optional[bool] = False
    ai_training: Optional[bool] = False
    avatar_generation: Optional[bool] = False
    future_playback: Optional[bool] = False
    signature_text: Optional[str] = None
    user_agent: Optional[str] = None


class ExportReq(BaseModel):
    memory_profile_id: str
    user_id: Optional[str] = None
    format: Optional[str] = "json"


class DeleteReq(BaseModel):
    memory_profile_id: str
    user_id: Optional[str] = None
    confirm: Optional[bool] = False


class VoiceSampleCountReq(BaseModel):
    user_id: Optional[str] = None
    count: Optional[int] = 0


class VoiceTrainReq(BaseModel):
    user_id: Optional[str] = None
    memory_profile_id: Optional[str] = None
    sample_count: Optional[int] = 0


class VoiceCloneReq(BaseModel):
    user_id: Optional[str] = None
    memory_profile_id: Optional[str] = None
    provider: Optional[str] = "pending"


class CompanionRespondReq(BaseModel):
    user_id: Optional[str] = None
    memory_profile_id: Optional[str] = None
    message: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = []


class CompanionVoiceReq(BaseModel):
    user_id: Optional[str] = None
    text: Optional[str] = None
    voice_id: Optional[str] = None
    provider: Optional[str] = "pending"


@app.get("/")
async def root():
    return {
        "status": "TerrellOS backend live",
        "version": "7.1.0-voice",
        "environment": "production",
        "platform": "Heavenly Eternal Echo",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "backend": "online",
        "version": "7.1.0-voice",
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "elevenlabs_configured": bool(ELEVEN_API_KEY),
        "voice_provider": "elevenlabs" if ELEVEN_API_KEY else "unconfigured",
        "memory": {
            "profiles": len(PROFILES_DB),
            "sessions": len(SESSIONS_DB),
            "fragments": len(FRAGMENTS_DB),
            "voice_profiles": len(VOICE_DB),
        },
        "timestamp": now(),
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    msg = req.message or req.prompt

    if not msg and req.messages:
        msg = req.messages[-1].content or ""

    if not msg and req.history:
        msg = req.history[-1].get("content", "")

    if not msg:
        raise HTTPException(status_code=400, detail="No prompt received")

    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "success": True,
            "reply": f"Backend is live. OpenAI key is not configured yet. Received: {msg}",
            "status": "openai_not_configured",
        }

    system = (
        "You are TerrellOS AI — the intelligence behind Heavenly Eternal Echo. "
        "You help users preserve memories, stories, voice, identity, and legacy. "
        "Be warm, thoughtful, useful, and production-focused."
    )

    history_msgs = []
    for h in req.history or []:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            history_msgs.append({"role": h["role"], "content": h["content"]})

    messages = [{"role": "system", "content": system}]
    messages.extend(history_msgs)
    messages.append({"role": "user", "content": msg})

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1200,
            temperature=0.75,
        )
        return {
            "success": True,
            "reply": res.choices[0].message.content.strip(),
            "status": "success",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {str(e)}")


@app.post("/v1/memory/session/start")
async def session_start(req: SessionStartReq):
    session_id = uid()
    profile_id = req.memory_profile_id or uid()

    if profile_id not in PROFILES_DB:
        PROFILES_DB[profile_id] = {
            "id": profile_id,
            "user_id": req.user_id,
            "status": "active",
            "session_count": 0,
            "total_duration_sec": 0,
            "completion_pct": 0,
            "created_at": now(),
            "is_encrypted": True,
        }

    PROFILES_DB[profile_id]["session_count"] += 1
    PROFILES_DB[profile_id]["last_session_at"] = now()

    SESSIONS_DB[session_id] = {
        "id": session_id,
        "memory_profile_id": profile_id,
        "user_id": req.user_id,
        "status": "active",
        "started_at": req.started_at or now(),
        "ended_at": None,
        "duration_sec": 0,
        "prompts_answered": 0,
        "prompts_skipped": 0,
        "camera_active": req.camera_active,
        "voice_active": req.voice_active,
        "consent_confirmed": req.consent_confirmed,
        "device_type": req.device_type,
        "fragments": [],
    }

    return {
        "success": True,
        "session_id": session_id,
        "memory_profile_id": profile_id,
        "started_at": SESSIONS_DB[session_id]["started_at"],
        "status": "active",
        "message": "Session started. Begin sharing your story.",
    }


@app.post("/v1/memory/session/frame")
async def session_frame(req: FrameReq):
    if req.session_id not in SESSIONS_DB:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "session_id": req.session_id,
        "timestamp": req.timestamp or now(),
        "facial_analysis_status": "preparation_active",
        "message": "Frame received. Facial embedding pipeline in preparation.",
    }


@app.post("/v1/memory/session/audio")
async def session_audio(req: AudioChunkReq):
    if req.session_id not in SESSIONS_DB:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "session_id": req.session_id,
        "duration_ms": req.duration_ms,
        "provider": req.provider,
        "stt_status": "preparation_active",
        "voiceprint_status": "preparation_active",
        "message": "Audio received. STT provider not fully configured yet.",
    }


@app.post("/v1/memory/session/transcript")
async def session_transcript(req: TranscriptReq):
    frag_id = uid()

    fragment = {
        "id": frag_id,
        "session_id": req.session_id,
        "memory_profile_id": req.memory_profile_id,
        "user_id": req.user_id,
        "prompt": req.prompt,
        "response_text": req.response_text,
        "audio_ref": req.audio_ref,
        "video_ref": req.video_ref,
        "duration_sec": req.duration_sec,
        "emotion_detected": req.emotion_detected,
        "confidence": req.confidence,
        "category": req.category,
        "is_pinned": req.is_pinned,
        "reviewed": False,
        "created_at": now(),
    }

    FRAGMENTS_DB.append(fragment)

    if req.session_id and req.session_id in SESSIONS_DB:
        SESSIONS_DB[req.session_id]["fragments"].append(frag_id)
        SESSIONS_DB[req.session_id]["prompts_answered"] += 1

    if req.memory_profile_id and req.memory_profile_id in PROFILES_DB:
        answered = len(
            [f for f in FRAGMENTS_DB if f.get("memory_profile_id") == req.memory_profile_id]
        )
        PROFILES_DB[req.memory_profile_id]["completion_pct"] = round(
            min(100, (answered / 15) * 100), 1
        )

    return {
        "success": True,
        "fragment_id": frag_id,
        "category": req.category,
        "completion_pct": PROFILES_DB.get(req.memory_profile_id or "", {}).get(
            "completion_pct", 0
        ),
        "message": "Story fragment saved to your Eternal Echo.",
    }


@app.post("/v1/memory/session/end")
async def session_end(req: SessionEndReq):
    session = SESSIONS_DB.get(req.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.update(
        {
            "status": "complete",
            "ended_at": req.ended_at or now(),
            "duration_sec": req.duration_sec,
            "prompts_answered": req.prompts_answered,
            "prompts_skipped": req.prompts_skipped,
            "notes": req.notes,
        }
    )

    profile = PROFILES_DB.get(session.get("memory_profile_id", ""))

    if profile:
        profile["total_duration_sec"] = profile.get("total_duration_sec", 0) + (
            req.duration_sec or 0
        )
        profile["last_session_at"] = now()

    return {
        "success": True,
        "session_id": req.session_id,
        "status": "complete",
        "duration_sec": req.duration_sec,
        "prompts_answered": req.prompts_answered,
        "fragments_saved": len(session.get("fragments", [])),
        "memory_synthesis_status": "preparation_active",
        "message": "Session complete. Your memories are being preserved.",
    }


@app.get("/v1/memory/profile/{profile_id}")
async def get_profile(profile_id: str):
    profile = PROFILES_DB.get(profile_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Memory profile not found")

    fragments = [f for f in FRAGMENTS_DB if f.get("memory_profile_id") == profile_id]
    sessions = [
        s for s in SESSIONS_DB.values() if s.get("memory_profile_id") == profile_id
    ]

    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for frag in fragments:
        by_cat.setdefault(frag.get("category", "other"), []).append(frag)

    return {
        "success": True,
        "profile": profile,
        "sessions": sessions,
        "fragments": fragments,
        "fragments_by_category": by_cat,
        "total_fragments": len(fragments),
        "total_sessions": len(sessions),
        "voice_profile_status": "preparation_active",
        "facial_profile_status": "preparation_active",
        "ai_synthesis_status": "preparation_active",
    }


@app.post("/v1/memory/transcribe")
async def transcribe_audio_route(req: TranscribeReq):
    return {
        "success": True,
        "transcript": None,
        "emotion_detected": None,
        "transcription_status": "preparation_active",
        "message": "Transcription backend in preparation. Configure STT provider to activate.",
        "supported_providers": ["whisper", "deepgram", "assemblyai", "openai_realtime"],
    }


@app.post("/v1/memory/consent")
async def record_consent(req: ConsentReq):
    consent_id = uid()

    record = {
        "id": consent_id,
        "user_id": req.user_id,
        "memory_profile_id": req.memory_profile_id,
        "consent_timestamp": req.consent_timestamp or now(),
        "consent_version": req.consent_version,
        "camera_approved": req.camera_approved,
        "mic_approved": req.mic_approved,
        "voice_analysis": req.voice_analysis,
        "memory_storage": req.memory_storage,
        "ai_training": req.ai_training,
        "avatar_generation": req.avatar_generation,
        "future_playback": req.future_playback,
        "signature_text": req.signature_text,
        "user_agent": req.user_agent,
        "recorded_at": now(),
    }

    CONSENTS_DB[consent_id] = record

    return {
        "success": True,
        "consent_id": consent_id,
        "recorded_at": record["recorded_at"],
        "all_approved": all(
            [
                req.camera_approved,
                req.mic_approved,
                req.voice_analysis,
                req.memory_storage,
                req.ai_training,
                req.avatar_generation,
                req.future_playback,
            ]
        ),
        "message": "Consent recorded. Your session may now begin.",
    }


@app.post("/v1/memory/export")
async def export_memory(req: ExportReq):
    profile = PROFILES_DB.get(req.memory_profile_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Memory profile not found")

    fragments = [
        f for f in FRAGMENTS_DB if f.get("memory_profile_id") == req.memory_profile_id
    ]
    sessions = [
        s for s in SESSIONS_DB.values()
        if s.get("memory_profile_id") == req.memory_profile_id
    ]
    consents = [
        c for c in CONSENTS_DB.values()
        if c.get("memory_profile_id") == req.memory_profile_id
    ]

    if req.format == "pdf":
        return {
            "success": False,
            "pdf_status": "preparation_active",
            "message": "PDF export in preparation. JSON available now.",
        }

    return {
        "success": True,
        "export": {
            "export_id": uid(),
            "exported_at": now(),
            "memory_profile_id": req.memory_profile_id,
            "profile": profile,
            "sessions": sessions,
            "fragments": fragments,
            "consents": consents,
        },
        "total_fragments": len(fragments),
        "message": "Memory export complete.",
    }


@app.delete("/v1/memory/delete")
async def delete_memory(req: DeleteReq):
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Deletion requires confirm=true. This is permanent.",
        )

    profile = PROFILES_DB.get(req.memory_profile_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Memory profile not found")

    del PROFILES_DB[req.memory_profile_id]

    deleted_sessions = [
        k for k, s in list(SESSIONS_DB.items())
        if s.get("memory_profile_id") == req.memory_profile_id
    ]

    for k in deleted_sessions:
        del SESSIONS_DB[k]

    deleted_fragments_count = len(
        [f for f in FRAGMENTS_DB if f.get("memory_profile_id") == req.memory_profile_id]
    )

    FRAGMENTS_DB[:] = [
        f for f in FRAGMENTS_DB if f.get("memory_profile_id") != req.memory_profile_id
    ]

    deleted_consents = [
        k for k, c in list(CONSENTS_DB.items())
        if c.get("memory_profile_id") == req.memory_profile_id
    ]

    for k in deleted_consents:
        del CONSENTS_DB[k]

    return {
        "success": True,
        "memory_profile_id": req.memory_profile_id,
        "deleted": {
            "profile": 1,
            "sessions": len(deleted_sessions),
            "fragments": deleted_fragments_count,
            "consents": len(deleted_consents),
        },
        "message": "All memory data permanently deleted.",
    }


@app.post("/v1/memory/voice/sample-count")
async def voice_sample_count(req: VoiceSampleCountReq):
    user_id = req.user_id or "unknown"

    if user_id not in VOICE_DB:
        VOICE_DB[user_id] = {
            "user_id": user_id,
            "sample_count": 0,
            "status": "collecting",
            "created_at": now(),
        }

    VOICE_DB[user_id]["sample_count"] = req.count or 0
    VOICE_DB[user_id]["updated_at"] = now()

    return {
        "success": True,
        "user_id": user_id,
        "sample_count": req.count,
        "voice_profile_status": "collecting"
        if (req.count or 0) < 5
        else "ready_for_training",
    }


@app.post("/v1/memory/voice/train")
async def voice_train(req: VoiceTrainReq):
    return {
        "success": True,
        "training_status": "preparation_active",
        "message": "Voice model training in preparation. Configure a voice provider to activate.",
        "supported_providers": ["elevenlabs", "resemble", "playht", "tortoise"],
    }


@app.post("/v1/memory/voice/clone")
async def voice_clone(req: VoiceCloneReq):
    return {
        "success": True,
        "clone_status": "preparation_active",
        "message": "Voice cloning in preparation. Configure ELEVENLABS_API_KEY or equivalent to activate.",
    }


@app.post("/v1/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    file_id = uid()

    record = {
        "id": file_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
        "uploaded_at": now(),
    }

    UPLOADS_DB.append(record)

    return {
        "success": True,
        "file_id": file_id,
        "file_url": f"/v1/files/{file_id}",
        "filename": file.filename,
        "size_bytes": len(content),
        "storage_status": "in_memory",
        "message": "File received. Persistent storage in preparation.",
    }


@app.post("/v1/companion/respond")
async def companion_respond(req: CompanionRespondReq):
    if not req.message:
        raise HTTPException(status_code=400, detail="No message received")

    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "success": True,
            "reply": f"Companion backend is live. OpenAI key is not configured yet. Received: {req.message}",
            "voice_synthesis_status": "preparation_active",
        }

    system = (
        "You are an Eternal Echo — a warm, emotionally intelligent AI companion "
        "modeled on a real person's memories, values, and conversational style. "
        "Respond with care, warmth, and dignity."
    )

    history_msgs = []
    for h in req.history or []:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            history_msgs.append({"role": h["role"], "content": h["content"]})

    messages = [{"role": "system", "content": system}]
    messages.extend(history_msgs)
    messages.append({"role": "user", "content": req.message})

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=600,
            temperature=0.85,
        )
        return {
            "success": True,
            "reply": res.choices[0].message.content.strip(),
            "voice_synthesis_status": "preparation_active",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Companion response error: {str(e)}")


@app.post("/v1/companion/voice")
async def companion_voice(req: CompanionVoiceReq):
    text = (req.message or "").strip()
    if not text:
        raise HTTPException(400, "message is required")
    if not ELEVEN_API_KEY:
        return {
            "success": False,
            "audio_data_url": None,
            "voice_synthesis_status": "unconfigured",
            "message": "Set ELEVENLABS_API_KEY in Render → Environment to activate voice.",
        }
    audio = await elevenlabs_tts(text, voice_id=req.voice_id)
    if audio:
        return {
            "success": True,
            "audio_data_url": audio_to_data_url(audio),
            "voice_synthesis_status": "complete",
            "provider": "elevenlabs",
            "voice_id": req.voice_id or ELEVEN_VOICE_ID,
            "bytes": len(audio),
        }
    return {
        "success": False,
        "audio_data_url": None,
        "voice_synthesis_status": "error",
        "message": "ElevenLabs TTS failed — check API key and voice ID in Render env vars.",
    }


@app.post("/v1/companion/voice/auto")
async def companion_voice_auto(req: CompanionVoiceReq):
    """One-shot: generate AI text reply + synthesize to voice. Returns both."""
    text_input = (req.message or "").strip()
    if not text_input:
        raise HTTPException(400, "message is required")

    # Step 1: AI text response
    text_reply = text_input
    if client:
        try:
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": (
                        "You are Eternal Echo — a warm, reflective AI companion that helps "
                        "people preserve and revisit their most meaningful memories. "
                        "Respond with warmth and depth in 1-3 sentences."
                    )},
                    {"role": "user", "content": text_input},
                ],
                max_tokens=200, temperature=0.8,
            )
            text_reply = r.choices[0].message.content.strip()
        except Exception as e:
            print(f"[voice/auto] OpenAI error: {e}", flush=True)

    # Step 2: Voice synthesis
    audio       = await elevenlabs_tts(text_reply, voice_id=req.voice_id) if ELEVEN_API_KEY else None
    data_url    = audio_to_data_url(audio) if audio else None

    return {
        "success": True,
        "text_reply": text_reply,
        "audio_data_url": data_url,
        "voice_synthesis_status": "complete" if data_url else ("unconfigured" if not ELEVEN_API_KEY else "error"),
        "provider": "elevenlabs" if data_url else None,
    }


@app.post("/v1/admin/check-grant")
async def admin_check_grant():
    return {
        "success": True,
        "message": "Admin check acknowledged.",
    }


@app.get("/v1/admin/stats")
async def admin_stats():
    return {
        "success": True,
        "profiles": len(PROFILES_DB),
        "sessions": len(SESSIONS_DB),
        "fragments": len(FRAGMENTS_DB),
        "voice_profiles": len(VOICE_DB),
        "uploads": len(UPLOADS_DB),
        "consents": len(CONSENTS_DB),
        "timestamp": now(),
    }
