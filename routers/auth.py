"""
/v1/auth/* — TerrellOS auth endpoints (JWT-based, persistent Supabase-backed users)
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import os, jwt, uuid

from routers import user_store

router = APIRouter(prefix="/v1/auth", tags=["Auth"])

FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com", "millsterrell5@gmail.com"}
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


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = ""
    app_id: Optional[str] = ""


def _token_data_from_row(row: dict) -> dict:
    return {
        "email": row.get("email"),
        "user_id": row.get("id"),
        "full_name": row.get("full_name"),
        "role": row.get("role", "user"),
        "plan": row.get("plan", "free"),
        "all_tools_access": row.get("role") == "super_admin",
        "is_founder": (row.get("email") or "").lower().strip() in FOUNDER_EMAILS,
    }


@router.post("/register")
async def register(payload: RegisterRequest):
    """Register a new user. Founders get super_admin, others get standard free plan.
    Passwords are hashed (PBKDF2-HMAC-SHA256) and stored persistently in Supabase —
    never in memory, never in plaintext."""
    email = payload.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email address required")
    if not payload.password or len(payload.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    if not user_store.configured():
        raise HTTPException(503, "Account storage is not configured — please try again shortly")

    is_founder = email in FOUNDER_EMAILS

    existing = await user_store.get_user_by_email(email)
    if existing:
        raise HTTPException(409, "An account with this email already exists. Please log in instead.")

    row = await user_store.create_user(email, payload.password, payload.full_name or "")
    if is_founder:
        row = await user_store.update_user(email, {"role": "super_admin", "plan": "elite"}) or row

    token_data = _token_data_from_row(row)
    token = create_token(token_data)
    return {
        "success": True,
        "token": token, "access_token": token,
        "user": token_data,
        "message": "Account created successfully",
    }


@router.post("/login")
async def login(payload: LoginRequest):
    email = payload.email.lower().strip()
    is_founder = email in FOUNDER_EMAILS

    if is_founder:
        # Founder override remains a server-side hardcoded bypass (per standing instructions) —
        # never gated on the password-store lookup.
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
            "token": token, "access_token": token,
            "user": {**token_data, "display_name": "Terrell Millz"},
            "message": "Founder access granted",
        }

    if not user_store.configured():
        raise HTTPException(503, "Account storage is not configured — please try again shortly")

    row = await user_store.get_user_by_email(email)
    if not row:
        raise HTTPException(status_code=401, detail="Email not found. Please register first.")

    if not payload.password or not user_store.verify_password(payload.password, row.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token_data = _token_data_from_row(row)
    token = create_token(token_data)
    return {
        "success": True,
        "token": token, "access_token": token,
        "user": token_data,
        "message": "Welcome back",
    }


@router.get("/me")
async def me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    data = decode_token(token)

    # Enrich with LIVE subscription state from user_subscriptions (Supabase) —
    # never trust a stale "plan" claim baked into the JWT at login time.
    email = data.get("email", "")
    if email:
        try:
            from routers.paypal import get_subscription, has_active_access
            sub = await get_subscription(email)
            active = await has_active_access(email)
            is_founder = email.lower().strip() in FOUNDER_EMAILS
            data["plan"] = "founder" if is_founder else (sub.get("plan_name", "free") if active else "free")
            data["is_founder"] = is_founder
            data["has_active_subscription"] = bool(active)
            data["subscription_status"] = sub.get("status", "inactive") if sub else "inactive"
            data["plan_expires_at"] = sub.get("current_period_end") if sub else None
        except Exception:
            pass

    return {"success": True, "user": data}


@router.post("/logout")
async def logout():
    return {"success": True, "message": "Logged out"}


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    phone:        Optional[str] = None
    business_name:Optional[str] = None
    avatar_url:   Optional[str] = None
    preferences:  Optional[dict] = None


# Immutable fields — never allow user to self-update these
_PROTECTED_FIELDS = {"role", "plan", "is_founder", "all_tools_access", "credits",
                     "email", "user_id", "id", "password_hash", "exp", "iat"}


@router.patch("/me")
async def update_me(payload: ProfileUpdateRequest, request: Request):
    """
    Allow the authenticated user to update safe profile fields only.
    Protected fields (role, plan, is_founder, email, credits) are
    silently ignored — never exposed as an error. Persisted in Supabase,
    survives deploys/restarts.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    claims = decode_token(token)
    email  = claims.get("email", "")
    if not email:
        raise HTTPException(status_code=401, detail="Could not identify user from token")

    if email.lower().strip() in FOUNDER_EMAILS:
        # Founders aren't in app_users; just echo back the update (nothing to persist against).
        return {"success": True, "message": "Profile updated", "profile": claims,
                "updated_fields": list(payload.model_dump(exclude_none=True).keys())}

    safe_updates: dict = {}
    for field, val in payload.model_dump(exclude_none=True).items():
        if field not in _PROTECTED_FIELDS and val is not None:
            safe_updates[field] = val

    if not safe_updates:
        return {"success": True, "message": "Nothing to update", "profile": claims, "updated_fields": []}

    try:
        updated_row = await user_store.update_user(email, safe_updates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile update failed: {e}")

    profile = user_store.public_user(updated_row) if updated_row else {**claims, **safe_updates}
    return {
        "success": True,
        "message": "Profile updated",
        "profile": profile,
        "updated_fields": list(safe_updates.keys()),
    }


@router.get("/me/profile")
async def get_profile(request: Request):
    """
    Return full profile from Supabase (persistent), merged with JWT claims.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    claims = decode_token(token)
    email  = claims.get("email", "")

    if email.lower().strip() in FOUNDER_EMAILS:
        return {"success": True, "user": {**claims, "display_name": "Terrell Millz"}}

    row = await user_store.get_user_by_email(email) if user_store.configured() else None
    stored = user_store.public_user(row) if row else {}
    return {
        "success": True,
        "user": {**claims, **stored},
    }


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
    return {"success": True, "token": token, "access_token": token, "user": token_data}

@router.get("/health")
async def auth_health():
    return {"success": True, "status": "online", "service": "Auth",
             "supabase": user_store.configured(), "storage": "persistent"}
