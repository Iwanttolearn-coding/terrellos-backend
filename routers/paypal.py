"""
routers/paypal.py — TerrellOS / Heavenly Eternal Echo PayPal Checkout
Mounted at /v1/paypal in app.py
Uses the same PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET env vars.
"""
import logging
import httpx
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("paypal_hee")
router = APIRouter(tags=["PayPal Payments"])

SANDBOX_URL = "https://api-m.sandbox.paypal.com"
LIVE_URL    = "https://api-m.paypal.com"

PAYPAL_CLIENT_ID     = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_ENV           = os.getenv("PAYPAL_ENV", "sandbox").lower()
HEE_FRONTEND_URL     = os.getenv("HEE_FRONTEND_URL", "https://heavenlyeternalecho.com")

def _base(): return SANDBOX_URL if PAYPAL_ENV == "sandbox" else LIVE_URL
def _now():  return datetime.now(timezone.utc).isoformat()

# ── Plan catalog ──────────────────────────────────────────────────
HEE_PLANS = {
    "heritage":         {"price": "9.99",  "name": "Heritage — Monthly",
                         "features": ["AI Companion chat","10 voice recordings","Memory vault","Family access"]},
    "legacy":           {"price": "24.99", "name": "Legacy — Monthly",
                         "features": ["Unlimited AI chat","Unlimited recordings","Avatar Studio","Priority support"]},
    "eternal":          {"price": "199.00","name": "Eternal — Lifetime",
                         "features": ["Everything forever","White-glove onboarding","Dedicated AI model","Legacy video"]},
    "kingdom_pro":      {"price": "499.00","name": "Kingdom Pro Lifetime",
                         "features": ["Ministry license","Multi-family vaults","Custom avatar","API access"]},
    "sandbox_test":     {"price": "1.00",  "name": "Sandbox Test $1",
                         "features": ["Test only — no real charge"]},
}

# ── PayPal helpers ────────────────────────────────────────────────
async def _get_token() -> str:
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise RuntimeError("PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET not set in env")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{_base()}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
    if r.status_code != 200:
        raise RuntimeError(f"PayPal token error {r.status_code}: {r.text[:200]}")
    return r.json()["access_token"]

# ── Pydantic models ───────────────────────────────────────────────
class CreateOrderReq(BaseModel):
    plan: str
    amount: Optional[str] = None       # auto-resolved from HEE_PLANS if omitted
    currency: str = "USD"
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None

class CaptureOrderReq(BaseModel):
    order_id: str
    plan: str
    user_id: Optional[str] = None      # passed from frontend localStorage

# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/plans")
async def hee_plans():
    return {
        "plans": HEE_PLANS,
        "environment": PAYPAL_ENV,
        "client_id": PAYPAL_CLIENT_ID[:20] + "..." if PAYPAL_CLIENT_ID else "",
    }

@router.get("/status")
async def hee_paypal_status():
    return {
        "environment": PAYPAL_ENV,
        "client_id_set": bool(PAYPAL_CLIENT_ID),
        "secret_set": bool(PAYPAL_CLIENT_SECRET),
        "ready": bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET),
        "plans_available": list(HEE_PLANS.keys()),
    }

@router.post("/create-order")
async def hee_create_order(req: CreateOrderReq):
    plan_info = HEE_PLANS.get(req.plan)
    if not plan_info and not req.amount:
        raise HTTPException(400, f"Unknown plan '{req.plan}'. Valid: {list(HEE_PLANS.keys())}")
    amount = plan_info["price"] if plan_info else req.amount
    desc   = plan_info["name"] if plan_info else "Heavenly Eternal Echo Subscription"

    try:
        token   = await _get_token()
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {"currency_code": req.currency, "value": amount},
                "description": desc,
            }],
            "application_context": {
                "brand_name": "Heavenly Eternal Echo",
                "landing_page": "BILLING",
                "user_action": "PAY_NOW",
                "return_url": req.return_url or f"{HEE_FRONTEND_URL}/billing?status=success",
                "cancel_url": req.cancel_url or f"{HEE_FRONTEND_URL}/billing?status=cancelled",
            },
        }
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{_base()}/v2/checkout/orders",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"PayPal error {r.status_code}: {r.text[:300]}")
        data         = r.json()
        approval_url = next((l["href"] for l in data.get("links",[]) if l["rel"]=="approve"), None)
        logger.info("HEE order created: %s plan=%s amount=%s", data["id"], req.plan, amount)
        return {
            "success": True,
            "order_id": data["id"],
            "status": data["status"],
            "approval_url": approval_url,
            "plan": req.plan,
            "amount": amount,
        }
    except Exception as e:
        logger.error("create_order failed: %s", e)
        raise HTTPException(502, f"PayPal error: {e}")

@router.post("/capture-order")
async def hee_capture_order(req: CaptureOrderReq):
    """Capture PayPal order after buyer approval. Updates plan in memory if user_id provided."""
    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{_base()}/v2/checkout/orders/{req.order_id}/capture",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"PayPal capture error {r.status_code}: {r.text[:300]}")
        data    = r.json()
        unit    = data.get("purchase_units", [{}])[0]
        capture = unit.get("payments", {}).get("captures", [{}])[0]
        capture_id = capture.get("id","")
        plan_name  = HEE_PLANS.get(req.plan, {}).get("name", req.plan)

        logger.info("HEE captured: %s plan=%s user=%s", capture_id, req.plan, req.user_id)
        return {
            "success": True,
            "capture_id": capture_id,
            "plan_upgraded_to": req.plan,
            "plan_name": plan_name,
            "status": data.get("status"),
            "payer": data.get("payer", {}),
        }
    except Exception as e:
        logger.error("capture_order failed: %s", e)
        raise HTTPException(502, f"PayPal capture error: {e}")

@router.post("/webhook")
async def hee_webhook(request: Request):
    """PayPal webhook for HEE — safety net for missed captures."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    event_type = body.get("event_type","")
    logger.info("HEE PayPal webhook: %s", event_type)
    return {"received": True, "event_type": event_type}
