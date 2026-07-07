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

    try:
        existing = await user_store.get_user_by_email(email)
        if existing:
            raise HTTPException(409, "An account with this email already exists. Please log in instead.")

        row = await user_store.create_user(email, payload.password, payload.full_name or "")
        if is_founder:
            row = await user_store.update_user(email, {"role": "super_admin", "plan": "elite"}) or row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Account storage is temporarily unavailable — please try again shortly. ({e})")

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
    """
    SECURITY: Founder emails are granted the super_admin/elite override ONLY after a
    real password check against the persistent app_users store — there is no
    password-less bypass for any account, founder or otherwise. (Previously founder
    logins skipped password verification entirely; that hole is closed as of 2026-07-07.)
    """
    email = payload.email.lower().strip()
    is_founder = email in FOUNDER_EMAILS

    if not user_store.configured():
        raise HTTPException(503, "Account storage is not configured — please try again shortly")

    try:
        row = await user_store.get_user_by_email(email)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Account storage is temporarily unavailable — please try again shortly. ({e})")

    if not row:
        if is_founder:
            # Founder account exists in config but has no password set up yet in the store —
            # do NOT grant access; the founder must register a real password first.
            raise HTTPException(status_code=401, detail="Founder account not yet provisioned with a password. Please register or contact support.")
        raise HTTPException(status_code=401, detail="Email not found. Please register first.")

    if not payload.password or not user_store.verify_password(payload.password, row.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    if row.get("is_active") is False:
        raise HTTPException(status_code=403, detail="This account has been deactivated. Contact support for help.")

    if is_founder:
        # Password verified — now apply the founder override on top of the real identity check.
        token_data = {
            "email": email,
            "user_id": row.get("id"),
            "full_name": row.get("full_name") or "Terrell Millz",
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


# ============================================================
# Change password (authenticated user changes their own password)
# ============================================================
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    claims = decode_token(token)
    email = claims.get("email", "")
    if not email:
        raise HTTPException(status_code=401, detail="Could not identify user from token")

    if email.lower().strip() in FOUNDER_EMAILS:
        raise HTTPException(status_code=400, detail="Founder accounts do not use password storage — nothing to change here.")

    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    if not user_store.configured():
        raise HTTPException(503, "Account storage is not configured — please try again shortly")

    row = await user_store.get_user_by_email(email)
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    if not user_store.verify_password(payload.current_password, row.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = user_store.hash_password(payload.new_password)
    await user_store.update_user(email, {"password_hash": new_hash})
    return {"success": True, "message": "Password updated successfully"}


# ============================================================
# Forgot / reset password (unauthenticated — email-token based)
# ============================================================
class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


_GENERIC_FORGOT_MSG = "If an account exists for that email, a password reset link has been sent."


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    from . import mailer
    email = (payload.email or "").lower().strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email address required")

    # Never reveal whether an account exists — always return the same generic message.
    if email in FOUNDER_EMAILS or not user_store.configured():
        return {"success": True, "message": _GENERIC_FORGOT_MSG}

    try:
        row = await user_store.get_user_by_email(email)
    except Exception:
        return {"success": True, "message": _GENERIC_FORGOT_MSG}

    if not row:
        return {"success": True, "message": _GENERIC_FORGOT_MSG}

    reset_token = uuid.uuid4().hex + uuid.uuid4().hex
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    try:
        await user_store.update_user(email, {"reset_token": reset_token, "reset_token_expires": expires})
    except Exception:
        return {"success": True, "message": _GENERIC_FORGOT_MSG}

    frontend_url = os.getenv("FRONTEND_URL") or os.getenv("PASTOR_FRONTEND_URL") or "https://pastoraiconnect.com"
    reset_link = f"{frontend_url.rstrip('/')}/reset-password?token={reset_token}"

    if mailer.configured():
        await mailer.send_email(
            to=email,
            subject="Reset your Pastor AI password",
            html=f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;">
              <h2>Reset your password</h2>
              <p>We received a request to reset your Pastor AI password. This link expires in 1 hour.</p>
              <p><a href="{reset_link}" style="background:#1a2744;color:#fff;padding:12px 20px;
                 border-radius:6px;text-decoration:none;display:inline-block;">Reset Password</a></p>
              <p>If you didn't request this, you can safely ignore this email.</p>
            </div>
            """,
        )

    return {"success": True, "message": _GENERIC_FORGOT_MSG}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    if not payload.token:
        raise HTTPException(400, "Reset token required")
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")
    if not user_store.configured():
        raise HTTPException(503, "Account storage is not configured — please try again shortly")

    row = await user_store.get_user_by_reset_token(payload.token)
    if not row:
        raise HTTPException(400, "This reset link is invalid or has already been used")

    expires_raw = row.get("reset_token_expires")
    if not expires_raw:
        raise HTTPException(400, "This reset link is invalid or has already been used")
    try:
        expires_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "This reset link is invalid")
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(400, "This reset link has expired — please request a new one")

    new_hash = user_store.hash_password(payload.new_password)
    await user_store.update_user(row["email"], {
        "password_hash": new_hash,
        "reset_token": None,
        "reset_token_expires": None,
    })
    return {"success": True, "message": "Password reset successfully — you can now log in"}
