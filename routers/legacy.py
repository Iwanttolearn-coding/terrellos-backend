"""
routers/legacy.py — HEE Legacy Profile Management
Stores and retrieves legacy/memorial profiles for Heavenly Eternal Echoes.
"""
import os, uuid, httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/v1/legacy", tags=["Legacy"])

SUPABASE_URL = os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY","")

def _headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json", "Prefer": "return=representation"}

def _now():
    return datetime.now(timezone.utc).isoformat()

class LegacyProfileCreate(BaseModel):
    user_email: str
    name: str
    birth_date: Optional[str] = None
    passing_date: Optional[str] = None
    bio: Optional[str] = ""
    memories: Optional[List[str]] = []
    photo_url: Optional[str] = None
    tribute: Optional[str] = ""

@router.get("/health")
async def legacy_health():
    return {
        "success": True, "status": "online", "service": "HEE Legacy",
        "supabase": bool(SUPABASE_URL and SUPABASE_KEY),
        "features": ["profiles","tributes","memories","eternal_tree"]
    }

@router.post("/profile")
async def create_legacy_profile(req: LegacyProfileCreate):
    if not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    record = {
        "id": str(uuid.uuid4()), "user_email": req.user_email,
        "name": req.name, "birth_date": req.birth_date,
        "passing_date": req.passing_date, "bio": req.bio,
        "memories": req.memories, "photo_url": req.photo_url,
        "tribute": req.tribute, "created_at": _now(), "updated_at": _now()
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/legacy_profiles",
            headers=_headers(), json=record)
    if r.status_code not in (200,201):
        raise HTTPException(status_code=500, detail=f"Save failed: {r.text[:200]}")
    return {"success": True, "profile_id": record["id"], "name": req.name}

@router.get("/profiles")
async def list_legacy_profiles(user_email: str):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/legacy_profiles",
            headers=_headers(),
            params={"user_email": f"eq.{user_email}", "order": "created_at.desc"})
    if r.status_code != 200:
        return {"success": True, "profiles": []}
    return {"success": True, "profiles": r.json()}
