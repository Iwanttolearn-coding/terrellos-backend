"""
routers/subscriptions.py — Universal Subscription Management
Handles subscription status checks for all apps.
"""
import os, httpx
from fastapi import APIRouter, HTTPException
from typing import Optional

router = APIRouter(prefix="/v1/subscriptions", tags=["Subscriptions"])

SUPABASE_URL = os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY","")
PAYPAL_CLIENT_ID     = os.getenv("PAYPAL_CLIENT_ID","")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET","")
PAYPAL_ENV           = os.getenv("PAYPAL_ENV","sandbox")

def _pp_base():
    return "https://api-m.paypal.com" if PAYPAL_ENV == "live" else "https://api-m.sandbox.paypal.com"

async def _pp_token():
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{_pp_base()}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type":"client_credentials"})
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="PayPal auth failed")
    return r.json()["access_token"]

@router.get("/health")
async def subscriptions_health():
    return {
        "success": True, "status": "online", "service": "Subscriptions",
        "paypal_env": PAYPAL_ENV,
        "paypal_live": PAYPAL_ENV == "live",
        "supabase": bool(SUPABASE_URL and SUPABASE_KEY),
        "apps": ["pastor-ai-connect","kindred-love-birds","heavenly-eternal-echoes",
                 "pro-se-ai","terrellos","all-around-customs"]
    }

@router.get("/status")
async def subscription_status(user_email: str, app_id: Optional[str] = None):
    if not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    params = {"user_email": f"eq.{user_email.lower().strip()}", "order": "created_at.desc", "limit": "1"}
    if app_id:
        params["app_id"] = f"eq.{app_id}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/subscriptions", headers=headers, params=params)
    if r.status_code != 200:
        return {"success": True, "plan": "free", "status": "inactive", "user_email": user_email}
    records = r.json()
    if not records:
        return {"success": True, "plan": "free", "status": "inactive", "user_email": user_email}
    sub = records[0]
    return {"success": True, "plan": sub.get("plan","free"),
            "status": sub.get("status","inactive"), "user_email": user_email}

@router.get("/plans")
async def list_plans(app_id: Optional[str] = "all"):
    plans = {
        "pastor-ai-connect":        ["free","pro_monthly","pro_annual","church"],
        "kindred-love-birds":       ["free","couples","premium"],
        "heavenly-eternal-echoes":  ["free","legacy","eternal"],
        "pro-se-ai":                ["free","basic","attorney","law_firm"],
        "terrellos":                ["free","creator","professional"],
        "all-around-customs":       ["free","starter","pro_tattoo","pro_unlimited","business"],
    }
    if app_id == "all":
        return {"success": True, "plans": plans}
    return {"success": True, "app_id": app_id, "plans": plans.get(app_id, ["free"])}
