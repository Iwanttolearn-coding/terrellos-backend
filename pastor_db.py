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


async def _post_with_retry(url: str, data: dict, retries: int = 1):
    """POST to Supabase REST with one automatic retry on transient failure.
    Returns (status_code, response_text_or_json)."""
    import asyncio as _asyncio
    last_status, last_text = None, None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(url, headers={**_headers(), "Prefer": "return=representation"}, json=data)
            if r.status_code in (200, 201):
                return r.status_code, r.json()
            last_status, last_text = r.status_code, r.text[:300]
        except Exception as e:
            last_status, last_text = None, str(e)
        if attempt < retries:
            await _asyncio.sleep(0.8)
    return last_status, last_text


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
        status, result = await _post_with_retry(f"{SUPABASE_URL}/rest/v1/pastor_sermons", data)
        if status in (200, 201):
            saved_id = result[0]["id"] if result else None
            logger.info("✅ sermon saved: %s", saved_id)
            return saved_id
        else:
            logger.error("sermon save failed after retry — status=%s detail=%s", status, result)
            return None
    except Exception as e:
        logger.error("sermon save error: %s", e)
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
        status, result = await _post_with_retry(f"{SUPABASE_URL}/rest/v1/pastor_bible_studies", data)
        if status in (200, 201):
            saved_id = result[0]["id"] if result else None
            logger.info("✅ bible study saved: %s", saved_id)
            return saved_id
        else:
            logger.error("bible study save failed after retry — status=%s detail=%s", status, result)
            return None
    except Exception as e:
        logger.error("bible study save error: %s", e)
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
                headers={**_headers(), "Prefer": "return=representation"},
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
                f"{SUPABASE_URL}/rest/v1/pastor_sermons?user_id=eq.{user_id}&limit={limit}&order=generated_at.desc",
                headers=_headers(),
            )
        if r.status_code == 200:
            return r.json()
        logger.error("get sermons failed — status=%s body=%s", r.status_code, r.text[:300])
        return []
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
                f"{SUPABASE_URL}/rest/v1/pastor_bible_studies?user_id=eq.{user_id}&limit={limit}&order=generated_at.desc",
                headers=_headers(),
            )
        if r.status_code == 200:
            return r.json()
        logger.error("get bible studies failed — status=%s body=%s", r.status_code, r.text[:300])
        return []
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
                f"{SUPABASE_URL}/rest/v1/pastor_transcripts?user_id=eq.{user_id}&limit={limit}&order=id.desc",
                headers=_headers(),
            )
        if r.status_code == 200:
            return r.json()
        logger.error("get transcripts failed — status=%s body=%s", r.status_code, r.text[:300])
        return []
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
                headers={**_headers(), "Prefer": "return=representation"},
                json=data,
            )
        if r.status_code in (200, 201):
            rows = r.json()
            return rows[0]["id"] if rows else None
        return None
    except Exception as e:
        logger.warning("content save error (%s): %s", content_type, e)
        return None



async def ensure_pastor_recordings_table() -> bool:
    """Create pastor_recordings table if it doesn't exist. Safe to call on every startup."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    # Supabase pg_catalog approach — use RPC exec_sql or direct table probe
    # Try inserting/selecting to detect table existence
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/pastor_recordings?limit=1",
                headers=_headers(),
            )
        if r.status_code == 200:
            return True  # Table exists
        # 404 / 42P01 = table missing — create it via Supabase SQL RPC
        sql = """
            CREATE TABLE IF NOT EXISTS pastor_recordings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'Untitled Recording',
                transcript TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                duration_sec INTEGER DEFAULT 0,
                tags TEXT[] DEFAULT ARRAY[]::TEXT[],
                audio_url TEXT,
                generated_at TIMESTAMPTZ DEFAULT now(),
                created_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_pastor_recordings_user ON pastor_recordings(user_id);
        """
        async with httpx.AsyncClient(timeout=15) as c:
            rpc = await c.post(
                f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
                headers=_headers(),
                json={"query": sql},
            )
        logger.info("pastor_recordings table create attempt: %s", rpc.status_code)
        return rpc.status_code in (200, 201, 204)
    except Exception as e:
        logger.warning("ensure_pastor_recordings_table error: %s", e)
        return False

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
    import uuid as _uuid
    try:
        record_id = str(_uuid.uuid4())
        data = {
            "id":           record_id,
            "user_id":      user_id or "anonymous",
            "title":        title,
            "transcript":   transcript,
            "summary":      summary,
            "duration_sec": duration_sec,
            "tags":         tags or [],
            "generated_at": _now(),
        }
        # Use service-role key so RLS doesn't block anonymous saves
        svc_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_KEY
        svc_headers = {
            "apikey":        svc_key,
            "Authorization": f"Bearer {svc_key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=representation",
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{SUPABASE_URL}/rest/v1/pastor_recordings",
                headers=svc_headers,
                json=data,
            )
        if r.status_code in (200, 201):
            rows = r.json()
            saved_id = rows[0]["id"] if rows else record_id
            logger.info("✅ recording saved: %s", saved_id)
            return saved_id
        else:
            logger.warning("recording save failed %s: %s", r.status_code, r.text[:200])
            # Return the pre-generated UUID even if DB save failed — client can use it
            return record_id
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


async def ensure_saved_items_table() -> bool:
    """Create saved_items table if it does not exist. Safe to call on every startup."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/saved_items?limit=1",
                headers=_headers(),
            )
        if r.status_code == 200:
            return True  # table already exists
        # Table does not exist — create via Supabase SQL RPC
        create_sql = """
CREATE TABLE IF NOT EXISTS public.saved_items (
  id           TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_email   TEXT        NOT NULL,
  type         TEXT        NOT NULL,
  title        TEXT        NOT NULL,
  content      JSONB       NOT NULL DEFAULT '{}',
  app_id       TEXT        NOT NULL DEFAULT 'pastor-ai-connect',
  tags         JSONB       NOT NULL DEFAULT '[]',
  notes        TEXT        NOT NULL DEFAULT '',
  metadata     JSONB       NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_saved_items_user_email ON public.saved_items (user_email);
CREATE INDEX IF NOT EXISTS idx_saved_items_app_id     ON public.saved_items (app_id);
CREATE INDEX IF NOT EXISTS idx_saved_items_type       ON public.saved_items (type);
"""
        async with httpx.AsyncClient(timeout=20) as c:
            r2 = await c.post(
                f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
                headers=_headers(),
                json={"sql": create_sql},
            )
        return r2.status_code in (200, 201, 204)
    except Exception as e:
        logger.warning(f"ensure_saved_items_table: {e}")
        return False
