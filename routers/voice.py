"""
routers/voice.py — Pastor AI Connect
TTS: ElevenLabs ONLY (Brian voice). NO fallbacks. NO robot TTS. NO HuggingFace. NO OpenAI TTS.
If ElevenLabs fails → return error. Never return a computer-generated voice.
"""
import os, base64, httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "nPczCjzI2devNBz1zQrb")  # Brian — Deep, Resonant
ELEVENLABS_MODEL    = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
ELEVENLABS_BASE     = "https://api.elevenlabs.io/v1"

class SpeakRequest(BaseModel):
    text:     str
    voice_id: Optional[str] = None
    model:    Optional[str] = None
    engine:   Optional[str] = "elevenlabs"
    email:    Optional[str] = None

class TranscribeRequest(BaseModel):
    audio_base64: Optional[str] = None
    language:     Optional[str] = "en"

async def _elevenlabs_speak(text: str, voice_id: str, model: str) -> bytes | None:
    if not ELEVENLABS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                json={
                    "text": text,
                    "model_id": model,
                    "voice_settings": {"stability": 0.42, "similarity_boost": 0.88, "use_speaker_boost": True}
                }
            )
            if r.status_code == 200:
                return r.content
    except Exception:
        pass
    return None

@router.post("/v1/voice/speak")
async def speak(payload: SpeakRequest, request: Request):
    from routers.pastor import _require_access
    await _require_access(request, payload.email or "")
    vid   = payload.voice_id or ELEVENLABS_VOICE_ID
    model = payload.model    or ELEVENLABS_MODEL

    if not ELEVENLABS_API_KEY:
        return {
            "success": False,
            "error": "ElevenLabs API key not configured. Contact admin.",
            "provider": None
        }

    audio_bytes = await _elevenlabs_speak(payload.text, vid, model)

    if not audio_bytes:
        return {
            "success": False,
            "error": "ElevenLabs audio generation failed. Please retry.",
            "provider": None
        }

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    return {
        "success":       True,
        "audio_base64":  audio_b64,
        "provider":      "elevenlabs",
        "voice_id":      vid,
        "model":         model
    }

@router.post("/v1/voice/transcribe-upload")
async def transcribe_upload(request: TranscribeRequest, http_request: Request):
    """Transcribe audio via OpenAI Whisper (speech-to-text only — not TTS)."""
    from routers.pastor import _require_auth_and_usage
    await _require_auth_and_usage(http_request, "")
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        return {"success": False, "error": "OpenAI key not configured."}
    if not request.audio_base64:
        return {"success": False, "error": "No audio data provided."}
    try:
        import io
        audio_bytes = base64.b64decode(request.audio_base64)
        openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.webm", io.BytesIO(audio_bytes), "audio/webm"),
            language=request.language or "en"
        )
        return {"success": True, "transcript": transcript.text, "provider": "openai_whisper"}
    except Exception as e:
        return {"success": False, "error": "Transcription failed. Please try again in a moment."}

@router.get("/v1/voice/status")
async def voice_status():
    return {
        "provider":      "elevenlabs",
        "voice_id":      ELEVENLABS_VOICE_ID,
        "model":         ELEVENLABS_MODEL,
        "key_configured": bool(ELEVENLABS_API_KEY),
        "fallbacks":     "disabled — ElevenLabs only"
    }

@router.get("/v1/voice/voices")
async def list_voices():
    if not ELEVENLABS_API_KEY:
        return {"success": False, "error": "ElevenLabs API key not configured."}
    try:
        async with httpx.AsyncClient(timeout=15) as h:
            r = await h.get(f"{ELEVENLABS_BASE}/voices", headers={"xi-api-key": ELEVENLABS_API_KEY})
            if r.status_code == 200:
                return {"success": True, "voices": r.json().get("voices", [])}
    except Exception as e:
        return {"success": False, "error": "Failed to fetch voices."}
    return {"success": False, "error": "Failed to fetch voices."}

@router.get("/v1/voice/health")
async def voice_health():
    import os
    return {
        "success": True, "status": "online", "service": "HEE Voice Studio",
        "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
        "whisper": True,
        "features": ["speak","transcribe","voices"]
    }
