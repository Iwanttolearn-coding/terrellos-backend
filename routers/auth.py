"""
/v1/auth/* — TerrellOS auth endpoints
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os, secrets

router = APIRouter(prefix="/v1/auth", tags=["Auth"])

FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com"}

# Simple in-memory token store (replace with DB in production)
_TOKENS: dict = {}

class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = None  # optional for founder bypass

@router.post("/login")
async def login(payload: LoginRequest):
    email = payload.email.lower().strip()
    is_founder = email in FOUNDER_EMAILS
    
    if not is_founder:
        # Non-founders need a real auth system — placeholder
        raise HTTPException(status_code=401, detail="Auth system not yet configured for non-founders")
    
    token = secrets.token_urlsafe(32)
    _TOKENS[token] = {
        "email": email,
        "role": "super_admin",
        "plan": "elite",
        "all_tools_access": True,
        "is_founder": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "success": True,
        "token": token,
        "user": _TOKENS[token],
        "message": "Founder access granted",
    }

@router.get("/me")
async def me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    
    user_data = _TOKENS.get(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return {"success": True, "user": user_data}

@router.post("/logout")
async def logout(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if token and token in _TOKENS:
        del _TOKENS[token]
    return {"success": True, "message": "Logged out"}

@router.post("/founder-bypass")
async def founder_bypass(payload: LoginRequest):
    """Direct founder access without password — email-gated."""
    email = payload.email.lower().strip()
    if email not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Not a founder email")
    
    token = secrets.token_urlsafe(32)
    user_data = {
        "email": email,
        "display_name": "Terrell Millz",
        "role": "super_admin",
        "plan": "elite",
        "all_tools_access": True,
        "is_founder": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TOKENS[token] = user_data
    return {"success": True, "token": token, "user": user_data}
