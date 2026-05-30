"""
routers/voice_interview.py — Heavenly Eternal Echo
Life Interview + Voice Clone System

Endpoints:
  POST /v1/voice-interview/recording/save     — save audio recording + transcript
  GET  /v1/voice-interview/recordings/{uid}   — list all recordings for a user
  DELETE /v1/voice-interview/recording/{id}   — delete one recording
  GET  /v1/voice-interview/progress/{uid}     — total minutes + clone readiness
  POST /v1/voice-interview/clone              — send all audio to ElevenLabs, store voice_id
  GET  /v1/voice-interview/clone/{uid}        — get clone status for a user
  POST /v1/voice-interview/test-clone         — TTS with user's cloned voice
  GET  /v1/voice-interview/admin/debug        — founder debug panel
  GET  /v1/voice-interview/questions          — return 100 life interview questions
"""
import os, io, uuid, httpx, base64, logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger("voice_interview")
router = APIRouter(prefix="/v1/voice-interview", tags=["Voice Interview"])

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_BASE    = "https://api.elevenlabs.io/v1"
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
SUPABASE_URL       = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY       = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
MIN_CLONE_SECONDS  = 15 * 60   # 15 minutes minimum for quality clone
RECOMMENDED_SECONDS= 30 * 60   # 30 minutes recommended

def _now(): return datetime.now(timezone.utc).isoformat()

# ── Supabase helpers ──────────────────────────────────────────────
async def _sb_insert(table: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=data,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Supabase insert failed {r.status_code}: {r.text[:200]}")
    rows = r.json()
    return rows[0] if rows else data

async def _sb_select(table: str, filters: dict = None, limit: int = 200) -> list:
    params = f"?limit={limit}"
    if filters:
        for k, v in filters.items():
            params += f"&{k}=eq.{v}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/{table}{params}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Accept": "application/json"},
        )
    if r.status_code != 200:
        return []
    return r.json() or []

async def _sb_update(table: str, filters: dict, data: dict):
    params = "?" + "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.patch(
            f"{SUPABASE_URL}/rest/v1/{table}{params}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=data,
        )
    return r.status_code in (200, 204)

async def _sb_delete(table: str, filters: dict):
    params = "?" + "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.delete(
            f"{SUPABASE_URL}/rest/v1/{table}{params}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        )
    return r.status_code in (200, 204)

async def _sb_upload_audio(bucket: str, path: str, audio_bytes: bytes, content_type: str = "audio/webm") -> str:
    """Upload audio to Supabase Storage bucket, return public URL."""
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": content_type, "x-upsert": "true"},
            content=audio_bytes,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Supabase Storage upload failed {r.status_code}: {r.text[:300]}")
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"

# ── 100 Life Interview Questions ──────────────────────────────────
INTERVIEW_QUESTIONS = [
    # Childhood
    "Tell me about where you grew up.",
    "What is your earliest memory?",
    "What were you like as a child?",
    "Tell me about your parents.",
    "Tell me about your siblings.",
    "What did your home look like?",
    "What games did you play as a kid?",
    "Tell me about your best childhood friend.",
    "What was your favorite meal growing up?",
    "What scared you as a child?",
    # School & Education
    "What was school like for you?",
    "Tell me about a teacher who changed your life.",
    "What were you good at in school?",
    "What was your biggest academic struggle?",
    "Tell me about graduation.",
    # Young Adulthood
    "Tell me about your first job.",
    "Tell me about your first love.",
    "What did you want to be when you grew up?",
    "Tell me about the first time you lived on your own.",
    "What was the best decision you made in your 20s?",
    "What was the worst decision you made in your 20s?",
    # Love & Family
    "Tell me about the day you met your partner.",
    "Describe your wedding day.",
    "Tell me about becoming a parent for the first time.",
    "What's the best thing about your family?",
    "What's the hardest thing about raising children?",
    "Tell me about a moment you were truly proud of your kids.",
    "How did your parents shape who you are?",
    "Tell me about a family tradition you love.",
    "If you could go back and change something about raising your kids, what would it be?",
    # Faith & Spirituality
    "What role has faith played in your life?",
    "Tell me about your relationship with God.",
    "Was there a moment your faith was tested?",
    "Was there a moment your faith was strengthened?",
    "What do you believe happens after we die?",
    "Tell me about a prayer that was answered.",
    "What does your church or spiritual community mean to you?",
    # Work & Purpose
    "Tell me about your career.",
    "What work are you most proud of?",
    "Tell me about your proudest professional moment.",
    "What did work teach you about life?",
    "If you could have had any career, what would it be?",
    "Tell me about someone who mentored you.",
    # Loss & Hardship
    "Tell me about the hardest year of your life.",
    "Tell me about losing someone you loved.",
    "How do you handle grief?",
    "What is your biggest regret?",
    "What almost broke you?",
    "What kept you going when things were hard?",
    # Joy & Gratitude
    "Tell me about your happiest memory.",
    "Tell me about a moment you laughed so hard it hurt.",
    "What brings you the most peace?",
    "Tell me about a perfect day.",
    "What are you most grateful for?",
    "Tell me about a moment of pure joy.",
    # Values & Wisdom
    "What values did you try to live by?",
    "What do you wish you had known at 20?",
    "What advice would you give your younger self?",
    "What did money teach you?",
    "Tell me about a time you had to stand up for what was right.",
    "What is the most important lesson life has taught you?",
    "What does success mean to you?",
    "What does love mean to you?",
    "What does it mean to be a good person?",
    # Legacy
    "What do you want to be remembered for?",
    "What would you tell your grandchildren?",
    "What do you hope your children learned from you?",
    "If you had one more year, how would you spend it?",
    "What would you tell the world if you had five minutes?",
    "What are you most proud of in your life?",
    "What unfinished business do you wish you could complete?",
    "What is the best gift you ever gave someone?",
    "What is the best gift someone ever gave you?",
    "What do you want your legacy to be?",
    # Simple & Beautiful
    "Tell me about your favorite place on Earth.",
    "Tell me about your favorite song and why it matters.",
    "Tell me about a book that changed your life.",
    "What is your favorite smell?",
    "What is your earliest happy memory?",
    "Tell me about your favorite season and why.",
    "Tell me about the bravest thing you ever did.",
    "Tell me about a time a stranger was kind to you.",
    "Tell me about a time you were kind to a stranger.",
    "Tell me about something you did that surprised even yourself.",
    # Relationships
    "Tell me about your best friend.",
    "Tell me about the most important relationship in your life.",
    "Tell me about a friendship that shaped who you are.",
    "Is there someone you wish you had said something to?",
    "Who has shown you the most unconditional love?",
    "Who are you most grateful you met?",
    # Final Words
    "What do you wish people understood about you?",
    "If you could speak to someone who is gone, what would you say?",
    "What do you want your family to do when you're gone?",
    "What message would you leave behind for someone who is suffering?",
    "Is there anything you've never told anyone that you'd like to say now?",
    "What is the last thing you want someone to hear in your voice?",
]

# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/questions")
async def get_questions():
    """Return all 100 life interview questions."""
    return {
        "success": True,
        "total": len(INTERVIEW_QUESTIONS),
        "questions": [{"index": i, "question": q} for i, q in enumerate(INTERVIEW_QUESTIONS)],
        "categories": {
            "childhood": list(range(0, 10)),
            "school": list(range(10, 15)),
            "young_adulthood": list(range(15, 20)),
            "love_family": list(range(20, 30)),
            "faith": list(range(30, 37)),
            "work": list(range(37, 44)),
            "loss_hardship": list(range(44, 50)),
            "joy_gratitude": list(range(50, 57)),
            "values_wisdom": list(range(57, 67)),
            "legacy": list(range(67, 77)),
            "simple_beautiful": list(range(77, 87)),
            "relationships": list(range(87, 93)),
            "final_words": list(range(93, 100)),
        }
    }

@router.post("/recording/save")
async def save_recording(
    audio: UploadFile = File(...),
    user_id: str = Form(...),
    profile_id: Optional[str] = Form(default=""),
    question_index: Optional[int] = Form(default=None),
    question_text: Optional[str] = Form(default=""),
    duration_sec: Optional[float] = Form(default=0),
    category: Optional[str] = Form(default="general"),
):
    """
    Save a voice recording.
    1. Upload audio to Supabase Storage
    2. Auto-transcribe with Whisper
    3. Save metadata to hee_recordings table
    Returns: { success, recording_id, audio_url, transcript, duration_sec }
    """
    logger.info("RECORDING SAVE STARTED user=%s duration=%.1fs", user_id, duration_sec or 0)

    if not user_id:
        raise HTTPException(400, "user_id is required")

    # Read audio bytes
    audio_bytes = await audio.read()
    file_size   = len(audio_bytes)
    logger.info("Audio bytes received: %d", file_size)

    if file_size < 100:
        raise HTTPException(400, "Audio file is empty or too small")

    # Upload to Supabase Storage
    audio_url = ""
    recording_id = str(uuid.uuid4())
    safe_user = user_id.replace("@", "_at_").replace(".", "_")
    storage_path = f"hee/{safe_user}/{recording_id}.webm"

    try:
        audio_url = await _sb_upload_audio(
            bucket="voice-recordings",
            path=storage_path,
            audio_bytes=audio_bytes,
            content_type=audio.content_type or "audio/webm",
        )
        logger.info("UPLOAD SUCCESS: %s", audio_url)
    except Exception as e:
        logger.error("UPLOAD FAILED: %s", e)
        # Don't fail the whole request — store as base64 data URL fallback
        b64 = base64.b64encode(audio_bytes).decode()
        audio_url = f"data:{audio.content_type or 'audio/webm'};base64,{b64[:100]}...[truncated]"
        logger.warning("Falling back to base64 data URL for recording %s", recording_id)

    # Auto-transcribe with Whisper
    transcript = ""
    try:
        if OPENAI_API_KEY and file_size > 0:
            from openai import OpenAI
            oai = OpenAI(api_key=OPENAI_API_KEY)
            audio_io = io.BytesIO(audio_bytes)
            audio_io.name = "recording.webm"
            result = oai.audio.transcriptions.create(model="whisper-1", file=audio_io)
            transcript = result.text
            logger.info("TRANSCRIPTION SUCCESS: %d chars", len(transcript))
    except Exception as e:
        logger.warning("TRANSCRIPTION FAILED: %s", e)
        transcript = ""

    # Save to hee_recordings table
    record_data = {
        "id": recording_id,
        "user_id": user_id,
        "profile_id": profile_id or user_id,
        "question_index": question_index,
        "question_text": question_text or (INTERVIEW_QUESTIONS[question_index] if question_index is not None and question_index < len(INTERVIEW_QUESTIONS) else ""),
        "category": category or "general",
        "audio_url": audio_url,
        "transcript": transcript,
        "duration_sec": float(duration_sec or 0),
        "file_size_bytes": file_size,
        "created_at": _now(),
        "storage_path": storage_path,
        "upload_success": "data:" not in audio_url,
    }

    saved = None
    try:
        saved = await _sb_insert("hee_recordings", record_data)
        logger.info("DB SAVE SUCCESS recording_id=%s", recording_id)
    except Exception as e:
        logger.error("DB SAVE FAILED: %s", e)
        # Return partial success — audio is uploaded even if DB save fails
        return {
            "success": True,
            "warning": f"Audio uploaded but DB save failed: {str(e)[:100]}",
            "recording_id": recording_id,
            "audio_url": audio_url,
            "transcript": transcript,
            "duration_sec": duration_sec or 0,
        }

    return {
        "success": True,
        "recording_id": recording_id,
        "audio_url": audio_url,
        "transcript": transcript,
        "duration_sec": duration_sec or 0,
        "question_text": record_data["question_text"],
        "upload_success": record_data["upload_success"],
    }


@router.get("/recordings/{user_id}")
async def get_recordings(user_id: str, profile_id: Optional[str] = None):
    """Get all recordings for a user, sorted newest first."""
    filters = {"user_id": user_id}
    if profile_id:
        filters["profile_id"] = profile_id
    try:
        rows = await _sb_select("hee_recordings", filters=filters, limit=500)
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        total_sec = sum(float(r.get("duration_sec", 0)) for r in rows)
        return {
            "success": True,
            "recordings": rows,
            "total_count": len(rows),
            "total_seconds": total_sec,
            "total_minutes": round(total_sec / 60, 1),
        }
    except Exception as e:
        logger.error("Get recordings failed: %s", e)
        return {"success": False, "recordings": [], "total_count": 0, "total_seconds": 0, "total_minutes": 0, "error": str(e)}


@router.delete("/recording/{recording_id}")
async def delete_recording(recording_id: str, user_id: str):
    """Delete a recording by ID."""
    try:
        # Verify ownership
        rows = await _sb_select("hee_recordings", filters={"id": recording_id, "user_id": user_id})
        if not rows:
            raise HTTPException(404, "Recording not found or access denied")
        await _sb_delete("hee_recordings", {"id": recording_id})
        return {"success": True, "deleted": recording_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/progress/{user_id}")
async def get_progress(user_id: str, profile_id: Optional[str] = None):
    """Return total audio time, clone readiness, and status."""
    filters = {"user_id": user_id}
    if profile_id:
        filters["profile_id"] = profile_id
    rows = await _sb_select("hee_recordings", filters=filters, limit=500)
    total_sec = sum(float(r.get("duration_sec", 0)) for r in rows)
    total_min = total_sec / 60

    clone_rows = await _sb_select("hee_voice_clones", filters={"user_id": user_id}, limit=1)
    clone = clone_rows[0] if clone_rows else None

    pct_to_min = min(100, int((total_sec / MIN_CLONE_SECONDS) * 100))
    pct_to_rec  = min(100, int((total_sec / RECOMMENDED_SECONDS) * 100))

    return {
        "success": True,
        "user_id": user_id,
        "recording_count": len(rows),
        "total_seconds": total_sec,
        "total_minutes": round(total_min, 1),
        "minimum_minutes": MIN_CLONE_SECONDS / 60,
        "recommended_minutes": RECOMMENDED_SECONDS / 60,
        "pct_to_minimum": pct_to_min,
        "pct_to_recommended": pct_to_rec,
        "clone_ready": total_sec >= MIN_CLONE_SECONDS,
        "clone_status": clone.get("status", "not_started") if clone else "not_started",
        "voice_id": clone.get("elevenlabs_voice_id") if clone else None,
        "clone_error": clone.get("last_error") if clone else None,
    }


@router.post("/clone")
async def create_voice_clone(
    user_id: str,
    profile_id: Optional[str] = None,
    voice_name: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger ElevenLabs voice clone using ALL recordings for this user.
    Requires minimum 15 minutes of audio.
    """
    if not ELEVENLABS_API_KEY:
        raise HTTPException(503, "ElevenLabs API key not configured")

    filters = {"user_id": user_id}
    if profile_id:
        filters["profile_id"] = profile_id
    rows = await _sb_select("hee_recordings", filters=filters, limit=500)
    total_sec = sum(float(r.get("duration_sec", 0)) for r in rows)

    if total_sec < MIN_CLONE_SECONDS:
        needed_min = round((MIN_CLONE_SECONDS - total_sec) / 60, 1)
        raise HTTPException(400, f"Not enough audio. Need {needed_min} more minutes (currently {round(total_sec/60,1)} min / 15 min minimum)")

    # Mark as training
    try:
        existing = await _sb_select("hee_voice_clones", filters={"user_id": user_id}, limit=1)
        clone_record = {
            "user_id": user_id,
            "profile_id": profile_id or user_id,
            "status": "training",
            "recording_count": len(rows),
            "total_seconds": total_sec,
            "updated_at": _now(),
        }
        if existing:
            await _sb_update("hee_voice_clones", {"user_id": user_id}, clone_record)
            clone_id = existing[0].get("id")
        else:
            clone_record["created_at"] = _now()
            saved = await _sb_insert("hee_voice_clones", clone_record)
            clone_id = saved.get("id")
    except Exception as e:
        logger.error("Failed to mark clone as training: %s", e)
        clone_id = str(uuid.uuid4())

    # Build ElevenLabs add-voice request with all audio files
    logger.info("CLONE STARTED user=%s recordings=%d total_min=%.1f", user_id, len(rows), total_sec/60)
    audio_urls = [r["audio_url"] for r in rows if r.get("audio_url") and "data:" not in r.get("audio_url","")]

    try:
        files = []
        async with httpx.AsyncClient(timeout=30) as c:
            for i, url in enumerate(audio_urls[:25]):  # ElevenLabs max 25 files
                try:
                    r = await c.get(url)
                    if r.status_code == 200:
                        files.append(("files", (f"recording_{i}.webm", r.content, "audio/webm")))
                except Exception as e:
                    logger.warning("Failed to fetch audio %s: %s", url, e)

        if not files:
            raise RuntimeError("No downloadable audio files found. Recordings may not have uploaded properly.")

        name = voice_name or f"HEE-{user_id[:8]}-{_now()[:10]}"
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{ELEVENLABS_BASE}/voices/add",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                data={"name": name, "description": f"Heavenly Eternal Echo voice clone for {user_id}"},
                files=files,
            )

        if r.status_code not in (200, 201):
            err_text = r.text[:300]
            logger.error("ELEVENLABS CLONE FAILED %d: %s", r.status_code, err_text)
            await _sb_update("hee_voice_clones", {"user_id": user_id}, {
                "status": "failed", "last_error": f"ElevenLabs error {r.status_code}: {err_text}", "updated_at": _now()
            })
            raise HTTPException(502, f"ElevenLabs voice clone failed ({r.status_code}): {err_text}")

        voice_data = r.json()
        voice_id   = voice_data.get("voice_id", "")
        logger.info("CLONE SUCCESS voice_id=%s", voice_id)

        await _sb_update("hee_voice_clones", {"user_id": user_id}, {
            "status": "ready",
            "elevenlabs_voice_id": voice_id,
            "voice_name": name,
            "last_error": None,
            "updated_at": _now(),
        })

        return {
            "success": True,
            "voice_id": voice_id,
            "voice_name": name,
            "status": "ready",
            "recordings_used": len(files),
            "total_minutes": round(total_sec / 60, 1),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("CLONE ERROR: %s", e)
        try:
            await _sb_update("hee_voice_clones", {"user_id": user_id}, {
                "status": "failed", "last_error": str(e)[:300], "updated_at": _now()
            })
        except Exception:
            pass
        raise HTTPException(500, f"Voice clone error: {e}")


@router.get("/clone/{user_id}")
async def get_clone_status(user_id: str):
    """Get voice clone status and voice_id for a user."""
    rows = await _sb_select("hee_voice_clones", filters={"user_id": user_id}, limit=1)
    if not rows:
        return {"success": True, "status": "not_started", "voice_id": None}
    clone = rows[0]
    return {
        "success": True,
        "status": clone.get("status", "not_started"),
        "voice_id": clone.get("elevenlabs_voice_id"),
        "voice_name": clone.get("voice_name"),
        "recording_count": clone.get("recording_count"),
        "total_minutes": round(float(clone.get("total_seconds", 0)) / 60, 1),
        "last_error": clone.get("last_error"),
        "updated_at": clone.get("updated_at"),
    }


@router.post("/test-clone")
async def test_clone_voice(user_id: str, text: Optional[str] = None):
    """Speak text using the user's cloned voice."""
    rows = await _sb_select("hee_voice_clones", filters={"user_id": user_id}, limit=1)
    if not rows or not rows[0].get("elevenlabs_voice_id"):
        raise HTTPException(404, "No voice clone found for this user")
    voice_id = rows[0]["elevenlabs_voice_id"]
    speak_text = text or "Hello. This is my voice, preserved forever for the ones I love."
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={"text": speak_text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
        )
    if r.status_code != 200:
        raise HTTPException(502, f"ElevenLabs TTS error {r.status_code}: {r.text[:200]}")
    audio_b64 = base64.b64encode(r.content).decode()
    return {"success": True, "audio_base64": audio_b64, "voice_id": voice_id, "text": speak_text}


@router.get("/admin/debug")
async def admin_voice_debug():
    """Founder debug panel — all users, audio minutes, clone status."""
    try:
        recordings = await _sb_select("hee_recordings", limit=1000)
        clones     = await _sb_select("hee_voice_clones", limit=200)

        # Group by user
        by_user = {}
        for r in recordings:
            uid = r.get("user_id", "unknown")
            if uid not in by_user:
                by_user[uid] = {"recording_count": 0, "total_seconds": 0, "user_id": uid}
            by_user[uid]["recording_count"] += 1
            by_user[uid]["total_seconds"]   += float(r.get("duration_sec", 0))

        clone_by_user = {c["user_id"]: c for c in clones}

        users_debug = []
        for uid, stats in by_user.items():
            clone = clone_by_user.get(uid, {})
            users_debug.append({
                "user_id": uid,
                "recording_count": stats["recording_count"],
                "total_minutes": round(stats["total_seconds"] / 60, 1),
                "clone_status": clone.get("status", "not_started"),
                "voice_id": clone.get("elevenlabs_voice_id"),
                "last_error": clone.get("last_error"),
                "clone_ready": stats["total_seconds"] >= MIN_CLONE_SECONDS,
            })

        users_debug.sort(key=lambda u: u["total_minutes"], reverse=True)
        return {
            "success": True,
            "total_users_with_recordings": len(users_debug),
            "total_recordings": len(recordings),
            "minimum_minutes_for_clone": MIN_CLONE_SECONDS / 60,
            "users": users_debug,
            "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
            "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/health")
async def voice_interview_health():
    return {
        "success": True,
        "status": "online",
        "elevenlabs": bool(ELEVENLABS_API_KEY),
        "supabase": bool(SUPABASE_URL and SUPABASE_KEY),
        "openai": bool(OPENAI_API_KEY),
        "question_count": len(INTERVIEW_QUESTIONS),
        "min_clone_minutes": MIN_CLONE_SECONDS / 60,
    }
