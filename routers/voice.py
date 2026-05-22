"""
/v1/voice/* — TTS, voice cloning, transcription, streaming
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
import os, httpx, base64, io

router = APIRouter(prefix="/v1/voice", tags=["Voice"])

OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ELEVENLABS_MODEL    = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_BASE     = "https://api.elevenlabs.io/v1"
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

class SpeakRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    model: Optional[str] = None
    emotional_tone: Optional[str] = None  # calm | grief | joyful | solemn

class TranscribeRequest(BaseModel):
    audio_base64: Optional[str] = None
    audio_url: Optional[str] = None
    language: Optional[str] = None

@router.post("/speak")
async def speak(payload: SpeakRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text required")
    if not ELEVENLABS_API_KEY:
        return {"success": False, "error": "ElevenLabs key not configured",
                "fallback": payload.text}
    vid = payload.voice_id or ELEVENLABS_VOICE_ID
    model = payload.model or ELEVENLABS_MODEL
    async with httpx.AsyncClient(timeout=30) as h:
        r = await h.post(
            f"{ELEVENLABS_BASE}/text-to-speech/{vid}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={"text": payload.text, "model_id": model,
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"ElevenLabs error: {r.text}")
    audio_b64 = base64.b64encode(r.content).decode()
    return {"success": True, "audio_base64": audio_b64, "content_type": "audio/mpeg",
            "voice_id": vid, "model": model}

@router.post("/transcribe")
async def transcribe(payload: TranscribeRequest):
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    try:
        if payload.audio_base64:
            audio_bytes = base64.b64decode(payload.audio_base64)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.webm"
        elif payload.audio_url:
            async with httpx.AsyncClient() as h:
                r = await h.get(payload.audio_url)
            audio_bytes = r.content
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.mp3"
        else:
            raise HTTPException(status_code=400, detail="audio_base64 or audio_url required")
        kwargs = {"model": "whisper-1", "file": audio_file}
        if payload.language: kwargs["language"] = payload.language
        result = openai_client.audio.transcriptions.create(**kwargs)
        return {"success": True, "transcript": result.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/transcribe-upload")
async def transcribe_upload(file: UploadFile = File(...), language: Optional[str] = None):
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    content = await file.read()
    audio_io = io.BytesIO(content)
    audio_io.name = file.filename or "upload.webm"
    try:
        kwargs = {"model": "whisper-1", "file": audio_io}
        if language: kwargs["language"] = language
        result = openai_client.audio.transcriptions.create(**kwargs)
        return {"success": True, "transcript": result.text, "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/voices")
async def list_voices():
    if not ELEVENLABS_API_KEY:
        return {"success": False, "voices": [], "error": "ElevenLabs not configured"}
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(f"{ELEVENLABS_BASE}/voices",
                        headers={"xi-api-key": ELEVENLABS_API_KEY})
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail="Failed to fetch voices")
    data = r.json()
    voices = [{"id": v["voice_id"], "name": v["name"],
               "labels": v.get("labels", {})} for v in data.get("voices", [])]
    return {"success": True, "voices": voices, "total": len(voices)}


@router.get("/health")
async def voice_health():
    """Voice engine health check."""
    import os
    return {
        "success":        True,
        "status":         "online",
        "elevenlabs_key": "configured" if os.getenv("ELEVENLABS_API_KEY") else "missing",
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID", "not_set"),
        "openai_key":     "configured" if os.getenv("OPENAI_API_KEY") else "missing",
        "services": {
            "tts":          bool(os.getenv("ELEVENLABS_API_KEY")),
            "transcription":bool(os.getenv("OPENAI_API_KEY")),
            "voice_list":   True,
        }
    }
