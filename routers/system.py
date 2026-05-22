"""
/v1/system/* — TerrellOS system telemetry routes
Provides: stats, recent-jobs, health summary
"""
from fastapi import APIRouter
from datetime import datetime, timezone
import os, time

router = APIRouter(prefix="/v1/system", tags=["System"])

# In-memory job log (populated by other routers on each request)
_recent_jobs = []
MAX_JOBS = 50

def log_job(job_type: str, status: str = "done", detail: str = ""):
    """Called by other routers to record activity."""
    _recent_jobs.insert(0, {
        "type":   job_type,
        "status": status,
        "detail": detail,
        "ts":     datetime.now(timezone.utc).isoformat(),
    })
    while len(_recent_jobs) > MAX_JOBS:
        _recent_jobs.pop()

START_TIME = time.time()

@router.get("/stats")
async def system_stats():
    uptime_sec = int(time.time() - START_TIME)
    return {
        "success": True,
        "stats": {
            "uptime_sec":    uptime_sec,
            "uptime_human":  f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m",
            "jobs_logged":   len(_recent_jobs),
            "backend":       os.getenv("FLY_APP_NAME", "terrellos-backend"),
            "region":        os.getenv("FLY_REGION", "local"),
            "environment":   "production",
            "openai_key":    "configured" if os.getenv("OPENAI_API_KEY") else "missing",
            "elevenlabs_key":"configured" if os.getenv("ELEVENLABS_API_KEY") else "missing",
        }
    }

@router.get("/recent-jobs")
async def recent_jobs():
    return {
        "success": True,
        "jobs":    _recent_jobs[:20],
        "total":   len(_recent_jobs),
    }

@router.get("/health")
async def system_health():
    return {
        "success":     True,
        "status":      "online",
        "openai":      "configured" if os.getenv("OPENAI_API_KEY") else "missing",
        "elevenlabs":  "configured" if os.getenv("ELEVENLABS_API_KEY") else "missing",
        "uptime_sec":  int(time.time() - START_TIME),
    }
