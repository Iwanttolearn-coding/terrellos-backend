"""
/v1/bible/* — Bible reading with Pastor Mills voice
Returns: scripture text + pastoral teaching + optional ElevenLabs audio
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
import os, httpx, base64
from openai import OpenAI

router = APIRouter(prefix="/v1/bible", tags=["Bible"])

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID= os.getenv("ELEVENLABS_VOICE_ID", "nPczCjzI2devNBz1zQrb")
ELEVENLABS_MODEL   = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
ELEVENLABS_BASE    = "https://api.elevenlabs.io/v1"

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

PASTOR_SYSTEM = """You are Pastor Mills — a warm, biblical, Spirit-filled teaching pastor. 
You speak naturally like a real pastor teaching a real person. Never be vague or generic.
Give scripture-rich, deep, practical answers. Use real Bible references. Explain passages in plain language.
Speak with warmth, authority, and pastoral care."""

class BibleReadRequest(BaseModel):
    book:        str
    chapter:     Optional[int] = 1
    verse_start: Optional[int] = None
    verse_end:   Optional[int] = None
    translation: Optional[str] = "NIV"
    language:    Optional[str] = "English"
    voice:       Optional[bool] = True

async def _elevenlabs_speak(text: str) -> Optional[str]:
    """Returns base64 audio or None."""
    if not ELEVENLABS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=45) as h:
            r = await h.post(
                f"{ELEVENLABS_BASE}/text-to-speech/{ELEVENLABS_VOICE_ID}",
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                json={
                    "text": text[:4500],
                    "model_id": ELEVENLABS_MODEL,
                    "voice_settings": {
                        "stability": 0.35,
                        "similarity_boost": 0.85,
                        "style": 0.45,
                        "use_speaker_boost": True
                    }
                },
            )
        if r.status_code == 200 and r.content:
            return base64.b64encode(r.content).decode()
    except Exception:
        pass
    return None

@router.post("/read")
async def read_bible(req: BibleReadRequest, request: Request):
    from routers.pastor import _require_auth_and_usage
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    if not client:
        return {"success": False, "error": "OpenAI not configured"}

    verse_ref = f"{req.book} {req.chapter}"
    if req.verse_start:
        verse_ref += f":{req.verse_start}"
        if req.verse_end:
            verse_ref += f"-{req.verse_end}"

    prompt = f"""Read {verse_ref} ({req.translation}) and provide:

1. SCRIPTURE TEXT: The actual text of {verse_ref} from the {req.translation} translation.

2. TEACHING: A deep, pastoral explanation of this passage. Include:
   - Historical and cultural context
   - Key word meanings
   - The central message Pastor Mills wants the listener to take away
   - At least 2 supporting scriptures from elsewhere in the Bible
   - A practical application for daily life today
   - A short closing prayer for the listener

Write as if Pastor Mills is sitting with the listener, reading and explaining the Word. Warm, direct, biblical, never vague. Language: {req.language}."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PASTOR_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2500,
            temperature=0.72,
        )
        full_text = resp.choices[0].message.content.strip()

        # Split scripture from teaching
        scripture_text = ""
        teaching = full_text
        if "SCRIPTURE TEXT:" in full_text.upper():
            parts = full_text.split("TEACHING:", 1) if "TEACHING:" in full_text else full_text.split("2.", 1)
            if len(parts) == 2:
                scripture_text = parts[0].replace("1.", "").replace("SCRIPTURE TEXT:", "").strip()
                teaching = parts[1].strip()
            else:
                scripture_text = ""
                teaching = full_text

        audio_base64 = None
        audio_error  = None
        if req.voice:
            speak_text = (scripture_text + "\n\n" + teaching)[:4500]
            audio_base64 = await _elevenlabs_speak(speak_text)
            if not audio_base64:
                audio_error = "ElevenLabs audio unavailable. Check ELEVENLABS_API_KEY."

        return {
            "success":       True,
            "reference":     verse_ref,
            "translation":   req.translation,
            "scriptureText": scripture_text,
            "teaching":      teaching,
            "audio_base64":  audio_base64,
            "audio_error":   audio_error,
            "voice_provider": "elevenlabs" if audio_base64 else None,
        }
    except Exception as e:
        return {"success": False, "error": "Bible reading generation failed. Please try again in a moment."}

@router.get("/health")
async def bible_health():
    return {
        "success": True,
        "openai": "configured" if OPENAI_API_KEY else "missing",
        "elevenlabs": "configured" if ELEVENLABS_API_KEY else "missing",
    }
