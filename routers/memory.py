"""
/v1/memory/* — Session, fragments, profiles, consent, export
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/v1/memory", tags=["Memory"])

# In-memory store (replace with Supabase/PostgreSQL in production)
MEMORY_SESSIONS: Dict[str, Dict[str, Any]] = {}
MEMORY_PROFILES: Dict[str, Dict[str, Any]] = {}
CONSENTS: Dict[str, Dict[str, Any]] = {}

class SessionStartRequest(BaseModel):
    user_id: str
    consent_confirmed: bool = False
    voice_active: bool = False
    camera_active: bool = False
    app_id: Optional[str] = "heavenly-eternal-echo"

class SessionTranscriptRequest(BaseModel):
    session_id: str
    transcript: str

class SessionEndRequest(BaseModel):
    session_id: str

class ConsentRequest(BaseModel):
    user_id: str
    consent_confirmed: bool
    app_id: Optional[str] = "heavenly-eternal-echo"

class MemoryDeleteRequest(BaseModel):
    user_id: str


@router.get("/health")
async def memory_health():
    """Memory system health check."""
    import os
    return {
        "success": True,
        "status": "online",
        "service": "HEE Memory System",
        "supabase": bool(os.getenv("SUPABASE_URL")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "features": ["voice_interview","memory_sessions","story_fragments","consent","export"],
    }

@router.post("/session/start")
async def session_start(payload: SessionStartRequest):
    if not payload.consent_confirmed:
        raise HTTPException(status_code=400, detail="Consent required before starting memory session")
    sid = str(uuid.uuid4())
    MEMORY_SESSIONS[sid] = {
        "session_id": sid, "user_id": payload.user_id,
        "app_id": payload.app_id, "consent_confirmed": True,
        "voice_active": payload.voice_active, "camera_active": payload.camera_active,
        "transcripts": [], "frames": [], "audio": [],
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "active",
    }
    if payload.user_id not in MEMORY_PROFILES:
        MEMORY_PROFILES[payload.user_id] = {
            "user_id": payload.user_id, "memory_fragments": [],
            "voice_samples": [], "created_at": datetime.now(timezone.utc).isoformat(),
        }
    return {"success": True, "session_id": sid}

@router.post("/session/transcript")
async def session_transcript(payload: SessionTranscriptRequest):
    session = MEMORY_SESSIONS.get(payload.session_id)
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    frag = {"id": str(uuid.uuid4()), "transcript": payload.transcript,
            "created_at": datetime.now(timezone.utc).isoformat()}
    session["transcripts"].append(frag)
    uid = session["user_id"]
    if uid in MEMORY_PROFILES:
        MEMORY_PROFILES[uid]["memory_fragments"].append(frag)
    return {"success": True, "fragment_id": frag["id"]}

@router.post("/session/end")
async def session_end(payload: SessionEndRequest):
    session = MEMORY_SESSIONS.get(payload.session_id)
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    session["status"] = "ended"
    session["ended_at"] = datetime.now(timezone.utc).isoformat()
    return {"success": True, "session_id": payload.session_id, "fragments": len(session["transcripts"])}

@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    profile = MEMORY_PROFILES.get(user_id)
    if not profile: raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True, "profile": profile}

@router.post("/consent")
async def save_consent(payload: ConsentRequest):
    CONSENTS[payload.user_id] = {
        "user_id": payload.user_id, "consent_confirmed": payload.consent_confirmed,
        "app_id": payload.app_id, "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return {"success": True, "consent_saved": True}

@router.get("/export/{user_id}")
async def export_memory(user_id: str):
    profile = MEMORY_PROFILES.get(user_id, {})
    sessions = [s for s in MEMORY_SESSIONS.values() if s.get("user_id") == user_id]
    return {"success": True, "user_id": user_id, "profile": profile,
            "sessions": sessions, "total_fragments": len(profile.get("memory_fragments", []))}

@router.delete("/delete/{user_id}")
async def delete_memory(user_id: str):
    MEMORY_PROFILES.pop(user_id, None)
    to_del = [sid for sid, s in MEMORY_SESSIONS.items() if s.get("user_id") == user_id]
    for sid in to_del: del MEMORY_SESSIONS[sid]
    return {"success": True, "deleted": True, "sessions_removed": len(to_del)}
