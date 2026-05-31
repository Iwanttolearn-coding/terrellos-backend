"""
/v1/payments/* — Pastor AI Connect payment routes
Trial checkout, subscription management
Wraps /v1/paypal/* to provide Pastor AI-branded payment routes.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import os, logging, httpx

router = APIRouter(prefix="/v1/payments", tags=["Payments"])
logger = logging.getLogger("payments")

PASTOR_FRONTEND_URL = os.getenv("PASTOR_FRONTEND_URL", "https://pastoraiconnect.com")
PAYPAL_CLIENT_ID    = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET       = os.getenv("PAYPAL_CLIENT_SECRET", "")  # matches paypal.py convention
PAYPAL_ENV          = os.getenv("PAYPAL_ENV", "sandbox")

PASTOR_PLANS = {
    "trial_7day": {"price": "1.00",  "name": "Pastor AI — 7-Day Trial",  "days": 7},
    "monthly":    {"price": "9.99",  "name": "Pastor AI — Monthly",       "days": 30},
    "annual":     {"price": "79.99", "name": "Pastor AI — Annual",        "days": 365},
}


def _base():
    return "https://api-m.paypal.com" if PAYPAL_ENV == "live" else "https://api-m.sandbox.paypal.com"


async def _get_token() -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{_base()}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        )
        if r.status_code != 200:
            raise RuntimeError(f"PayPal auth failed: {r.status_code} {r.text[:100]}")
        return r.json().get("access_token", "")


class TrialCheckoutRequest(BaseModel):
    email: Optional[str] = ""
    plan: Optional[str] = "trial_7day"
    return_url: Optional[str] = ""
    cancel_url: Optional[str] = ""
    app_id: Optional[str] = ""


@router.post("/trial-checkout")
async def trial_checkout(req: TrialCheckoutRequest):
    """Create a PayPal checkout session for Pastor AI trial/subscription."""
    plan_id = req.plan or "trial_7day"
    plan = PASTOR_PLANS.get(plan_id, PASTOR_PLANS["trial_7day"])

    if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET:
        raise HTTPException(503, "Payment processor not configured. Contact support@pastoraiconnect.com")

    try:
        token = await _get_token()
        return_url = req.return_url or f"{PASTOR_FRONTEND_URL}/upgrade?status=success&plan={plan_id}"
        cancel_url  = req.cancel_url  or f"{PASTOR_FRONTEND_URL}/upgrade?status=cancelled"

        async with httpx.AsyncClient(timeout=20) as c:
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
            r = await c.post(
                f"{_base()}/v2/checkout/orders",
                json=order_payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(f"PayPal order error {r.status_code}: {r.text[:200]}")

            order = r.json()
            checkout_url = next(
                (link["href"] for link in order.get("links", []) if link.get("rel") == "approve"),
                None
            )
            return {
                "success": True,
                "checkout_url": checkout_url,
                "approval_url": checkout_url,  # alias for frontend compatibility
                "order_id": order.get("id"),
                "plan": plan,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("trial_checkout error: %s", e)
        raise HTTPException(502, f"Checkout creation failed: {str(e)}")


@router.get("/plans")
async def list_plans():
    return {"success": True, "plans": PASTOR_PLANS}
