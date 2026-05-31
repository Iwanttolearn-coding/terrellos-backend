"""
services/pastor_db.py — Supabase save helpers for Pastor AI
Auto-save every generation to Supabase (pastor_sermons, pastor_bible_studies, etc.)
"""
import os, uuid, httpx, logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("pastor_db")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def save_sermon(
    user_id: str,
    title: str,
    content: str,
    scripture: str = "",
    tone: str = "inspirational",
    denomination: str = "Non-Denominational",
    sermon_length: str = "medium",
    output_type: str = "full_sermon",
    sermon_json: dict = None,
    tags: list = None,
) -> Optional[str]:
    """Save a generated sermon. Returns saved record ID or None on failure."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase not configured — skipping sermon save")
        return None
    try:
        word_count = len(content.split())
        data = {
            "user_id": user_id,
            "title": title,
            "content": content,
            "scripture": scripture,
            "tone": tone,
            "denomination": denomination,
            "sermon_length": sermon_length,
            "output_type": output_type,
            "sermon_json": sermon_json or {},
            "word_count": word_count,
            "tags": tags or [],
            "generated_at": _now(),
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/pastor_sermons",
                headers=_headers(),
                json=data,
            )
        if r.status_code in (200, 201):
            rows = r.json()
            saved_id = rows[0]["id"] if rows else None
            logger.info("✅ sermon saved: %s", saved_id)
            return saved_id
        else:
            logger.warning("sermon save failed %s: %s", r.status_code, r.text[:200])
            return None
    except Exception as e:
        logger.warning("sermon save error: %s", e)
        return None


async def save_bible_study(
    user_id: str,
    title: str,
    content: str,
    book: str = "",
    passage: str = "",
    audience: str = "adults",
    version: str = "NIV",
    topic: str = "",
    study_json: dict = None,
    tags: list = None,
) -> Optional[str]:
    """Save a generated Bible study. Returns saved record ID or None."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        data = {
            "user_id": user_id,
            "title": title,
            "content": content,
            "book": book,
            "passage": passage,
            "audience": audience,
            "version": version,
            "topic": topic,
            "study_json": study_json or {},
            "tags": tags or [],
            "generated_at": _now(),
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/pastor_bible_studies",
                headers=_headers(),
                json=data,
            )
        if r.status_code in (200, 201):
            rows = r.json()
            saved_id = rows[0]["id"] if rows else None
            logger.info("✅ bible study saved: %s", saved_id)
            return saved_id
        else:
            logger.warning("bible study save failed %s: %s", r.status_code, r.text[:200])
            return None
    except Exception as e:
        logger.warning("bible study save error: %s", e)
        return None


async def save_transcript(
    user_id: str,
    transcript_text: str,
    duration_sec: float = 0,
    language: str = "en",
    confidence: float = 0,
    source: str = "whisper",
) -> Optional[str]:
    """Save a transcript. Returns saved record ID or None."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        data = {
            "user_id": user_id,
            "transcript_text": transcript_text,
            "duration_sec": duration_sec,
            "language": language,
            "confidence": confidence,
            "source": source,
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/pastor_transcripts",
                headers=_headers(),
                json=data,
            )
        if r.status_code in (200, 201):
            rows = r.json()
            return rows[0]["id"] if rows else None
        return None
    except Exception as e:
        logger.warning("transcript save error: %s", e)
        return None


async def get_user_sermons(user_id: str, limit: int = 50) -> list:
    """Fetch all saved sermons for a user."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/pastor_sermons?user_id=eq.{user_id}&limit={limit}&order=created_at.desc",
                headers=_headers(),
            )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        logger.warning("get sermons error: %s", e)
        return []


async def get_user_bible_studies(user_id: str, limit: int = 50) -> list:
    """Fetch all saved Bible studies for a user."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/pastor_bible_studies?user_id=eq.{user_id}&limit={limit}&order=created_at.desc",
                headers=_headers(),
            )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        logger.warning("get bible studies error: %s", e)
        return []


async def get_user_transcripts(user_id: str, limit: int = 50) -> list:
    """Fetch all saved transcripts for a user."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/pastor_transcripts?user_id=eq.{user_id}&limit={limit}&order=created_at.desc",
                headers=_headers(),
            )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        logger.warning("get transcripts error: %s", e)
        return []


async def delete_item(table: str, item_id: str, user_id: str) -> bool:
    """Delete an item by ID, scoped to user for safety."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.delete(
                f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{item_id}&user_id=eq.{user_id}",
                headers=_headers(),
            )
        return r.status_code in (200, 204)
    except Exception as e:
        logger.warning("delete error: %s", e)
        return False

async def save_generated_content(
    user_id: str,
    title: str,
    content: str,
    content_type: str = "devotional",  # devotional | counseling | discipleship | theology
    topic: str = "",
    scripture: str = "",
) -> Optional[str]:
    """Save devotional/counseling/discipleship/theology to pastor_transcripts with type tag."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        data = {
            "user_id": user_id,
            "transcript_text": content,
            "duration_sec": 0,
            "language": "en",
            "confidence": 1.0,
            "source": content_type,
            "title": title,
            "topic": topic,
            "scripture": scripture,
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/pastor_transcripts",
                headers=_headers(),
                json=data,
            )
        if r.status_code in (200, 201):
            rows = r.json()
            return rows[0]["id"] if rows else None
        return None
    except Exception as e:
        logger.warning("content save error (%s): %s", content_type, e)
        return None


async def save_recording(
    user_id: str,
    title: str,
    transcript: str = "",
    summary: str = "",
    duration_sec: int = 0,
    tags: list = None,
) -> Optional[str]:
    """Save a transcription recording. Returns saved record ID or None on failure."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase not configured — skipping recording save")
        return None
    try:
        data = {
            "user_id": user_id,
            "title": title,
            "transcript": transcript,
            "summary": summary,
            "duration_sec": duration_sec,
            "tags": tags or [],
            "generated_at": _now(),
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/pastor_recordings",
                headers=_headers(),
                json=data,
            )
        if r.status_code in (200, 201):
            rows = r.json()
            saved_id = rows[0]["id"] if rows else None
            logger.info("✅ recording saved: %s", saved_id)
            return saved_id
        else:
            logger.warning("recording save failed %s: %s", r.status_code, r.text[:200])
            return None
    except Exception as e:
        logger.warning("recording save error: %s", e)
        return None


async def get_user_recordings(user_id: str, limit: int = 50) -> list:
    """Fetch recordings for a user."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        params = {
            "user_id": f"eq.{user_id}",
            "order": "generated_at.desc",
            "limit": str(limit),
        }
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/pastor_recordings",
                headers=_headers(),
                params=params,
            )
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        logger.warning("get_user_recordings error: %s", e)
        return []
