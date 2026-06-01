"""
usage_logger.py — TerrellOS job/credit usage logger
Logs successful generative AI actions to an in-memory ring buffer.
Non-blocking: logging failures never surface to the caller.
Production upgrade path: swap _LOG_STORE for a Supabase insert.
"""
from datetime import datetime, timezone
from collections import deque
from typing import Optional
import traceback

# In-memory ring buffer — last 1000 log entries
_LOG_STORE: deque = deque(maxlen=1000)

# Credit costs per endpoint (tuneable via env or future DB table)
CREDIT_COSTS: dict = {
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
    """
    try:
        credits = CREDIT_COSTS.get(endpoint, CREDIT_COSTS["default"])
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "user_id": user_id or "anonymous",
            "credits_used": credits,
            "status": status,
        }
        if model:    entry["model"]    = model
        if provider: entry["provider"] = provider
        if extra:    entry.update({k: v for k, v in extra.items()
                                   if k not in entry})
        _LOG_STORE.append(entry)
    except Exception:
        # Log failure is silent — never propagate
        pass


def get_logs(limit: int = 100, user_id: Optional[str] = None) -> list:
    """Return recent logs, optionally filtered by user."""
    logs = list(_LOG_STORE)
    logs.reverse()          # newest first
    if user_id:
        logs = [l for l in logs if l.get("user_id") == user_id]
    return logs[:limit]


def get_stats() -> dict:
    logs = list(_LOG_STORE)
    total_credits = sum(l.get("credits_used", 0) for l in logs)
    return {
        "jobs_logged": len(logs),
        "total_credits_used": total_credits,
        "endpoints": list({l["endpoint"] for l in logs}),
    }
