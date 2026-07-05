"""
/v1/founder/* — Founder-only orchestration, ecosystem control, audit logs
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

router = APIRouter(prefix="/v1/founder", tags=["Founder"])

FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com", "millsterrell5@gmail.com"}
AUDIT_LOG = []

def verify_founder(email: str):
    if not email or email.lower().strip() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Founder access required")

class FounderRequest(BaseModel):
    email: str

class AuditLogRequest(BaseModel):
    email: str
    action: str
    details: Optional[str] = None

@router.post("/verify")
async def verify(payload: FounderRequest):
    is_f = payload.email.lower().strip() in FOUNDER_EMAILS
    return {"success": True, "is_founder": is_f,
            "access_level": "full_system" if is_f else "none"}

@router.post("/audit-log")
async def audit_log(payload: AuditLogRequest):
    verify_founder(payload.email)
    entry = {"id": len(AUDIT_LOG)+1, "email": payload.email, "action": payload.action,
             "details": payload.details, "timestamp": datetime.now(timezone.utc).isoformat()}
    AUDIT_LOG.append(entry)
    return {"success": True, "logged": entry}

@router.get("/audit-log/{email}")
async def get_audit_log(email: str):
    verify_founder(email)
    return {"success": True, "log": AUDIT_LOG[-50:], "total": len(AUDIT_LOG)}

@router.get("/ecosystem-status/{email}")
async def ecosystem_status(email: str):
    verify_founder(email)
    from app import APP_REGISTRY
    import os
    return {
        "success": True,
        "apps": APP_REGISTRY,
        "backend_version": "9.0.0-orchestration",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "elevenlabs_configured": bool(os.getenv("ELEVENLABS_API_KEY")),
        "time": datetime.now(timezone.utc).isoformat(),
    }
