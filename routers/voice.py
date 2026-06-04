"""
/v1/voice/* — TTS, voice cloning, transcription, streaming
TTS priority: ElevenLabs → HuggingFace MMS → OpenAI TTS → text fallback
Transcription: OpenAI Whisper
"""
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
import os, httpx, base64, io
from .usage_logger import log_usage
from .auth import email_from_request

router = APIRouter(prefix="/v1/voice", tags=["Voice"])

OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")
HF_API_KEY          = os.getenv("HUGGINGFACE_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "nPczCjzI2devNBz1zQrb")  # Brian — Deep, Resonant and Comforting
ELEVENLABS_MODEL    = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
ELEVENLABS_BASE     = "https://api.elevenlabs.io/v1"
HF_TTS_URL          = "https://router.huggingface.co/hf-inference/models/facebook/mms-tts-eng"

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class SpeakRequest(BaseModel):
    text: str
    voice_id:       Optional[str] = None
    model:          Optional[str] = None
    emotional_tone: Optional[str] = None   # calm | grief | joyful | solemn
    engine:         Optional[str] = "auto" # "elevenlabs" | "huggingface" | "openai" | "auto"


class TranscribeRequest(BaseModel):
    audio_base64: Optional[str] = None
    audio_url:    Optional[str] = None
    language:     Optional[str] = None


# ── ElevenLabs TTS ───────────────────────────────────────────────────────────
async def _elevenlabs_speak(text: str, voice_id: str, model: str) -> bytes | None:
    if not ELEVENLABS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                json={"text": text, "model_id": model,
                      "voice_settings": {"stability": 0.35, "similarity_boost": 0.85, "style": 0.45, "use_speaker_boost": True}},
            )
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        pass
    return None


# ── HuggingFace TTS (free fallback) ─────────────────────────────────────────
async def _hf_speak(text: str) -> bytes | None:
    """Use HuggingFace MMS-TTS as free fallback. Chunks long text."""
    if not HF_API_KEY:
        return None
    # MMS-TTS has ~400 char limit — chunk on sentence boundaries
    chunks = _chunk_text(text, 380)
    all_audio = b""
    try:
        async with httpx.AsyncClient(timeout=45) as h:
            for chunk in chunks:
                r = await h.post(
                    HF_TTS_URL,
                    headers={"Authorization": f"Bearer {HF_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"inputs": chunk},
                )
                if r.status_code == 200 and r.content and len(r.content) > 100:
                    all_audio += r.content
                else:
                    return None  # model unavailable
        return all_audio if all_audio else None
    except Exception:
        return None


def _chunk_text(text: str, max_len: int) -> list[str]:
    """Split text on sentence boundaries."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 <= max_len:
            current = (current + " " + s).strip()
        else:
            if current:
                chunks.append(current)
            current = s[:max_len]
    if current:
        chunks.append(current)
    return chunks or [text[:max_len]]


# ── OpenAI TTS (secondary fallback) ─────────────────────────────────────────
async def _openai_speak(text: str) -> bytes | None:
    if not openai_client:
        return None
    try:
        resp = openai_client.audio.speech.create(
            model="tts-1", voice="alloy", input=text[:4096]
        )
        return resp.content
    except Exception:
        return None


# ── /speak — ElevenLabs → HuggingFace → OpenAI ───────────────────────────────
@router.post("/speak")
async def speak(payload: SpeakRequest, request: Request = None):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text required")

    vid    = payload.voice_id or ELEVENLABS_VOICE_ID
    model  = payload.model    or ELEVENLABS_MODEL
    engine = payload.engine   or "auto"

    audio_bytes   = None
    provider_used = None

    if engine in ("elevenlabs", "auto"):
        audio_bytes = await _elevenlabs_speak(payload.text, vid, model)
        if audio_bytes:
            provider_used = "elevenlabs"

    if not audio_bytes and engine in ("huggingface", "auto"):
        audio_bytes = await _hf_speak(payload.text)
        if audio_bytes:
            provider_used = "huggingface"

    if not audio_bytes and engine in ("openai", "auto"):
        audio_bytes = await _openai_speak(payload.text)
        if audio_bytes:
            provider_used = "openai"

    if not audio_bytes:
        # Final fallback — return text so frontend can show it
        return {"success": False, "error": "All TTS engines unavailable",
                "fallback_text": payload.text, "provider": None}

    audio_b64 = base64.b64encode(audio_bytes).decode()
    try:
        user_email = email_from_request(request) if request else "anonymous"
        log_usage(endpoint="/v1/voice/speak", user_id=user_email,
                  provider=provider_used, model=model if provider_used == "elevenlabs" else provider_used,
                  extra={"voice_id": vid, "text_length": len(payload.text)})
    except Exception:
        pass

    return {
        "success":      True,
        "audio_base64": audio_b64,
        "content_type": "audio/mpeg",
        "voice_id":     vid,
        "model":        model,
        "provider":     provider_used,
    }


# ── /transcribe ───────────────────────────────────────────────────────────────
@router.post("/transcribe")
async def transcribe(payload: TranscribeRequest):
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    try:
        if payload.audio_base64:
            audio_bytes = base64.b64decode(payload.audio_base64)
            audio_file  = io.BytesIO(audio_bytes)
            audio_file.name = "audio.webm"
        elif payload.audio_url:
            async with httpx.AsyncClient(timeout=30) as h:
                r = await h.get(payload.audio_url)
            audio_file = io.BytesIO(r.content)
            audio_file.name = "audio.mp3"
        else:
            raise HTTPException(status_code=400, detail="audio_base64 or audio_url required")
        kwargs = {"model": "whisper-1", "file": audio_file}
        if payload.language:
            kwargs["language"] = payload.language
        result = openai_client.audio.transcriptions.create(**kwargs)
        return {"success": True, "transcript": result.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── /transcribe-upload ────────────────────────────────────────────────────────
@router.post("/transcribe-upload")
async def transcribe_upload(file: UploadFile = File(...), language: Optional[str] = None):
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    content  = await file.read()
    audio_io = io.BytesIO(content)
    audio_io.name = file.filename or "upload.webm"
    try:
        kwargs = {"model": "whisper-1", "file": audio_io}
        if language:
            kwargs["language"] = language
        result = openai_client.audio.transcriptions.create(**kwargs)
        try:
            log_usage(endpoint="/v1/voice/transcribe-upload", user_id="anonymous",
                      model="whisper-1", provider="openai",
                      extra={"filename": file.filename})
        except Exception:
            pass
        return {"success": True, "transcript": result.text, "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── /voices ───────────────────────────────────────────────────────────────────
@router.get("/voices")
async def list_voices():
    if not ELEVENLABS_API_KEY:
        return {"success": False, "voices": [], "error": "ElevenLabs not configured"}
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(f"{ELEVENLABS_BASE}/voices",
                        headers={"xi-api-key": ELEVENLABS_API_KEY})
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail="Failed to fetch voices")
    data   = r.json()
    voices = [{"id": v["voice_id"], "name": v["name"],
               "labels": v.get("labels", {})} for v in data.get("voices", [])]
    return {"success": True, "voices": voices, "total": len(voices)}


# ── /health ───────────────────────────────────────────────────────────────────
@router.get("/health")
async def voice_health():
    return {
        "success":         True,
        "status":          "online",
        "elevenlabs_key":  "configured" if ELEVENLABS_API_KEY else "missing",
        "huggingface_key": "configured" if HF_API_KEY        else "missing",
        "openai_key":      "configured" if OPENAI_API_KEY    else "missing",
        "tts_chain":       ["elevenlabs", "huggingface", "openai"],
        "services": {
            "tts":          bool(ELEVENLABS_API_KEY or HF_API_KEY or OPENAI_API_KEY),
            "transcription":bool(OPENAI_API_KEY),
            "voice_list":   True,
        }
    }
