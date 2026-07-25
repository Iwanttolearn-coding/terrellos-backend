"""
routers/transcribe.py — Audio Transcription (Whisper)
Used by all apps for voice-to-text.
"""
import os, httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional

router = APIRouter(prefix="/v1/transcribe", tags=["Transcribe"])
OPENAI_KEY = os.getenv("OPENAI_API_KEY","")

@router.get("/health")
async def transcribe_health():
    return {
        "success": True, "status": "online", "service": "Transcription",
        "whisper": bool(OPENAI_KEY),
        "model": "whisper-1",
        "apps": ["pastor-ai","hee","kindred","pro-se-ai","terrellos"]
    }

@router.post("/audio")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default="en"),
    app_id: Optional[str] = Form(default="terrellos"),
):
    if not OPENAI_KEY:
        raise HTTPException(status_code=500, detail="OpenAI not configured")
    audio_bytes = await file.read()
    files = {"file": (file.filename or "audio.webm", audio_bytes, file.content_type or "audio/webm")}
    data  = {"model": "whisper-1", "language": language}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            files=files, data=data
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Whisper error: {r.text[:200]}")
    return {"success": True, "transcript": r.json().get("text",""), "language": language}
