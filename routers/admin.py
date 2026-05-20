"""
/v1/admin/* — Admin tools, stats, user management
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os

router = APIRouter(prefix="/v1/admin", tags=["Admin"])

class AdminRequest(BaseModel):
    email: str

@router.get("/stats")
async def admin_stats():
    return {
        "success": True,
        "version": "9.0.0-orchestration",
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
        "time": datetime.now(timezone.utc).isoformat(),
    }

@router.post("/grant")
async def admin_grant(payload: AdminRequest):
    FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com"}
    is_founder = payload.email.lower().strip() in FOUNDER_EMAILS
    return {"success": True, "email": payload.email, "granted": True,
            "role": "super_admin" if is_founder else "admin",
            "plan": "founder" if is_founder else "admin"}
