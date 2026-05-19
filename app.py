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
    version="8.0.0-full",
    description="TerrellOS / Heavenly Eternal Echo production AI backend"
)

# ── CORS — env-driven allowlist ────────────────────────────────────────────
_CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "")
_CORS_ALLOWED = [o.strip() for o in _CORS_ORIGINS_ENV.split(",") if o.strip()] or [
    "https://heavenlyeternalecho.com",
    "https://www.heavenlyeternalecho.com",
    "https://pastoraiconnect.com",
    "https://www.pastoraiconnect.com",
    "https://pastor-ai-connect.com",
    "https://www.pastor-ai-connect.com",
    "https://terrellos.com",
    "https://www.terrellos.com",
    "https://app.base44.com",
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


def _theology(system_role: str, prompt: str, tokens: int = 2000) -> dict:
    """Shared theology AI call."""
    result = _gpt(system_role, prompt, max_tokens=tokens)
    return {"success": True, "content": result, "model": "gpt-4o", "generatedAt": datetime.now(timezone.utc).isoformat()}


@app.post("/v1/theology/bible-study")
async def bible_study(payload: TheologyRequest):
    SYS = "You are a seminary-trained biblical scholar. Produce thorough, verse-by-verse, historically grounded Bible study material."
    prompt = f"""Create a comprehensive Bible study on {payload.scripture or payload.topic}.
Denomination perspective: {payload.denomination}. Depth: {payload.depth}.
Include:
1. PASSAGE OVERVIEW (context, authorship, date)
2. VERSE BY VERSE analysis (each key verse explained)
3. THEOLOGICAL THEMES (3-5 major themes)
4. CROSS-REFERENCES (related passages)
5. HISTORICAL/CULTURAL CONTEXT
6. APPLICATION (5 practical life applications)
7. REFLECTION QUESTIONS (5 questions)
8. PRAYER
Be thorough and academically rigorous."""
    return _theology(SYS, prompt, 2500)


@app.post("/v1/theology/discipleship")
async def discipleship(payload: TheologyRequest):
    SYS = "You are an experienced discipleship pastor. Create structured, progressive discipleship curriculum."
    prompt = f"""Create a complete discipleship lesson on: {payload.topic}
Level: {payload.level}. Audience: {payload.audience}.
Include:
1. LESSON TITLE & OBJECTIVE
2. OPENING SCRIPTURE
3. INTRODUCTION (why this matters)
4. CORE TEACHING (3-4 sections)
5. KEY SCRIPTURES (at least 5)
6. PRACTICAL EXERCISES
7. REFLECTION QUESTIONS (5)
8. MEMORY VERSE
9. PRAYER
10. NEXT STEPS
Be pastoral, warm, and spiritually deep."""
    return _theology(SYS, prompt, 2000)


@app.post("/v1/theology/denomination")
async def denomination_study(payload: TheologyRequest):
    SYS = "You are a church historian and comparative theology professor. Give accurate, fair, respectful analysis."
    prompt = f"""Write a comprehensive theological profile of: {payload.denomination}
Topic focus: {payload.topic or 'complete overview'}
Include:
1. HISTORY (founding, key events, growth)
2. FOUNDERS & KEY FIGURES
3. CORE BELIEFS (statement of faith summary)
4. SALVATION DOCTRINE (how one is saved)
5. BAPTISM DOCTRINE
6. COMMUNION / LORD'S SUPPER
7. HOLY SPIRIT DOCTRINE
8. WORSHIP STYLE
9. CHURCH GOVERNMENT
10. END-TIMES VIEW (eschatology)
11. MAJOR THEOLOGIANS
12. KEY DIFFERENCES from other traditions
13. RECOMMENDED SCRIPTURES
14. STUDY QUESTIONS (5)
Be academically accurate and fair to the tradition."""
    return _theology(SYS, prompt, 2500)


@app.post("/v1/theology/church-history")
async def church_history(payload: TheologyRequest):
    SYS = "You are a church historian with expertise across all eras of Christian history."
    prompt = f"""Write a thorough study on this church history topic: {payload.topic}
Era: {payload.era or 'all relevant eras'}
Include:
1. HISTORICAL OVERVIEW
2. KEY FIGURES INVOLVED
3. TIMELINE OF EVENTS
4. THEOLOGICAL SIGNIFICANCE
5. IMPACT ON THE CHURCH TODAY
6. CONTROVERSIES & RESOLUTIONS
7. SCRIPTURE CONNECTIONS
8. LESSONS FOR THE MODERN CHURCH
9. STUDY QUESTIONS (5)
Be historically accurate and theologically rich."""
    return _theology(SYS, prompt, 2000)


@app.post("/v1/theology/martyr")
async def martyr_profile(payload: TheologyRequest):
    SYS = "You are a church historian specializing in Christian martyrology. Write with reverence and historical accuracy."
    prompt = f"""Write a complete martyr profile for: {payload.name}
Include:
1. BIOGRAPHY (life, calling, ministry)
2. HISTORICAL SETTING
3. HOW THEY SERVED GOD
4. PERSECUTION HISTORY
5. MARTYRDOM — what happened, when, how
6. SPIRITUAL LESSONS from their life
7. SCRIPTURE CONNECTIONS
8. DENOMINATIONAL / TRADITION context
9. SERMON APPLICATION
10. STUDY QUESTIONS (5)
Write with historical accuracy and pastoral warmth."""
    return _theology(SYS, prompt, 2000)


@app.post("/v1/theology/christian-hero")
async def christian_hero(payload: TheologyRequest):
    SYS = "You are a church historian and theologian. Write thorough, accurate, inspiring profiles of great Christian leaders."
    prompt = f"""Write a comprehensive profile of Christian hero/leader: {payload.name}
Include:
1. BIOGRAPHY & CALLING
2. HISTORICAL IMPACT
3. KEY TEACHINGS & DOCTRINES
4. MAJOR WORKS / BOOKS / SERMONS
5. THEOLOGICAL TRADITION
6. CONTROVERSIES (if any — balanced)
7. TIMELINE
8. HOW THEIR LIFE APPLIES TODAY
9. STUDY QUESTIONS (5)
10. RECOMMENDED READING
Be historically accurate and inspirational."""
    return _theology(SYS, prompt, 2000)


@app.post("/v1/theology/apologetics")
async def apologetics(payload: TheologyRequest):
    SYS = "You are a Christian apologist trained in classical, evidential, and presuppositional apologetics."
    prompt = f"""Provide a thorough apologetics answer to this question: {payload.question}
Tradition: {payload.tradition}
Include:
1. THE QUESTION restated clearly
2. BRIEF ANSWER (summary)
3. FULL DEFENSE (3-4 paragraphs, theological and philosophical)
4. SCRIPTURE SUPPORT
5. HISTORICAL EVIDENCE if applicable
6. COMMON OBJECTIONS & RESPONSES
7. RECOMMENDED READING
8. CLOSING THOUGHT
Be intellectually rigorous and spiritually grounded."""
    return _theology(SYS, prompt, 2000)


@app.post("/v1/theology/prayer")
async def generate_prayer_route(payload: TheologyRequest):
    SYS = "You are a pastoral prayer writer. Write deep, sincere, scripturally grounded prayers."
    prompt = f"""Write a {payload.type} prayer for: {payload.context}
The prayer should:
- Be 200-300 words
- Reference relevant scripture
- Be warm, sincere, and theologically sound
- Include praise, confession, intercession, and surrender
Write the prayer itself — not a description of it."""
    return _theology(SYS, prompt, 500)


@app.post("/v1/theology/lesson-plan")
async def lesson_plan(payload: TheologyRequest):
    SYS = "You are a curriculum designer for Christian education. Build structured, progressive lesson plans."
    prompt = f"""Create a {payload.weeks}-week lesson plan on: {payload.topic}
Audience: {payload.audience}
For each week include:
- Week title
- Learning objective
- Main scripture
- Key points (3)
- Activity or discussion
- Homework / reflection
Make it progressive — each week builds on the previous."""
    return _theology(SYS, prompt, int(payload.weeks) * 300 + 500)



# ═══════════════════════════════════════════════════════════════════════════
# ANCIENT TEXTS ENGINE — Dead Sea Scrolls, Enoch, Apocrypha, Pseudepigrapha
# EASY BIBLE ENGINE — Simple language, beginner, children, prison ministry
# ═══════════════════════════════════════════════════════════════════════════

# ── CANONICAL STATUS LABELS (never mix without these) ───────────────────────
CANONICAL_STATUS = {
    "canonical":     "This text IS part of the accepted biblical canon.",
    "apocrypha":     "APOCRYPHA — Accepted by Catholic/Orthodox traditions; NOT in Protestant or Jewish Bibles.",
    "pseudepigrapha":"PSEUDEPIGRAPHA — Ancient Jewish/Christian writing; NOT accepted as Scripture by any major tradition.",
    "historical":    "HISTORICAL DOCUMENT — Valuable for scholarship; NOT Scripture.",
    "early-church":  "EARLY CHURCH WRITING — Important historically; NOT Scripture or equal to the Bible.",
    "non-canonical": "NON-CANONICAL — Not part of any accepted Bible canon.",
}

ANCIENT_TEXT_DISCLAIMER = (
    "IMPORTANT DISCLAIMER: This content is for scholarly and historical research. "
    "It clearly distinguishes between canonical Scripture, Apocrypha, historical writings, "
    "and theological commentary. Never treat non-canonical texts as equal to the Bible "
    "without explicit labeling."
)

class AncientTextRequest(BaseModel):
    text_name:    str
    text_category: Optional[str] = "historical"
    study_type:   Optional[str] = "overview"   # overview | biblical | pastoral | apologetics
    tradition:    Optional[str] = "evangelical-scholarly"
    user_id:      Optional[str] = "pastor"

class EasyBibleRequest(BaseModel):
    passage:      str
    mode:         Optional[str] = "easy"       # easy | beginner | children | prison | devotion | sermon
    action:       Optional[str] = "easy"       # easy | deep | historical | language | denominations | sermon | prayer
    language:     Optional[str] = "english"    # english | spanish
    user_id:      Optional[str] = "pastor"


@app.post("/v1/ancient-texts/study")
async def ancient_text_study(payload: AncientTextRequest):
    """
    AI study for ancient texts — always includes canonical status disclaimer.
    """
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    status_label = CANONICAL_STATUS.get(payload.text_category, CANONICAL_STATUS["historical"])

    study_prompts = {
        "overview": (
            f"Give a comprehensive scholarly overview of '{payload.text_name}'. "
            "Include: origin, date, language, discovery/history, contents summary, "
            "theological themes, historical significance, relation to biblical canon, "
            "and what scholars agree/disagree on. "
            "Begin with the canonical status of this text. Be academic but accessible. "
            f"Status: {status_label}"
        ),
        "biblical": (
            f"Explain all connections between '{payload.text_name}' and the canonical Bible. "
            "Where does it quote or reference Scripture? Where does the NT cite it? "
            "What biblical concepts does it illuminate? Where does it DIFFER from Scripture? "
            "ALWAYS clearly distinguish what IS Scripture vs historical/non-canonical writing. "
            f"Status: {status_label}"
        ),
        "pastoral": (
            f"How can a pastor responsibly use '{payload.text_name}' in ministry? "
            "What historical and theological insights does it offer without compromising biblical authority? "
            "Include: sermon applications, discipleship uses, apologetics value, "
            "and clear warnings about what is NOT scriptural from this text. "
            f"Status: {status_label}"
        ),
        "apologetics": (
            f"From a Christian apologetics perspective, evaluate '{payload.text_name}'. "
            "How do skeptics misuse it? How do Christians respond? "
            "What does it prove or not prove about the Bible? "
            "Be academically honest and theologically grounded. "
            f"Status: {status_label}"
        ),
    }

    SYS = (
        "You are a biblical scholar specializing in Second Temple Judaism, Dead Sea Scrolls, "
        "early Christianity, and ancient manuscripts. You always clearly label canonical status "
        "of every text — never mixing non-canonical writings with Scripture without explicit labeling. "
        f"DISCLAIMER: {ANCIENT_TEXT_DISCLAIMER}"
    )

    prompt = study_prompts.get(payload.study_type, study_prompts["overview"])
    content = _gpt(SYS, prompt, max_tokens=2000)

    return {
        "success":         True,
        "text_name":       payload.text_name,
        "study_type":      payload.study_type,
        "canonical_status": status_label,
        "disclaimer":      ANCIENT_TEXT_DISCLAIMER,
        "content":         content,
        "model":           "gpt-4o",
        "generatedAt":     datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/ancient-texts/qumran")
async def qumran_study(payload: TheologyRequest):
    """Qumran community & Dead Sea Scrolls background study."""
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    SYS = (
        "You are an expert in Dead Sea Scrolls scholarship, Second Temple Judaism, and Qumran history. "
        "Always clarify what is historical fact, scholarly consensus, or ongoing debate."
    )
    prompt = (
        f"Write a comprehensive study on: {payload.topic or 'The Qumran Community and Dead Sea Scrolls'}\n\n"
        "Include:\n"
        "1. Who were the Essenes / Qumran community?\n"
        "2. Historical timeline (discovery, dating, key figures)\n"
        "3. Their theology and beliefs\n"
        "4. How the scrolls confirm biblical text accuracy\n"
        "5. Unique documents found (non-biblical)\n"
        "6. Comparison with early Christianity\n"
        "7. Pastoral and apologetics value today\n"
        "8. Study questions (5)\n"
        "Always label what is Scripture vs. historical document."
    )
    result = _gpt(SYS, prompt, max_tokens=2000)
    return {
        "success": True,
        "content": result,
        "disclaimer": ANCIENT_TEXT_DISCLAIMER,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/easy-bible/explain")
async def easy_bible_explain(payload: EasyBibleRequest):
    """
    Easy OBM Bible Mode — simple language Bible explanations.
    Supports: easy, beginner, children, prison, devotion, sermon modes.
    Supports English and Spanish.
    """
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    lang = "Spanish" if payload.language == "spanish" else "English"

    audience_map = {
        "easy":     "a general adult audience using simple, clear, everyday language — no seminary jargon",
        "beginner": "someone who has never read the Bible before — explain every concept, no assumed knowledge",
        "children": "children ages 6–12 — use a fun story approach, simple words, relatable examples, and excitement",
        "prison":   "someone in prison ministry — emphasize grace, redemption, forgiveness, and new life in Christ. Be warm, hopeful, and direct.",
        "devotion": "a personal devotional reader — make it warm, personal, encouraging, and spiritually nourishing",
        "sermon":   "a pastor preparing a simple, accessible sermon — give a clean outline with practical application",
    }

    action_map = {
        "easy": (
            f"Explain {payload.passage} in {lang} for {audience_map.get(payload.mode,'a general audience')}.\n"
            "Include:\n1. What it says in simple words\n2. What it meant when written\n"
            "3. What it means for life today\n4. One key takeaway\n5. An encouraging closing thought.\n"
            "Keep it warm, accessible, and spiritually alive."
        ),
        "deep": (
            f"Give a deep theological study of {payload.passage} in {lang}.\n"
            "Include: Greek/Hebrew word meanings, context in chapter and book, "
            "major theological themes, cross-references, and key commentary insights.\n"
            f"Audience: {audience_map.get(payload.mode,'general')}."
        ),
        "historical": (
            f"Explain the historical and cultural background of {payload.passage} in {lang}.\n"
            "Who wrote it? When? To whom? What was happening historically? "
            "How does context change how we read it today?\n"
            f"Audience: {audience_map.get(payload.mode,'general')}."
        ),
        "language": (
            f"Break down the original language of {payload.passage} in {lang}.\n"
            "Show key Hebrew or Greek words, root meanings, translation nuances, "
            "and how English versions differ.\n"
            f"Make this accessible for {audience_map.get(payload.mode,'a general audience')}."
        ),
        "denominations": (
            f"Explain how 4 different Christian denominations interpret {payload.passage} in {lang}.\n"
            "Include: Baptist, Catholic, Pentecostal, and Reformed. "
            "Note agreements, disagreements, and why.\n"
            f"Write for {audience_map.get(payload.mode,'a general audience')}."
        ),
        "sermon": (
            f"Create a simple sermon outline from {payload.passage} in {lang} "
            f"for {audience_map.get(payload.mode,'general congregation')}.\n"
            "Include: title, 3 main points with scripture, illustration for each, "
            "practical application, and closing call to action."
        ),
        "prayer": (
            f"Write a heartfelt prayer based on {payload.passage} in {lang} "
            f"for {audience_map.get(payload.mode,'a general audience')}.\n"
            "Include: praise, reflection on the verse, personal petition, and surrender. 150–200 words."
        ),
    }

    SYS = (
        f"You are a compassionate Bible teacher who excels at making Scripture accessible in {lang}. "
        "You adapt your language to your audience — from children to seminary students. "
        "You are always biblically accurate, warm, and encouraging."
    )

    prompt = action_map.get(payload.action, action_map["easy"])
    content = _gpt(SYS, prompt, max_tokens=1500)

    return {
        "success":    True,
        "passage":    payload.passage,
        "action":     payload.action,
        "mode":       payload.mode,
        "language":   lang,
        "content":    content,
        "model":      "gpt-4o",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/easy-bible/verse-breakdown")
async def verse_breakdown(payload: EasyBibleRequest):
    """Verse-by-verse breakdown for an entire passage."""
    if not openai_client:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    lang = "Spanish" if payload.language == "spanish" else "English"
    mode = payload.mode or "easy"

    SYS = (
        f"You are a Bible teacher explaining Scripture verse-by-verse in {lang}. "
        "You make every verse crystal clear, meaningful, and applicable."
    )
    prompt = (
        f"Do a complete verse-by-verse breakdown of {payload.passage} in {lang}.\n"
        "For EACH verse:\n"
        "VERSE: [verse reference and text]\n"
        "MEANING: [what this verse means in simple terms]\n"
        "APPLICATION: [one practical takeaway]\n\n"
        f"Write for someone who is {mode} — adjust language accordingly.\n"
        "After all verses, add a 'BIG PICTURE' section summarizing the whole passage."
    )
    content = _gpt(SYS, prompt, max_tokens=2000)

    return {
        "success":    True,
        "passage":    payload.passage,
        "mode":       mode,
        "language":   lang,
        "content":    content,
        "model":      "gpt-4o",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
