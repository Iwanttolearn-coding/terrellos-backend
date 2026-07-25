"""
usage_logger.py — TerrellOS / Pastor AI usage logger
Logs successful generative AI actions.
Writes to Supabase `ai_usage_logs` table for persistence.
Falls back to in-memory ring buffer if Supabase is unavailable.
Non-blocking: logging failures never surface to the caller.
"""
from datetime import datetime, timezone
from collections import deque
from typing import Optional
import os, httpx, traceback, asyncio

# In-memory ring buffer fallback — last 1000 entries
_LOG_STORE: deque = deque(maxlen=1000)

# Supabase config (same project used by pastor_db.py)
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

# Credit costs per Pastor AI endpoint
CREDIT_COSTS: dict = {
    # Pastor AI
    "/v1/pastor/sermon":         5,
    "/v1/pastor/bible-study":    3,
    "/v1/pastor/devotional":     2,
    "/v1/pastor/theology":       2,
    "/v1/pastor/counseling":     2,
    "/v1/pastor/discipleship":   2,
    "/v1/pastor/church-history": 2,
    "/v1/pastor/martyr-study":   2,
    "/v1/pastor/apologetics":    2,
    "/v1/pastor/history/search": 1,
    "/v1/pastor/recordings":     1,
    # TerrellOS core
    "/v1/core/chat":              1,
    "/v1/voice/speak":            2,
    "/v1/voice/transcribe-upload":2,
    "/v1/voice/transcribe":       2,
    "/v1/design/generate-image":  5,
    "/v1/design/memorial-image":  5,
    "/v1/design/vectorize-prompt":1,
    "/v1/tattoo/generate":        5,
    "/v1/tattoo/outline":         3,
    "/v1/tattoo/upscale":         4,
    "/v1/tattoo/vectorize":       3,
    "/v1/tattoo/variations":      5,
    "default":                    1,
}

TABLE = "ai_usage_logs"


def _supabase_headers() -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


async def _persist_to_supabase(entry: dict) -> bool:
    """Write one log entry to Supabase. Returns True on success."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{TABLE}",
                headers=_supabase_headers(),
                json=entry,
            )
            return r.status_code in (200, 201)
    except Exception:
        return False


def log_usage(
    endpoint: str,
    user_id: str,
    status: str = "success",
    model: Optional[str] = None,
    provider: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Fire-and-forget usage log. Never raises.
    Call after a successful generative action.
    Writes to Supabase `ai_usage_logs` and local ring buffer.
    """
    try:
        credits = CREDIT_COSTS.get(endpoint, CREDIT_COSTS["default"])
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "user_id": user_id or "anonymous",
            "credits_used": credits,
            "status": status,
            "app": "pastor_ai" if "/pastor/" in endpoint else "terrellos",
        }
        if model:    entry["model"]    = model
        if provider: entry["provider"] = provider
        if extra:
            entry.update({k: str(v)[:200] for k, v in extra.items()
                         if k not in entry})

        # Always write to in-memory buffer
        _LOG_STORE.append(entry)

        # Fire-and-forget async write to Supabase
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_persist_to_supabase(entry))
            else:
                asyncio.run(_persist_to_supabase(entry))
        except Exception:
            pass  # Supabase write failure is silent

    except Exception:
        pass


def get_logs(limit: int = 100, user_id: Optional[str] = None) -> list:
    """Return recent logs from in-memory buffer, optionally filtered by user."""
    logs = list(_LOG_STORE)
    logs.reverse()
    if user_id:
        logs = [l for l in logs if l.get("user_id") == user_id]
    return logs[:limit]


def get_stats() -> dict:
    logs = list(_LOG_STORE)
    total_credits = sum(l.get("credits_used", 0) for l in logs)
    pastor_credits = sum(l.get("credits_used", 0) for l in logs if l.get("app") == "pastor_ai")
    return {
        "jobs_logged": len(logs),
        "total_credits_used": total_credits,
        "pastor_ai_credits": pastor_credits,
        "endpoints": list({l["endpoint"] for l in logs}),
    }
