"""
/v1/payments/* — Pastor AI Connect payment routes
Trial checkout, subscription management
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import os, logging

router = APIRouter(prefix="/v1/payments", tags=["Payments"])
logger = logging.getLogger("payments")

PASTOR_FRONTEND_URL = os.getenv("PASTOR_FRONTEND_URL", "https://pastoraiconnect.com")

PASTOR_PLANS = {
    "trial_7day": {"price": "1.00", "name": "Pastor AI — 7-Day Trial", "days": 7},
    "monthly":    {"price": "9.99", "name": "Pastor AI — Monthly",      "days": 30},
    "annual":     {"price": "79.99","name": "Pastor AI — Annual",        "days": 365},
}


class TrialCheckoutRequest(BaseModel):
    email: Optional[str] = ""
    plan: Optional[str] = "trial_7day"
    return_url: Optional[str] = ""
    cancel_url: Optional[str] = ""
    app_id: Optional[str] = ""


@router.post("/trial-checkout")
async def trial_checkout(req: TrialCheckoutRequest, request: Request):
    """Create a PayPal checkout session for Pastor AI trial/subscription."""
    plan_id = req.plan or "trial_7day"
    plan = PASTOR_PLANS.get(plan_id)
    if not plan:
        plan = PASTOR_PLANS["trial_7day"]

    try:
        # Route through the existing PayPal infrastructure
        import httpx
        PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID","")
        PAYPAL_SECRET    = os.getenv("PAYPAL_SECRET","")
        PAYPAL_MODE      = os.getenv("PAYPAL_MODE","sandbox")
        base_url = "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"

        if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET:
            # Graceful fallback — return a checkout_url pointing to upgrade page
            logger.warning("PayPal credentials not configured for payments router")
            return {
                "success": False,
                "checkout_url": None,
                "error": "Payment processor not configured. Please contact support.",
                "plan": plan,
            }

        async with httpx.AsyncClient(timeout=15) as c:
            # Get access token
            r = await c.post(
                f"{base_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            )
            if r.status_code != 200:
                raise RuntimeError(f"PayPal auth failed: {r.status_code}")
            token = r.json().get("access_token","")

            # Create order
            return_url = req.return_url or f"{PASTOR_FRONTEND_URL}/upgrade?status=success&plan={plan_id}"
            cancel_url = req.cancel_url or f"{PASTOR_FRONTEND_URL}/upgrade?status=cancelled"

            order_payload = {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {"currency_code": "USD", "value": plan["price"]},
                    "description": plan["name"],
                }],
                "application_context": {
                    "brand_name": "Pastor AI Connect",
                    "landing_page": "BILLING",
                    "user_action": "PAY_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            }
            r2 = await c.post(
                f"{base_url}/v2/checkout/orders",
                json=order_payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            if r2.status_code not in (200, 201):
                raise RuntimeError(f"PayPal order failed: {r2.status_code} {r2.text[:200]}")

            order = r2.json()
            checkout_url = next(
                (link["href"] for link in order.get("links", []) if link.get("rel") == "approve"),
                None
            )
            return {
                "success": True,
                "checkout_url": checkout_url,
                "order_id": order.get("id"),
                "plan": plan,
            }

    except Exception as e:
        logger.error("trial_checkout error: %s", e)
        raise HTTPException(502, f"Checkout creation failed: {str(e)}")


@router.get("/plans")
async def list_plans():
    return {"success": True, "plans": PASTOR_PLANS}
