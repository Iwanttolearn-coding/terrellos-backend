"""
/v1/auth/* — TerrellOS auth endpoints (JWT-based, stateless)
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import os, jwt, uuid

router = APIRouter(prefix="/v1/auth", tags=["Auth"])

FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com"}
JWT_SECRET     = os.getenv("JWT_SECRET", "terrellos-default-secret-change-in-prod")
JWT_ALGORITHM  = "HS256"
JWT_EXPIRES_DAYS = 30

# Simple in-memory user store for non-founder registered users
# (Production: replace with Supabase auth.users table)
_REGISTERED_USERS: dict = {}


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


@router.post("/register")
async def register(payload: RegisterRequest):
    """Register a new user. Founders get super_admin, others get standard trial plan."""
    email = payload.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email address required")
    if len(payload.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    is_founder = email in FOUNDER_EMAILS

    # Check if already registered (in-memory store)
    if email in _REGISTERED_USERS and not is_founder:
        # Allow re-registration without error — just return token
        pass

    user_id = str(uuid.uuid4())
    token_data = {
        "email": email,
        "user_id": user_id,
        "full_name": payload.full_name or email.split("@")[0],
        "role": "super_admin" if is_founder else "user",
        "plan": "elite" if is_founder else "free",
        "all_tools_access": is_founder,
        "is_founder": is_founder,
    }

    # Persist in memory store
    _REGISTERED_USERS[email] = {
        **token_data,
        "password_hint": payload.password[:2] + "***",  # Never store plaintext
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }

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

    # Check registered users
    if email in _REGISTERED_USERS:
        user = _REGISTERED_USERS[email]
        token = create_token({k: v for k, v in user.items() if k not in ("password_hint", "registered_at")})
        return {
            "success": True,
            "token": token, "access_token": token,
            "user": user,
            "message": "Welcome back",
        }

    raise HTTPException(status_code=401, detail="Email not found. Please register first.")


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
    return {"success": True, "message": "Logged out"}



class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    phone:        Optional[str] = None
    business_name:Optional[str] = None
    avatar_url:   Optional[str] = None
    preferences:  Optional[dict] = None


# Immutable fields — never allow user to self-update these
_PROTECTED_FIELDS = {"role", "plan", "is_founder", "all_tools_access", "credits",
                     "email", "user_id", "exp", "iat"}

# In-memory profile store (augments JWT claims)
_PROFILE_STORE: dict = {}


@router.patch("/me")
async def update_me(payload: ProfileUpdateRequest, request: Request):
    """
    Allow the authenticated user to update safe profile fields only.
    Protected fields (role, plan, is_founder, email, credits) are
    silently ignored — never exposed as an error.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    claims = decode_token(token)
    email  = claims.get("email", "")
    if not email:
        raise HTTPException(status_code=401, detail="Could not identify user from token")

    # Build update dict from only the safe, non-None fields supplied
    safe_updates: dict = {}
    for field, val in payload.model_dump(exclude_none=True).items():
        if field not in _PROTECTED_FIELDS and val is not None:
            safe_updates[field] = val

    # Merge into profile store
    existing = _PROFILE_STORE.get(email, {})
    existing.update(safe_updates)
    existing["email"]      = email        # always preserve
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    _PROFILE_STORE[email]  = existing

    # Also update _REGISTERED_USERS if this is a registered user
    if email in _REGISTERED_USERS:
        for k, v in safe_updates.items():
            _REGISTERED_USERS[email][k] = v

    return {
        "success": True,
        "message": "Profile updated",
        "profile": {**claims, **{k: v for k, v in existing.items()
                                 if k not in _PROTECTED_FIELDS}},
        "updated_fields": list(safe_updates.keys()),
    }


@router.get("/me/profile")
async def get_profile(request: Request):
    """
    Return full profile: JWT claims merged with stored profile fields.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    claims = decode_token(token)
    email  = claims.get("email", "")
    stored = _PROFILE_STORE.get(email, {})
    return {
        "success": True,
        "user": {
            **claims,
            **{k: v for k, v in stored.items() if k not in _PROTECTED_FIELDS},
        },
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
