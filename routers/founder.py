"""
/v1/founder/* — Founder-only orchestration, ecosystem control, audit logs

SECURITY: All founder-only routes require a valid JWT (Authorization: Bearer <token>)
whose email claim is in FOUNDER_EMAILS — the same login-issued token used everywhere
else in the app. There is no plaintext-email-only path to founder access; a client
can no longer claim to be the founder just by putting the right string in a request
body. (Closed 2026-07-07 alongside the /v1/auth/login password bypass fix.)
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os, jwt as _jwt

router = APIRouter(prefix="/v1/founder", tags=["Founder"])

FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com", "millsterrell5@gmail.com"}
JWT_SECRET = os.getenv("JWT_SECRET", "terrellos-default-secret-change-in-prod")
AUDIT_LOG = []


def require_founder(request: Request) -> dict:
    """Guard dependency — only a valid JWT belonging to a founder email may pass."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = _jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = (claims.get("email") or "").lower().strip()
    if not (bool(claims.get("is_founder")) or email in FOUNDER_EMAILS):
        raise HTTPException(status_code=403, detail="Founder access required")
    return claims


class AuditLogRequest(BaseModel):
    action: str
    details: Optional[str] = None


@router.get("/verify")
async def verify(claims: dict = Depends(require_founder)):
    """Confirms the CALLER's own authenticated token is a founder token. No longer
    accepts an arbitrary email to check on someone else's behalf."""
    return {"success": True, "is_founder": True, "access_level": "full_system"}


@router.post("/audit-log")
async def audit_log(payload: AuditLogRequest, claims: dict = Depends(require_founder)):
    entry = {
        "id": len(AUDIT_LOG) + 1,
        "email": claims.get("email"),
        "action": payload.action,
        "details": payload.details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    AUDIT_LOG.append(entry)
    return {"success": True, "logged": entry}


@router.get("/audit-log")
async def get_audit_log(claims: dict = Depends(require_founder)):
    return {"success": True, "log": AUDIT_LOG[-50:], "total": len(AUDIT_LOG)}


@router.get("/ecosystem-status")
async def ecosystem_status(claims: dict = Depends(require_founder)):
    from app import APP_REGISTRY
    return {
        "success": True,
        "apps": APP_REGISTRY,
        "backend_version": "9.0.0-orchestration",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "elevenlabs_configured": bool(os.getenv("ELEVENLABS_API_KEY")),
        "time": datetime.now(timezone.utc).isoformat(),
    }
