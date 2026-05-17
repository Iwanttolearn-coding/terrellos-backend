from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from openai import OpenAI
import os
import uuid
import base64
import httpx

app = FastAPI(
    title="TerrellOS Backend",
    version="7.1.0-prod",
    description="TerrellOS / Heavenly Eternal Echo production AI backend"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MEMORY_SESSIONS: Dict[str, Dict[str, Any]] = {}
MEMORY_PROFILES: Dict[str, Dict[str, Any]] = {}
UPLOADS: Dict[str, Dict[str, Any]] = {}
CONSENTS: Dict[str, Dict[str, Any]] = {}


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "terrell"


class SessionStartRequest(BaseModel):
    user_id: str
    consent_confirmed: bool = False
    voice_active: bool = False
    camera_active: bool = False


class SessionFrameRequest(BaseModel):
    session_id: str
    frame_data: Optional[str] = None
    note: Optional[str] = None


class SessionTranscriptRequest(BaseModel):
    session_id: str
    transcript: str


class SessionEndRequest(BaseModel):
    session_id: str


class ConsentRequest(BaseModel):
    user_id: str
    consent_confirmed: bool
    consent_type: Optional[str] = "memory_voice_camera"


class MemoryDeleteRequest(BaseModel):
    user_id: str


class VoiceSampleCountRequest(BaseModel):
    user_id: str


class VoiceTrainRequest(BaseModel):
    user_id: str
    profile_id: Optional[str] = None


class VoiceCloneRequest(BaseModel):
    user_id: str
    voice_name: Optional[str] = "Heavenly Eternal Echo Voice"


class CompanionRequest(BaseModel):
    message: str
    user_id: Optional[str] = "terrell"
    profile_id: Optional[str] = "default"


class VoiceSpeakRequest(BaseModel):
    text: str


class AdminGrantRequest(BaseModel):
    email: str


@app.get("/")
async def root():
    return {
        "success": True,
        "service": "TerrellOS Backend",
        "status": "online",
        "version": "7.1.0-prod",
        "docs": "/docs",
        "health": "/health",
        "time": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health")
async def health():
    return {
        "success": True,
        "status": "healthy",
        "render": "online",
        "fastapi": "online",
        "openai_configured": bool(OPENAI_API_KEY),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "multipart_uploads": "ready",
        "time": datetime.now(timezone.utc).isoformat()
    }


@app.post("/chat")
async def chat(payload: ChatRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Missing message")

    if not openai_client:
        return {
            "success": True,
            "mode": "fallback",
            "reply": f"TerrellOS received your message: {payload.message}",
            "note": "OPENAI_API_KEY is not configured yet."
        }

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are TerrellOS, the backend intelligence layer for Heavenly Eternal Echo."
                },
                {
                    "role": "user",
                    "content": payload.message
                }
            ],
            temperature=0.7
        )

        reply = response.choices[0].message.content

        return {
            "success": True,
            "reply": reply
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/memory/session/start")
async def memory_session_start(payload: SessionStartRequest):
    if not payload.consent_confirmed:
        raise HTTPException(status_code=400, detail="Consent is required before starting memory session")

    session_id = str(uuid.uuid4())

    MEMORY_SESSIONS[session_id] = {
        "session_id": session_id,
        "user_id": payload.user_id,
        "consent_confirmed": payload.consent_confirmed,
        "voice_active": payload.voice_active,
        "camera_active": payload.camera_active,
        "frames": [],
        "audio": [],
        "transcripts": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "status": "active"
    }

    if payload.user_id not in MEMORY_PROFILES:
        MEMORY_PROFILES[payload.user_id] = {
            "profile_id": payload.user_id,
            "user_id": payload.user_id,
            "memory_fragments": [],
            "voice_samples": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    return {
        "success": True,
        "session_id": session_id,
        "message": "Memory session started"
    }


@app.post("/v1/memory/session/frame")
async def memory_session_frame(payload: SessionFrameRequest):
    session = MEMORY_SESSIONS.get(payload.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    frame = {
        "id": str(uuid.uuid4()),
        "frame_data": payload.frame_data,
        "note": payload.note,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    session["frames"].append(frame)

    return {
        "success": True,
        "frame_id": frame["id"],
        "message": "Frame saved"
    }


@app.post("/v1/memory/session/audio")
async def memory_session_audio(session_id: str, file: UploadFile = File(...)):
    session = MEMORY_SESSIONS.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = await file.read()
    audio_id = str(uuid.uuid4())

    audio_record = {
        "id": audio_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    session["audio"].append(audio_record)

    return {
        "success": True,
        "audio_id": audio_id,
        "message": "Audio received"
    }


@app.post("/v1/memory/session/transcript")
async def memory_session_transcript(payload: SessionTranscriptRequest):
    session = MEMORY_SESSIONS.get(payload.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    transcript_record = {
        "id": str(uuid.uuid4()),
        "transcript": payload.transcript,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    session["transcripts"].append(transcript_record)

    user_id = session["user_id"]

    if user_id in MEMORY_PROFILES:
        MEMORY_PROFILES[user_id]["memory_fragments"].append(transcript_record)

    return {
        "success": True,
        "transcript_id": transcript_record["id"],
        "message": "Transcript saved"
    }


@app.post("/v1/memory/session/end")
async def memory_session_end(payload: SessionEndRequest):
    session = MEMORY_SESSIONS.get(payload.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["status"] = "ended"
    session["ended_at"] = datetime.now(timezone.utc).isoformat()

    return {
        "success": True,
        "session_id": payload.session_id,
        "message": "Memory session ended"
    }


@app.get("/v1/memory/profile/{profile_id}")
async def memory_profile(profile_id: str):
    profile = MEMORY_PROFILES.get(profile_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Memory profile not found")

    return {
        "success": True,
        "profile": profile
    }


@app.post("/v1/memory/transcribe")
async def memory_transcribe(file: UploadFile = File(...)):
    content = await file.read()

    return {
        "success": True,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "transcript": "Transcription placeholder ready. Connect Whisper/OpenAI audio transcription next."
    }


@app.post("/v1/memory/consent")
async def memory_consent(payload: ConsentRequest):
    CONSENTS[payload.user_id] = {
        "user_id": payload.user_id,
        "consent_confirmed": payload.consent_confirmed,
        "consent_type": payload.consent_type,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    return {
        "success": True,
        "message": "Consent saved",
        "consent": CONSENTS[payload.user_id]
    }


@app.post("/v1/memory/export")
async def memory_export(payload: MemoryDeleteRequest):
    profile = MEMORY_PROFILES.get(payload.user_id, {})

    return {
        "success": True,
        "user_id": payload.user_id,
        "export": profile
    }


@app.delete("/v1/memory/delete")
async def memory_delete(payload: MemoryDeleteRequest):
    MEMORY_PROFILES.pop(payload.user_id, None)

    sessions_to_delete = [
        session_id
        for session_id, session in MEMORY_SESSIONS.items()
        if session.get("user_id") == payload.user_id
    ]

    for session_id in sessions_to_delete:
        MEMORY_SESSIONS.pop(session_id, None)

    return {
        "success": True,
        "message": "Memory deleted",
        "user_id": payload.user_id
    }


@app.post("/v1/memory/voice/sample-count")
async def voice_sample_count(payload: VoiceSampleCountRequest):
    profile = MEMORY_PROFILES.get(payload.user_id, {})
    samples = profile.get("voice_samples", [])

    return {
        "success": True,
        "user_id": payload.user_id,
        "sample_count": len(samples),
        "ready_for_training": len(samples) >= 10
    }


@app.post("/v1/memory/voice/train")
async def voice_train(payload: VoiceTrainRequest):
    return {
        "success": True,
        "user_id": payload.user_id,
        "profile_id": payload.profile_id or payload.user_id,
        "status": "training_ready",
        "message": "Voice training route is live. Connect ElevenLabs voice cloning workflow next."
    }


@app.post("/v1/memory/voice/clone")
async def voice_clone(payload: VoiceCloneRequest):
    return {
        "success": True,
        "user_id": payload.user_id,
        "voice_name": payload.voice_name,
        "status": "clone_ready",
        "message": "Voice clone route is live. Real clone creation requires uploaded samples and ElevenLabs clone endpoint."
    }


@app.post("/v1/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    upload_id = str(uuid.uuid4())

    UPLOADS[upload_id] = {
        "upload_id": upload_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    return {
        "success": True,
        "upload_id": upload_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "message": "File uploaded successfully"
    }


@app.post("/v1/companion/respond")
async def companion_respond(payload: CompanionRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Missing message")

    if not openai_client:
        return {
            "success": True,
            "mode": "fallback",
            "reply": f"Heavenly Eternal Echo heard you: {payload.message}",
            "note": "OPENAI_API_KEY is not configured yet."
        }

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are Heavenly Eternal Echo, a warm AI legacy companion that responds with empathy, memory, dignity, and spiritual gentleness."
                },
                {
                    "role": "user",
                    "content": payload.message
                }
            ],
            temperature=0.75
        )

        reply = response.choices[0].message.content

        return {
            "success": True,
            "reply": reply,
            "profile_id": payload.profile_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/voice/speak")
async def voice_speak(payload: VoiceSpeakRequest):
    text = payload.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="Missing text")

    if not ELEVENLABS_API_KEY:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY missing")

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
        response = await client.post(url, headers=headers, json=body)

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    audio_base64 = base64.b64encode(response.content).decode("utf-8")

    return {
        "success": True,
        "provider": "elevenlabs",
        "voice_id": ELEVENLABS_VOICE_ID,
        "audio_mime_type": "audio/mpeg",
        "audio_base64": audio_base64
    }


@app.post("/v1/companion/voice")
async def companion_voice(payload: CompanionRequest):
    companion = await companion_respond(payload)

    voice_payload = VoiceSpeakRequest(text=companion["reply"])
    voice = await voice_speak(voice_payload)

    return {
        "success": True,
        "reply": companion["reply"],
        "voice": voice
    }


@app.post("/v1/companion/voice/auto")
async def companion_voice_auto(payload: CompanionRequest):
    companion = await companion_respond(payload)

    voice_payload = VoiceSpeakRequest(text=companion["reply"])
    voice = await voice_speak(voice_payload)

    return {
        "success": True,
        "mode": "auto",
        "reply": companion["reply"],
        "audio_mime_type": voice["audio_mime_type"],
        "audio_base64": voice["audio_base64"]
    }


@app.post("/v1/admin/check-grant")
async def admin_check_grant(payload: AdminGrantRequest):
    founder_emails = {
        "millzterrell210@icloud.com",
        "millzterrell5@gmail.com"
    }

    email = payload.email.lower().strip()
    is_founder = email in founder_emails

    return {
        "success": True,
        "email": email,
        "founder": is_founder,
        "role": "super_admin" if is_founder else "member",
        "plan": "heritage" if is_founder else "free",
        "access_level": "founder_override" if is_founder else "standard"
    }


@app.get("/v1/admin/stats")
async def admin_stats():
    return {
        "success": True,
        "status": "online",
        "sessions": len(MEMORY_SESSIONS),
        "profiles": len(MEMORY_PROFILES),
        "uploads": len(UPLOADS),
        "consents": len(CONSENTS),
        "openai_configured": bool(OPENAI_API_KEY),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "routes_live": [
            "/",
            "/health",
            "/chat",
            "/v1/memory/session/start",
            "/v1/memory/session/frame",
            "/v1/memory/session/audio",
            "/v1/memory/session/transcript",
            "/v1/memory/session/end",
            "/v1/memory/profile/{profile_id}",
            "/v1/memory/transcribe",
            "/v1/memory/consent",
            "/v1/memory/export",
            "/v1/memory/delete",
            "/v1/memory/voice/sample-count",
            "/v1/memory/voice/train",
            "/v1/memory/voice/clone",
            "/v1/upload",
            "/v1/companion/respond",
            "/v1/voice/speak",
            "/v1/companion/voice",
            "/v1/companion/voice/auto",
            "/v1/admin/check-grant",
            "/v1/admin/stats"
        ],
        "time": datetime.now(timezone.utc).isoformat()
    }
