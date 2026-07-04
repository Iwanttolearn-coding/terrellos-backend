"""
routers/user_store.py — Persistent user storage (Supabase-backed)
Replaces the old in-memory _REGISTERED_USERS / _PROFILE_STORE dicts.
Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib only, no extra deps).
"""
import os, hashlib, hmac, secrets, httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
TABLE = "app_users"

PBKDF2_ITERATIONS = 200_000


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _now():
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"{salt}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, digest_hex = stored_hash.split(":", 1)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except Exception:
        return False


def configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if not configured():
        return None
    email = email.lower().strip()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"email": f"eq.{email}", "limit": "1"},
        )
    if r.status_code != 200:
        raise RuntimeError(f"user lookup failed: {r.text[:200]}")
    rows = r.json() or []
    return rows[0] if rows else None


async def create_user(email: str, password: str, full_name: str = "") -> Dict[str, Any]:
    if not configured():
        raise RuntimeError("Supabase not configured — cannot persist users")
    email = email.lower().strip()
    record = {
        "email": email,
        "password_hash": hash_password(password),
        "full_name": full_name or email.split("@")[0],
        "role": "user",
        "plan": "free",
        "created_at": _now(),
        "updated_at": _now(),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            json=record,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"user create failed: {r.text[:300]}")
    rows = r.json()
    return rows[0] if isinstance(rows, list) and rows else record


async def update_user(email: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not configured():
        return None
    email = email.lower().strip()
    updates = {**updates, "updated_at": _now()}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"email": f"eq.{email}"},
            json=updates,
        )
    if r.status_code not in (200, 204):
        raise RuntimeError(f"user update failed: {r.text[:300]}")
    rows = r.json() if r.text else []
    return rows[0] if isinstance(rows, list) and rows else None


def public_user(row: Dict[str, Any]) -> Dict[str, Any]:
    """Strip password_hash and internal fields before returning to any client."""
    if not row:
        return {}
    return {k: v for k, v in row.items() if k not in ("password_hash",)}
