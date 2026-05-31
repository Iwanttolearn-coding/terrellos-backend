"""
/v1/auth/* — TerrellOS auth endpoints (JWT-based, stateless)
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import os, jwt

router = APIRouter(prefix="/v1/auth", tags=["Auth"])

FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com"}
JWT_SECRET     = os.getenv("JWT_SECRET", "terrellos-default-secret-change-in-prod")
JWT_ALGORITHM  = "HS256"
JWT_EXPIRES_DAYS = 30


def create_token(payload: dict) -> str:
    data = {**payload, "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRES_DAYS)}
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def email_from_request(request: Request) -> str:
    """Extract user email from Authorization header JWT."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        return ""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("email", "")
    except Exception:
        return ""


class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = None


@router.post("/login")
async def login(payload: LoginRequest):
    email = payload.email.lower().strip()
    is_founder = email in FOUNDER_EMAILS

    if not is_founder:
        raise HTTPException(status_code=401, detail="Auth system: only founder emails supported")

    token_data = {
        "email": email,
        "role": "super_admin",
        "plan": "elite",
        "all_tools_access": True,
        "is_founder": True,
    }
    token = create_token(token_data)
    return {
        "success": True,
        "token": token,
        "user": {**token_data, "display_name": "Terrell Millz"},
        "message": "Founder access granted",
    }


@router.get("/me")
async def me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    data = decode_token(token)
    return {"success": True, "user": data}


@router.post("/logout")
async def logout():
    # Stateless JWT — just confirm logout on client side
    return {"success": True, "message": "Logged out"}


@router.post("/founder-bypass")
async def founder_bypass(payload: LoginRequest):
    email = payload.email.lower().strip()
    if email not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Not a founder email")
    token_data = {
        "email": email,
        "display_name": "Terrell Millz",
        "role": "super_admin",
        "plan": "elite",
        "all_tools_access": True,
        "is_founder": True,
    }
    token = create_token(token_data)
    return {"success": True, "token": token, "user": token_data}
