"""
/v1/admin/* — Admin tools, stats, user management
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os

router = APIRouter(prefix="/v1/admin", tags=["Admin"])

class AdminRequest(BaseModel):
    email: str

class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    plan: Optional[str] = None
    notes: Optional[str] = None


@router.get("/stats")
async def admin_stats():
    return {
        "success": True,
        "version": "9.1.0-pastor-patch",
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
        "supabase": bool(os.getenv("SUPABASE_URL")),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/users")
async def admin_users(request: Request):
    """Return registered user list. Pulls from auth module's in-memory store."""
    try:
        from routers.auth import _REGISTERED_USERS, FOUNDER_EMAILS
        # Also include founders as synthetic entries
        all_users = {}
        for email in FOUNDER_EMAILS:
            all_users[email] = {
                "email": email,
                "role": "super_admin",
                "plan": "elite",
                "is_founder": True,
                "registered_at": "2026-01-01T00:00:00+00:00",
            }
        # Override with real registered data
        for email, data in _REGISTERED_USERS.items():
            all_users[email] = data
        users = list(all_users.values())
    except Exception as e:
        users = []
    return {
        "success": True,
        "users": users,
        "count": len(users),
    }


@router.patch("/users/{user_id}")
async def admin_update_user(user_id: str, payload: UpdateUserRequest):
    """Update a user's role or plan. user_id is email in this system."""
    try:
        from routers.auth import _REGISTERED_USERS
        email = user_id.lower().strip()
        if email in _REGISTERED_USERS:
            if payload.role:
                _REGISTERED_USERS[email]["role"] = payload.role
            if payload.plan:
                _REGISTERED_USERS[email]["plan"] = payload.plan
            return {"success": True, "updated": email, "data": _REGISTERED_USERS[email]}
        else:
            return {"success": True, "updated": email, "message": "User not in registry (founder or external)"}
    except Exception as e:
        raise HTTPException(500, f"Update failed: {e}")


@router.get("/logs")
async def admin_logs(request: Request, limit: int = 50):
    """Return recent system activity logs from Supabase if available."""
    logs = []
    try:
        import httpx
        SUPABASE_URL = os.getenv("SUPABASE_URL", "")
        SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
        if SUPABASE_URL and SUPABASE_KEY:
            headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            }
            async with httpx.AsyncClient(timeout=10) as c:
                # Try pastor_ai_logs table first
                r = await c.get(
                    f"{SUPABASE_URL}/rest/v1/pastor_ai_logs",
                    headers=headers,
                    params={"order": "created_at.desc", "limit": limit},
                )
                if r.status_code == 200:
                    logs = r.json()
                else:
                    # Fallback: try generation_history
                    r2 = await c.get(
                        f"{SUPABASE_URL}/rest/v1/generation_history",
                        headers=headers,
                        params={"order": "created_at.desc", "limit": limit},
                    )
                    if r2.status_code == 200:
                        logs = r2.json()
    except Exception as e:
        logs = [{"message": f"Log fetch error: {str(e)}", "timestamp": datetime.now(timezone.utc).isoformat()}]

    return {
        "success": True,
        "logs": logs,
        "count": len(logs),
    }


@router.post("/grant")
async def admin_grant(payload: AdminRequest):
    FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com"}
    is_founder = payload.email.lower().strip() in FOUNDER_EMAILS
    return {"success": True, "email": payload.email, "granted": True,
            "role": "super_admin" if is_founder else "admin",
            "plan": "founder" if is_founder else "admin"}
