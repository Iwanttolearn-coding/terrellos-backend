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

from pastor_routes import router as pastor_router

app = FastAPI(
    title="TerrellOS Backend",
    version="8.0.0-full",
    description="Pastor AI Connect | Powered by TM Dezigns — Production Backend"
)

# ── CORS — env-driven allowlist ────────────────────────────────────────────
_CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "")
_CORS_ALLOWED = [o.strip() for o in _CORS_ORIGINS_ENV.split(",") if o.strip()] or [
    "https://app.tm-dezigns.org",
    "https://tm-dezigns.org",
    "https://terrellos-frontend.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ALLOWED,
    allow_origin_regex=r"https://.*\.vercel\.app",   # catch all Vercel preview URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pastor_router)

OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ELEVENLABS_MODEL    = os.getenv("ELEVENLABS_MODEL",    "eleven_multilingual_v2")
WHISPER_MODEL       = os.getenv("WHISPER_MODEL",       "whisper-1")
IMAGE_MODEL         = os.getenv("IMAGE_MODEL",         "dall-e-3")
FRONTEND_URL        = os.getenv("FRONTEND_URL",        "https://heavenlyeternalecho.com")

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

class ImageGenerateRequest(BaseModel):
    prompt: str
    style:   Optional[str] = "vivid"       # vivid | natural
    quality: Optional[str] = "standard"    # standard | hd
    size:    Optional[str] = "1024x1024"   # 1024x1024 | 1792x1024 | 1024x1792
    n:       Optional[int] = 1
    user_id: Optional[str] = None

class WhisperTranscribeRequest(BaseModel):
    audio_base64:  Optional[str] = None
    audio_url:     Optional[str] = None
    language:      Optional[str] = None
    session_id:    Optional[str] = None



# ── Status ────────────────────────────────────────────────────────────────────
@app.get("/status")
async def status():
    """Simple status check — returns active service capabilities."""
    return {
        "service":    "TerrellOS / Heavenly Eternal Echo",
        "version":    "8.0.0-full",
        "status":     "online",
        "capabilities": {
            "chat":       bool(OPENAI_API_KEY),
            "voice":      bool(ELEVENLABS_API_KEY),
            "images":     bool(OPENAI_API_KEY),
            "transcribe": bool(OPENAI_API_KEY),
            "memory":     True,
            "uploads":    True,
        },
        "time": datetime.now(timezone.utc).isoformat()
    }


@app.get("/")
async def root():
    return {
        "success": True,
        "service": "TerrellOS Backend",
        "status": "online",
        "version": "8.0.0-full",
        "docs": "/docs",
        "health": "/health",
        "time": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health")
async def health():
    return {
        "success": True,
        "status": "healthy",
        "version": "8.0.0-full",
        "render": "online",
        "fastapi": "online",
        "openai_configured":    bool(OPENAI_API_KEY),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "image_generation":     "ready" if OPENAI_API_KEY else "needs_api_key",
        "voice_synthesis":      "ready" if ELEVENLABS_API_KEY else "needs_api_key",
        "whisper_transcription": "ready" if OPENAI_API_KEY else "needs_api_key",
        "multipart_uploads":    "ready",
        "cors_origins":         len(_CORS_ALLOWED),
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
    """
    Transcribe audio using OpenAI Whisper.
    Accepts: webm, mp3, mp4, wav, m4a, ogg, flac (max ~25MB).
    """
    audio_bytes = await file.read()

    if not openai_client:
        return {
            "success": False,
            "transcript": None,
            "note": "OPENAI_API_KEY not configured — Whisper transcription unavailable.",
            "filename": file.filename,
            "size": len(audio_bytes),
        }

    import io
    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = file.filename or "audio.webm"
        result = openai_client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=audio_file,
            response_format="verbose_json",
        )
        return {
            "success": True,
            "transcript": result.text,
            "language": getattr(result, "language", None),
            "duration": getattr(result, "duration", None),
            "provider": "openai_whisper",
            "model": WHISPER_MODEL,
            "filename": file.filename,
            "size": len(audio_bytes),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Whisper transcription failed: {str(e)}")


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



# ── Image Generation ──────────────────────────────────────────────────────────
@app.post("/v1/images/generate")
async def images_generate(payload: ImageGenerateRequest):
    """
    Generate images via DALL-E 3.
    Powers: memorial scenes, heavenly avatars, AI vacations, memory reconstruction.
    """
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    if not openai_client:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # Safety-enhanced prompt for spiritual/memorial context
    enhanced_prompt = (
        f"{prompt} — rendered in a warm, sacred, cinematic style with "
        "soft heavenly light and emotional depth."
    )

    try:
        response = openai_client.images.generate(
            model=IMAGE_MODEL,
            prompt=enhanced_prompt,
            size=payload.size,
            quality=payload.quality,
            style=payload.style,
            n=payload.n,
        )
        images = [
            {"url": img.url, "revised_prompt": img.revised_prompt}
            for img in response.data
        ]
        return {
            "success": True,
            "images": images,
            "model": IMAGE_MODEL,
            "prompt": prompt,
            "enhanced_prompt": enhanced_prompt,
            "count": len(images),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


@app.post("/v1/images/memorial")
async def images_memorial(payload: ImageGenerateRequest):
    """
    Specialized memorial / legacy scene generator.
    Creates warm, dignified, spiritual imagery for memory preservation.
    """
    base_prompt = payload.prompt.strip() or "A peaceful eternal scene"
    memorial_prompt = (
        f"A serene, spiritually comforting scene: {base_prompt}. "
        "Soft warm golden light, heavenly clouds, gentle atmosphere, "
        "dignified and emotionally moving, photorealistic with painterly quality."
    )
    memorial_payload = ImageGenerateRequest(
        prompt=memorial_prompt,
        style="natural",
        quality=payload.quality,
        size=payload.size,
        user_id=payload.user_id,
    )
    return await images_generate(memorial_payload)


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
            "/v1/images/generate",
            "/v1/images/memorial",
            "/status",
            "/v1/admin/check-grant",
            "/v1/admin/stats"
        ],
        "time": datetime.now(timezone.utc).isoformat()
    }


# ═══════════════════════════════════════════════════════════════════════════
# SERMON ENGINE — v1.0 — Multi-stage theological generation
# ═══════════════════════════════════════════════════════════════════════════

class SermonGenerateRequest(BaseModel):
    scripture: str
    topic: Optional[str] = None
    denomination: Optional[str] = "non-denominational"
    audience: Optional[str] = "general congregation"
    tone: Optional[str] = "inspiring"
    user_id: Optional[str] = "terrell"

class SermonAnalyzeRequest(BaseModel):
    sermon_id: str
    file_url: Optional[str] = None
    title: Optional[str] = None
    speaker: Optional[str] = None


# In-memory sermon store (swap for DB later)
SERMON_STORE: Dict[str, Dict[str, Any]] = {}


def _gpt(system: str, user: str, max_tokens: int = 1200, temperature: float = 0.75) -> str:
    """Internal helper — single GPT-4o call with error fallback."""
    if not openai_client:
        return "[AI not configured — add OPENAI_API_KEY to Render environment]"
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Generation error: {str(e)}]"


@app.head("/")
async def head_root():
    """Render health ping — silences 405 log spam."""
    from fastapi.responses import Response
    return Response(status_code=200)


@app.post("/v1/sermons/generate")
async def generate_sermon(payload: SermonGenerateRequest):
    """
    7-stage seminary-level sermon generator.
    Each stage builds on the previous — produces 3,000–5,000 word output.
    """
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    scripture  = payload.scripture.strip()
    topic      = payload.topic or scripture
    denom      = payload.denomination or "non-denominational"
    audience   = payload.audience or "general congregation"
    tone       = payload.tone or "inspiring"

    SYS = (
        f"You are a seminary-trained theologian and master preacher writing for a {denom} church. "
        f"Audience: {audience}. Tone: {tone}. "
        "Be specific, deep, and practical. Use scripture references throughout. "
        "Never be vague or generic. Every point must have real theological substance."
    )

    # ── Stage 1: Scripture analysis ───────────────────────────────────────
    scripture_analysis = _gpt(SYS,
        f"Deeply analyze this scripture passage for a sermon: {scripture}\n\n"
        "Cover: historical context, original language nuances, theological themes, "
        "cross-references to other scripture, and practical applications for today. "
        "Be thorough — this is the foundation of the entire sermon.",
        max_tokens=1000
    )

    # ── Stage 2: Sermon structure ─────────────────────────────────────────
    structure = _gpt(SYS,
        f"Scripture: {scripture}\nTopic: {topic}\nAnalysis: {scripture_analysis}\n\n"
        "Create a complete sermon outline with:\n"
        "- A powerful, memorable title\n"
        "- 4-5 main points (each with a sub-heading)\n"
        "- Hook/opening illustration idea\n"
        "- Closing call to action\n"
        "Format as structured outline only.",
        max_tokens=600
    )

    # ── Stage 3: Introduction ─────────────────────────────────────────────
    introduction = _gpt(SYS,
        f"Scripture: {scripture}\nOutline: {structure}\n\n"
        "Write a compelling sermon introduction (400-500 words) that:\n"
        "- Opens with a gripping story, question, or cultural observation\n"
        "- Naturally transitions to the scripture\n"
        "- States the sermon's central thesis clearly\n"
        "- Makes the audience lean in and want to hear more.",
        max_tokens=700
    )

    # ── Stage 4: Main points (the body) ──────────────────────────────────
    key_points_raw = _gpt(SYS,
        f"Scripture: {scripture}\nOutline: {structure}\nIntro: {introduction}\n\n"
        "Write the full body of the sermon — all 4-5 main points.\n"
        "For EACH point write:\n"
        "POINT_TITLE: [bold, memorable title]\n"
        "POINT_CONTENT: [250-350 words — scripture, theological depth, illustration, application]\n\n"
        "Use this exact format for each point so it can be parsed.",
        max_tokens=2500
    )

    # ── Stage 5: Applications ────────────────────────────────────────────
    applications = _gpt(SYS,
        f"Scripture: {scripture}\nMain points: {key_points_raw}\n\n"
        "Write 4-5 specific, practical life applications from this sermon. "
        "Each should be actionable — something a person can do THIS WEEK. "
        "Ground each application in the scripture.",
        max_tokens=600
    )

    # ── Stage 6: Closing prayer ──────────────────────────────────────────
    closing_prayer = _gpt(SYS,
        f"Scripture: {scripture}\nTopic: {topic}\n\n"
        "Write a deeply moving pastoral closing prayer (150-200 words) that:\n"
        "- Summarizes the sermon's spiritual message\n"
        "- Invites personal transformation\n"
        "- Is warm, sincere, and theologically sound\n"
        "Write the prayer itself — not instructions for a prayer.",
        max_tokens=350
    )

    # ── Stage 7: Discussion questions ────────────────────────────────────
    discussion_questions = _gpt(SYS,
        f"Scripture: {scripture}\nMain points: {key_points_raw}\n\n"
        "Write 5-6 small group discussion questions that:\n"
        "- Engage both new believers and mature Christians\n"
        "- Drive personal reflection AND community conversation\n"
        "- Connect directly to the scripture and sermon points\n"
        "Number them 1-6.",
        max_tokens=500
    )

    # ── Parse key points into structured array ────────────────────────────
    key_points = []
    current_title = None
    current_content_lines = []

    for line in key_points_raw.splitlines():
        if line.startswith("POINT_TITLE:"):
            if current_title:
                key_points.append({
                    "title": current_title,
                    "content": " ".join(current_content_lines).strip()
                })
                current_content_lines = []
            current_title = line.replace("POINT_TITLE:", "").strip()
        elif line.startswith("POINT_CONTENT:"):
            current_content_lines = [line.replace("POINT_CONTENT:", "").strip()]
        elif current_title and line.strip():
            current_content_lines.append(line.strip())

    if current_title:
        key_points.append({
            "title": current_title,
            "content": " ".join(current_content_lines).strip()
        })

    # Fallback: if parsing failed, split by double newlines
    if not key_points:
        sections = [s.strip() for s in key_points_raw.split("\n\n") if s.strip()]
        for i, section in enumerate(sections[:5]):
            lines = section.splitlines()
            key_points.append({
                "title": lines[0] if lines else f"Point {i+1}",
                "content": " ".join(lines[1:]) if len(lines) > 1 else section
            })

    # ── Extract sermon title from structure ───────────────────────────────
    sermon_title = topic
    for line in structure.splitlines():
        l = line.strip()
        if l and not l.startswith("-") and len(l) < 100:
            sermon_title = l.lstrip("#").strip(' "\'')
            break

    # ── Parse application list ────────────────────────────────────────────
    app_list = [
        line.lstrip("0123456789.-• ").strip()
        for line in applications.splitlines()
        if line.strip() and len(line.strip()) > 10
    ][:5]

    # ── Parse discussion questions ────────────────────────────────────────
    dq_list = [
        line.lstrip("0123456789.-• ").strip()
        for line in discussion_questions.splitlines()
        if line.strip() and len(line.strip()) > 10
    ][:6]

    sermon_id = str(uuid.uuid4())
    result = {
        "id":                   sermon_id,
        "title":                sermon_title,
        "scripture":            scripture,
        "denomination":         denom,
        "introduction":         introduction,
        "keyPoints":            key_points,
        "applications":         app_list,
        "closingPrayer":        closing_prayer,
        "discussionQuestions":  dq_list,
        "outline":              structure,
        "scriptureAnalysis":    scripture_analysis,
        "wordCount":            len((introduction + key_points_raw + closing_prayer).split()),
        "generatedAt":          datetime.now(timezone.utc).isoformat(),
        "model":                "gpt-4o",
        "stages":               7,
    }

    SERMON_STORE[sermon_id] = result
    return {"success": True, "sermon": result}


@app.get("/v1/sermons/{sermon_id}")
async def get_sermon(sermon_id: str):
    """Retrieve a previously generated sermon by ID."""
    sermon = SERMON_STORE.get(sermon_id)
    if not sermon:
        raise HTTPException(status_code=404, detail="Sermon not found")
    return {"success": True, "sermon": sermon}


@app.post("/v1/content/sermon/analyze")
async def analyze_sermon(payload: SermonAnalyzeRequest):
    """
    Analyze an uploaded sermon file — transcribe (if audio) then extract
    themes, verses, key quotes, and summary.
    """
    title = payload.title or "Untitled Sermon"
    file_url = payload.file_url or ""

    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    SYS = (
        "You are a theological content analyst. Analyze the sermon and extract: "
        "key themes, all Bible verses referenced, main message summary, "
        "key quotes, and spiritual insights."
    )

    summary = _gpt(SYS,
        f"Analyze this sermon titled '{title}'.\n"
        "Extract:\n"
        "1. THEMES: 3-5 core theological themes\n"
        "2. BIBLE_VERSES: all scripture references mentioned\n"
        "3. SUMMARY: 150-word summary of the main message\n"
        "4. KEY_QUOTES: 2-3 most impactful quotes\n"
        "5. SPIRITUAL_INSIGHT: one sentence spiritual takeaway",
        max_tokens=800
    )

    return {
        "success": True,
        "sermon_id": payload.sermon_id,
        "analysis": summary,
        "status": "ready",
        "processedAt": datetime.now(timezone.utc).isoformat()
    }


# ═══════════════════════════════════════════════════════════════════════════
# THEOLOGY ENGINE — Pastor AI Connect
# Discipleship · Denominations · Church History · Martyrs · Apologetics
# ═══════════════════════════════════════════════════════════════════════════

class TheologyRequest(BaseModel):
    topic:        Optional[str] = ""
    scripture:    Optional[str] = ""
    denomination: Optional[str] = "Non-Denominational"
    depth:        Optional[str] = "intermediate"
    level:        Optional[str] = "new-believer"
    era:          Optional[str] = ""
    name:         Optional[str] = ""
    question:     Optional[str] = ""
    tradition:    Optional[str] = "evangelical"
    audience:     Optional[str] = "adults"
    weeks:        Optional[int] = 4
    context:      Optional[str] = ""
    type:         Optional[str] = "pastoral"
    user_id:      Optional[str] = "pastor"


# ═══════════════════════════════════════════════════════════════════════════
# THEOLOGY ENGINE v2 — upgraded prompt engineering + output quality rules
# ═══════════════════════════════════════════════════════════════════════════

# ── Output Quality Standards (injected into every prompt) ──────────────────
OUTPUT_QUALITY_RULES = """
OUTPUT QUALITY RULES — MUST FOLLOW:
✅ Theological depth — go beyond surface-level explanation
✅ Historical context — ground everything in actual history
✅ Scripture integration — cite specific verses with book/chapter/verse
✅ Denominational awareness — note where traditions differ
✅ Practical application — always connect to real Christian life
✅ Emotionally intelligent teaching — pastoral warmth, not academic coldness
✅ Source references — cite church fathers, theologians, or historians where relevant
✅ Structured formatting — clear headers, numbered lists, no run-on paragraphs
❌ No filler phrases ("In conclusion," "As we can see," "It is important to note")
❌ No generic AI fluff or repetitive church clichés
❌ No tiny underdeveloped paragraphs — every section must have substance
❌ No vague application — be specific and actionable
"""

# ── Source citation template ──────────────────────────────────────────────
SOURCE_CITATION_FOOTER = """

---
SOURCES & REFERENCES:
Cite at least 3–5 relevant sources at the end, such as:
- Bible passages (book, chapter:verse)
- Church fathers (e.g., Augustine, Confessions, IV.12)
- Theologians (e.g., Grudem, Systematic Theology, ch. 14)
- Historical councils (e.g., Council of Nicaea, 325 AD)
- Denominational confessions (e.g., Westminster Confession, ch. IX)
Format: [Author/Source] — [Title/Document] — [Date/Edition]
"""

# ── Upgraded _theology helper ─────────────────────────────────────────────
def _theology(system_role: str, prompt: str, tokens: int = 2500) -> dict:
    """Shared theology AI call — v2 with quality enforcement."""
    enriched_system = system_role + "\n\n" + OUTPUT_QUALITY_RULES
    result = _gpt(enriched_system, prompt, max_tokens=tokens, temperature=0.7)
    return {
        "success":     True,
        "content":     result,
        "model":       "gpt-4o",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


# ── BIBLE STUDY ───────────────────────────────────────────────────────────
@app.post("/v1/theology/bible-study")
async def bible_study(payload: TheologyRequest):
    SYS = (
        "You are a seminary-trained biblical scholar with 30 years of pastoral experience. "
        "You combine rigorous academic exegesis with pastoral warmth and practical application. "
        "You are fluent in original languages (Hebrew/Greek) and cite them when relevant. "
        "You produce structured, in-depth Bible studies that could be used in a seminary classroom "
        "or a local church small group — never shallow, always useful."
    )
    prompt = f"""Create a comprehensive, seminary-level Bible study on: {payload.scripture or payload.topic}

Denomination perspective: {payload.denomination or 'non-denominational evangelical'}
Study depth: {payload.depth or 'intermediate'}
Target audience: {payload.audience or 'adult believers'}

REQUIRED SECTIONS:

## 1. PASSAGE OVERVIEW
- Full text of the passage (or key verses)
- Book, author, date written, original audience
- Where this fits in the biblical narrative (redemptive history)
- The literary genre and how it affects interpretation

## 2. HISTORICAL & CULTURAL CONTEXT
- The political, religious, and social world of the original audience
- Key cultural practices referenced in the text
- How understanding the context changes interpretation

## 3. ORIGINAL LANGUAGE INSIGHTS
- 2–3 key words in Hebrew (OT) or Greek (NT) with meaning
- How translation choices affect understanding
- Any nuances lost in English translations

## 4. VERSE-BY-VERSE ANALYSIS
- Work through each key verse or section carefully
- Explain what it meant to the original audience
- Note interpretive differences between traditions (where they exist)

## 5. MAJOR THEOLOGICAL THEMES
- 3–5 significant theological truths in this passage
- How each theme connects to the broader biblical storyline
- Cross-references (at least 5 related passages)

## 6. DENOMINATIONAL PERSPECTIVES
- How do Baptist, Catholic, Orthodox, Pentecostal, Reformed traditions read this passage differently?
- Note major interpretive differences without dismissing any tradition

## 7. PRACTICAL APPLICATION
- 5 specific, actionable applications for believers today
- One application per life area: personal devotion, family, church, work, witness

## 8. DISCUSSION QUESTIONS (for small group / Sunday school)
- 5 thoughtful questions that spark real conversation
- Mix of observation, interpretation, and application questions

## 9. PRAYER
- A pastoral prayer drawing from the themes of the passage

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 3000)


# ── DISCIPLESHIP ──────────────────────────────────────────────────────────
@app.post("/v1/theology/discipleship")
async def discipleship(payload: TheologyRequest):
    SYS = (
        "You are a master discipleship pastor who has trained thousands of Christians "
        "across 30+ years of ministry. You understand that discipleship is not just "
        "information transfer — it is life-on-life spiritual formation. You create "
        "curriculum that is theologically sound, progressively structured, and "
        "practically transformative. You write for real people in real churches."
    )
    prompt = f"""Create a complete, well-structured discipleship lesson on: {payload.topic}

Maturity level: {payload.level or 'growing believer'}
Target audience: {payload.audience or 'adults in a local church'}
Denomination context: {payload.denomination or 'non-denominational'}

REQUIRED SECTIONS:

## LESSON TITLE
Create a memorable, compelling title.

## LEARNING OBJECTIVES
3 clear outcomes — what will the student know, believe, and do differently?

## OPENING HOOK
Start with a real-life story, question, or scenario that creates immediate relevance.

## FOUNDATIONAL SCRIPTURE
The primary passage with verse text. Explain why this text is the anchor for this lesson.

## CORE TEACHING (3–4 sections)
Each section should have:
- A clear sub-heading
- Biblical grounding (with scripture references)
- Theological explanation
- Illustration or story
- Connection to daily life

## KEY SCRIPTURES (minimum 6)
Cited in full with brief commentary on each.

## PRACTICAL EXERCISES
3 specific, actionable exercises the student can do this week.
Make them concrete, not vague.

## REFLECTION QUESTIONS (5)
Move from information → conviction → action.

## ACCOUNTABILITY QUESTIONS
3 questions a discipleship partner can ask next week to check follow-through.

## MEMORY VERSE
One verse from the lesson. Include KJV and NIV versions.

## CLOSING PRAYER
A pastoral prayer for transformation, not just information.

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 2800)


# ── DENOMINATION STUDY ────────────────────────────────────────────────────
@app.post("/v1/theology/denomination")
async def denomination_study(payload: TheologyRequest):
    SYS = (
        "You are a comparative theology professor and church historian with expertise "
        "in all major Christian traditions — Catholic, Orthodox, Protestant, Pentecostal, "
        "and everything in between. You give accurate, respectful, and fair analysis of "
        "each tradition, noting what they believe and why — not dismissing any tradition. "
        "You help Christians understand their own tradition deeply and engage others charitably."
    )
    prompt = f"""Write a comprehensive theological profile of: {payload.denomination}
Topic focus: {payload.topic or 'complete theological overview'}

REQUIRED SECTIONS:

## HISTORICAL ORIGIN
- When, where, and why this denomination was founded
- The theological controversy or spiritual movement that gave birth to it
- Key founders with brief biographies
- Major historical milestones (councils, splits, revivals, mergers)

## STATEMENT OF FAITH — CORE BELIEFS
Cover each: God/Trinity, Scripture, humanity/sin, salvation, Christ, Holy Spirit, church, sacraments, eschatology
For each doctrine: what they believe AND the scriptural basis

## SALVATION DOCTRINE (critical — be precise)
- How does one become saved?
- Role of faith, works, grace, baptism, sacraments
- Assurance of salvation — can you lose it?
- Comparison to other major traditions (1–2 sentences each)

## BAPTISM DOCTRINE
- Mode (immersion, sprinkling, pouring)
- Timing (infant, believer's)
- Theological meaning (symbol, sacrament, regeneration?)

## LORD'S SUPPER / COMMUNION / EUCHARIST
- Frequency
- Theological meaning (memorial, real presence, consubstantiation, transubstantiation?)
- Who may participate

## HOLY SPIRIT DOCTRINE
- Role of the Spirit
- Spiritual gifts — cessationist or continuationist?
- Speaking in tongues — required, expected, or not emphasized?

## WORSHIP STYLE
- Liturgical vs. contemporary
- Order of service
- Music tradition
- Prayer forms

## CHURCH GOVERNMENT
- Episcopal, presbyterian, or congregational?
- Role of pastors, bishops, elders, deacons
- Accountability structures

## ESCHATOLOGY (END TIMES)
- Pre-mil, post-mil, or a-mil?
- Rapture views
- Tribulation views

## MAJOR THEOLOGIANS & CONFESSIONS
- Key theologians with their most important works
- Official confessions/catechisms (Westminster, Heidelberg, Augsburg, etc.)

## KEY DISTINCTIVES vs OTHER TRADITIONS
- What makes this tradition unique?
- Major theological agreements and disagreements with Baptists, Catholics, Pentecostals, Orthodox

## SCRIPTURE FOUNDATION
- 8–10 key scriptures that ground this tradition's core beliefs

## FOR FURTHER STUDY
- 3–5 recommended books, confessions, or resources for deeper study

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 3200)


# ── CHURCH HISTORY ────────────────────────────────────────────────────────
@app.post("/v1/theology/church-history")
async def church_history(payload: TheologyRequest):
    SYS = (
        "You are a church historian with a PhD and 25 years of teaching. You write with "
        "the precision of a scholar and the passion of a pastor. You connect historical "
        "events to the present — showing students that church history is not dry dates "
        "but the living story of God working through broken people. You do not sanitize "
        "the church's failures, nor do you fail to celebrate her triumphs."
    )
    prompt = f"""Write a thorough, engaging church history study on: {payload.topic}
Era focus: {payload.era or 'all relevant eras'}
Denomination lens: {payload.denomination or 'pan-denominational'}

REQUIRED SECTIONS:

## OVERVIEW
- What is this topic/event/period and why does it matter?
- The "so what" — why every Christian should know this

## HISTORICAL TIMELINE
- Key dates and events in chronological order
- Each entry: date, event, significance (2–3 sentences)

## KEY FIGURES
- For each major person: biography, theological contribution, lasting impact
- Include both heroes AND those who made mistakes (honest history)

## THEOLOGICAL SIGNIFICANCE
- What theological questions were being debated?
- What was at stake for the church?
- How was the issue resolved (or not)?

## PRIMARY SOURCES
- Direct quotes from original documents, letters, council decisions, or writings
- Explanation of what each quote reveals

## IMPACT ON THE CHURCH TODAY
- How does this historical event/period still affect Christianity?
- What denominations or practices emerged from it?
- What lessons have (or haven't) been learned?

## CRITICAL ANALYSIS
- What did the church get right?
- What did the church get wrong?
- What would you have done differently?

## LESSONS FOR THE MODERN CHURCH
- 5 specific lessons for 21st-century Christians and churches
- How can these lessons change how we do church today?

## DISCUSSION QUESTIONS (5)

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 2800)


# ── MARTYR BIOGRAPHICAL ───────────────────────────────────────────────────
@app.post("/v1/theology/martyr")
async def martyr_study(payload: TheologyRequest):
    SYS = (
        "You are a Christian historian and pastoral theologian specializing in martyrology "
        "and the theology of suffering. You write with historical precision, spiritual depth, "
        "and pastoral tenderness. You help the church remember those who died for Christ "
        "so that believers today are inspired, challenged, and equipped to face their own trials."
    )
    prompt = f"""Create a comprehensive martyr study for: {payload.topic or payload.figure_name or 'Christian martyrs'}
Era/Region focus: {payload.era or 'all eras'}
Denomination: {payload.denomination or 'cross-denominational'}

## BIOGRAPHICAL PROFILE
- Full name, dates, birthplace, family background
- Pre-conversion life (what were they before Christ?)
- Conversion story — how and when did they come to faith?
- Ministry calling and work

## THE PERSECUTION
- Who persecuted them, why, and in what political/religious context
- The specific events leading to their arrest, trial, or death
- Their response to persecution — how did their faith show?
- Any opportunity they had to recant and why they refused

## FINAL HOURS & DEATH
- Last known words, prayers, or writings
- Manner of death
- Eyewitness accounts (if historical records exist)
- How those present were affected

## THEOLOGICAL SIGNIFICANCE
- What did their death reveal about Christian faith?
- How does their story reflect the life of Christ?
- Key scriptures they embodied (cite specific verses)
- What their martyrdom revealed about the nature of the Gospel

## LEGACY & IMPACT
- How the church responded to their death
- Churches, institutions, or movements named after them
- How their story has been used in Christian history
- Their relevance to persecuted Christians today

## SERMON APPLICATION
- 3 powerful sermon points drawn from their life
- Each point: title, scripture, illustration from their life, application

## PRAYER OF REMEMBRANCE

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 2800)


# ── CHRISTIAN HERO ────────────────────────────────────────────────────────
@app.post("/v1/theology/christian-hero")
async def christian_hero(payload: TheologyRequest):
    SYS = (
        "You are a Christian biographer and historian who tells the stories of Christian "
        "heroes — missionaries, reformers, scholars, revivalists, and ordinary believers "
        "who changed the world through extraordinary faith. You write with historical accuracy, "
        "spiritual insight, and the ability to make history come alive and speak to the present."
    )
    prompt = f"""Write a comprehensive profile of Christian hero: {payload.topic or payload.figure_name}
Ministry type: {payload.ministry_type or 'general'}
Era: {payload.era or 'relevant era'}

## WHO THEY WERE
- Full biography: birth, family, education, early life
- The world they lived in — historical and cultural context
- Their personality and human flaws (not hagiography — real people)

## THE CALLING
- How God called them into ministry
- What obstacles they faced at the start
- The vision God gave them

## THE WORK
- Their specific ministry — what exactly did they do?
- Key achievements, books written, churches planted, lives changed
- Their methods and why they were effective

## FAITH IN ACTION
- Key moments where their faith was tested
- Specific prayers God answered in their ministry
- Miracles or breakthroughs (if documented)
- Failures and how they recovered

## THEOLOGICAL LEGACY
- Their core theological beliefs
- How their theology shaped their ministry
- Lasting theological contributions
- Key writings or sermons

## IMPACT ON CHRISTIANITY
- How did they change the church?
- What movements, institutions, or traditions trace back to them?
- How their work continues today

## WHAT WE CAN LEARN
- 5 specific lessons for Christians today
- How their example challenges comfortable faith
- One thing they did that every believer could imitate

## REFLECTION & DISCUSSION (5 questions)

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 2800)


# ── APOLOGETICS ───────────────────────────────────────────────────────────
@app.post("/v1/theology/apologetics")
async def apologetics(payload: TheologyRequest):
    SYS = (
        "You are a Christian apologist with expertise in philosophy, historical evidence, "
        "and theology. You combine the rigor of C.S. Lewis, the scholarship of N.T. Wright, "
        "and the accessibility of Lee Strobel. You help Christians give confident, intellectually "
        "honest answers to hard questions — without dismissing doubts or oversimplifying objections. "
        "You are always respectful of questioners while being clear about Christian truth claims."
    )
    prompt = f"""Write a comprehensive apologetics response to: {payload.topic}
Target audience: {payload.audience or 'skeptical seekers and questioning Christians'}
Denomination context: {payload.denomination or 'broadly evangelical'}

## THE OBJECTION / QUESTION
- State the objection or question clearly and fairly
- The strongest version of the objection (steelman it)
- Why this is a serious question that deserves a real answer

## HISTORICAL CHRISTIAN RESPONSES
- How have Christians historically responded to this challenge?
- Key apologists who addressed this (with their arguments)
- Church councils or theologians who spoke to this issue

## PHILOSOPHICAL RESPONSE
- The logical structure of the Christian answer
- Where the objection's premises fail or lead to contradictions
- The philosophical case for the Christian position

## BIBLICAL RESPONSE
- Key scriptures that address this question
- How the biblical authors themselves wrestled with this
- The biblical narrative's answer (not just proof-texting)

## HISTORICAL & EVIDENTIAL RESPONSE
- Historical evidence relevant to this question
- Archaeological, manuscript, or scientific evidence
- How the historical case strengthens the Christian answer

## DENOMINATIONAL PERSPECTIVES
- Do different Christian traditions answer this differently?
- Note where there is broad agreement across traditions
- Note where there are genuine theological tensions

## HONEST ACKNOWLEDGMENTS
- What remains genuinely difficult or uncertain?
- What has Christianity gotten wrong in the past on related issues?
- How intellectual honesty strengthens rather than weakens the faith

## PRACTICAL EVANGELISM APPLICATION
- How to use this in a conversation with a skeptic
- What NOT to say
- Questions to ask that open the conversation

## RESOURCES FOR DEEPER STUDY
- 3–5 specific books, articles, or scholars on this topic

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 3000)


# ── PRAYER GENERATION ─────────────────────────────────────────────────────
@app.post("/v1/theology/prayer")
async def prayer_generation(payload: TheologyRequest):
    SYS = (
        "You are a pastoral prayer writer and spiritual director with decades of experience "
        "leading God's people in prayer. You write prayers that are biblically grounded, "
        "emotionally honest, theologically rich, and pastorally sensitive. Your prayers feel "
        "like they come from the heart of a real person before a real God — not corporate "
        "church-speak. You understand different traditions of prayer: extemporaneous, liturgical, "
        "intercessory, contemplative, and warfare prayer."
    )
    prompt = f"""Write a comprehensive prayer resource on: {payload.topic}
Prayer type: {payload.prayer_type or 'pastoral / devotional'}
Occasion: {payload.occasion or 'general use'}
Denomination context: {payload.denomination or 'broadly Christian'}
Audience: {payload.audience or 'adult believers'}

## OPENING PRAYER
A full written prayer (200–300 words) for {payload.topic}.
Rich in scripture, emotionally honest, theologically grounded.

## SCRIPTURE FOUNDATION
5–7 key scriptures that ground this type of prayer.
Brief explanation of how each scripture shapes prayer.

## HOW TO PRAY FOR THIS
Step-by-step guidance for praying about {payload.topic}:
- What to confess
- What to thank God for
- What to ask for (specific petitions)
- How to listen and wait
- How to pray in faith

## PRAYER MODELS FROM SCRIPTURE
- 2–3 biblical figures who prayed about this (with their specific prayers cited)
- What their prayers reveal about how God responds

## SHORT PRAYERS (for different contexts)
- Morning prayer (50 words)
- Evening reflection (50 words)
- Crisis prayer (50 words)
- Thanksgiving prayer (50 words)

## CORPORATE / CONGREGATIONAL PRAYER
A prayer suitable for a church service, including responsive elements if useful.

## PRAYER JOURNAL PROMPTS
5 questions for personal journaling around this topic.

## FOR DIFFERENT TRADITIONS
- How do Catholics approach this prayer topic?
- How do Pentecostals?
- How do Reformed/liturgical traditions?

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 2500)


# ── LESSON PLAN ───────────────────────────────────────────────────────────
@app.post("/v1/theology/lesson-plan")
async def lesson_plan(payload: TheologyRequest):
    SYS = (
        "You are a master Christian educator with experience in seminary education, "
        "Sunday school curriculum development, and adult discipleship programs. "
        "You create lesson plans that are educationally sound, theologically rigorous, "
        "and practically applicable — usable by a first-time Sunday school teacher "
        "or a seasoned seminary professor."
    )
    prompt = f"""Create a complete, production-ready lesson plan on: {payload.topic}
Duration: {payload.duration or '45–60 minutes'}
Audience: {payload.audience or 'adult church class'}
Setting: {payload.setting or 'Sunday school or small group'}
Denomination: {payload.denomination or 'non-denominational'}
Depth level: {payload.depth or 'intermediate'}

## LESSON OVERVIEW
- Title (memorable and compelling)
- Big Idea (one sentence — what this lesson is fundamentally about)
- Learning Objectives: Students will KNOW ___, BELIEVE ___, DO ___
- Key Scripture: Primary passage with full text

## PREPARATION (for the teacher)
- Background reading (2–3 recommended resources)
- Key theological concepts to understand before teaching
- Potential difficult questions and suggested responses
- Materials needed

## LESSON OUTLINE

### HOOK / OPENING (5–10 minutes)
- An attention-grabbing story, question, or activity
- Connect the opening to the lesson's big idea

### BIBLICAL CONTENT (20–30 minutes)
- Section 1: [Title] — explanation, scripture, illustration
- Section 2: [Title] — explanation, scripture, illustration
- Section 3: [Title] — explanation, scripture, illustration
Each section: what to say, what to ask, how long to spend

### APPLICATION BRIDGE (10 minutes)
- How does this biblical truth change how we live?
- 3 specific real-life scenarios where this applies
- Group activity or pair-share exercise

### DISCUSSION (10 minutes)
- 4–5 discussion questions (mix of observation, interpretation, application)
- Tips for facilitating good discussion

### CLOSING (5 minutes)
- Summary of key points
- Memory verse
- Challenge for the week
- Closing prayer

## DIFFERENTIATION
- How to simplify for new believers
- How to deepen for mature believers
- How to adapt for youth

## TAKE-HOME RESOURCE
A one-paragraph summary students can take home.

{SOURCE_CITATION_FOOTER}"""
    return _theology(SYS, prompt, 3000)


@app.post("/v1/martyrs/study")
async def martyr_study(payload: MartyrStudyRequest):
    """Full AI study for any Christian martyr or persecuted believer."""
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    SYS = (
        "You are a Christian historian and pastor specializing in church history, martyrology, "
        "and the theology of suffering and persecution. You write with historical accuracy, "
        "pastoral warmth, and deep reverence for those who gave their lives for Christ. "
        "You are useful for pastors, teachers, and Christians who want to learn from the "
        "courage of those who came before them."
    )

    prompt = _martyr_prompt(payload.figure_name, payload.study_type, MARTYR_STUDY_PROMPTS)
    content = _gpt(SYS, prompt, max_tokens=2200)

    return {
        "success":     True,
        "figure_name": payload.figure_name,
        "study_type":  payload.study_type,
        "content":     content,
        "model":       "gpt-4o",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/black-christian-history/study")
async def black_christian_history_study(payload: BlackChristianHistoryRequest):
    """Full AI study for any figure in Black Christian history."""
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    SYS = (
        "You are a historian and theologian specializing in Black Christian history — "
        "from the African church fathers and Ethiopian Christianity to the slavery era, "
        "the Black church, civil rights movement, and modern Black Christian leaders. "
        "You write with historical rigor, theological depth, and pastoral relevance. "
        "You help the entire church — of every background — understand and honor "
        "the profound contributions of Black Christians throughout history. "
        "You are honest about both the failures of the church toward Black people "
        "and the extraordinary faith of Black Christians despite those failures."
    )

    prompt = _martyr_prompt(payload.figure_name, payload.study_type, BLACK_HISTORY_STUDY_PROMPTS)
    content = _gpt(SYS, prompt, max_tokens=2200)

    return {
        "success":     True,
        "figure_name": payload.figure_name,
        "study_type":  payload.study_type,
        "content":     content,
        "model":       "gpt-4o",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/history/search")
async def christian_history_search(payload: HistorySearchRequest):
    """
    Global Christian history search — search by figure, denomination, country,
    century, theology, persecution type, race/ethnicity, church era, or ministry type.
    """
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    filters = []
    if payload.denomination:   filters.append(f"denomination: {payload.denomination}")
    if payload.country:        filters.append(f"country/region: {payload.country}")
    if payload.century:        filters.append(f"century: {payload.century}")
    if payload.theology:       filters.append(f"theological tradition: {payload.theology}")
    if payload.persecution_type: filters.append(f"persecution type: {payload.persecution_type}")
    if payload.race_ethnicity: filters.append(f"race/ethnicity: {payload.race_ethnicity}")
    if payload.church_era:     filters.append(f"church era: {payload.church_era}")
    if payload.ministry_type:  filters.append(f"ministry type: {payload.ministry_type}")

    filter_str = "\n".join(f"- {f}" for f in filters) if filters else "No additional filters — broad search."

    SYS = (
        "You are a comprehensive Christian historian with knowledge of the entire 2,000-year "
        "history of Christianity — martyrs, theologians, church fathers, missionaries, "
        "revival leaders, Black Christian history, denominational history, and global persecution. "
        "You provide accurate, detailed, and pastorally useful information about Christian historical figures."
    )

    prompt = (
        f"Search Christian history for: '{payload.query}'\n\n"
        f"Filters applied:\n{filter_str}\n\n"
        "Return:\n"
        "1. Top 5–10 relevant historical figures or events matching the search\n"
        "2. For each: name, dates, denomination/tradition, region, brief description (2–3 sentences)\n"
        "3. Why they are relevant to this search\n"
        "4. Suggested further study\n"
        "Format clearly with headers for each result."
    )

    content = _gpt(SYS, prompt, max_tokens=2000)

    return {
        "success":  True,
        "query":    payload.query,
        "filters":  filters,
        "content":  content,
        "model":    "gpt-4o",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
