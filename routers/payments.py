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
PAYPAL_ENV          = os.getenv("PAYPAL_ENV", "live")

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


# ── NEW: Live PayPal checkout for all plans ───────────────────────────────────

class CheckoutRequest(BaseModel):
    planName: Optional[str] = "church"
    price: Optional[str] = "29.00"
    billingCycle: Optional[str] = "monthly"
    app_id: Optional[str] = ""

class CaptureRequest(BaseModel):
    token: Optional[str] = None        # PayPal's ?token= query param (order ID)
    orderId: Optional[str] = None      # alias
    order_id: Optional[str] = None     # alias
    planName: Optional[str] = "church"
    billingCycle: Optional[str] = "monthly"
    userEmail: Optional[str] = None
    app_id: Optional[str] = ""


@router.post("/checkout")
async def create_checkout(req: CheckoutRequest):
    """Create a live PayPal order for Church/Premium plans."""
    # Use live credentials — PAYPAL_ENV must be 'live' on Fly.io
    client_id = PAYPAL_CLIENT_ID
    secret     = PAYPAL_SECRET
    if not client_id or not secret:
        raise HTTPException(503, "PayPal not configured. Contact support.")

    price_str = str(req.price or "29.00").replace("$", "").strip()
    try:
        amount = f"{float(price_str):.2f}"
    except ValueError:
        amount = "29.00"

    plan_slug   = (req.planName or "church").lower().replace(" ", "-")
    cycle       = req.billingCycle or "monthly"
    description = f"Pastor AI {req.planName or 'Church'} Plan — {cycle.capitalize()}"
    return_url  = f"{PASTOR_FRONTEND_URL}/billing/success?plan={plan_slug}&cycle={cycle}"
    cancel_url  = f"{PASTOR_FRONTEND_URL}/billing/cancel"

    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{_base()}/v2/checkout/orders",
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{"amount": {"currency_code": "USD", "value": amount}, "description": description}],
                    "application_context": {
                        "brand_name": "Pastor AI Connect",
                        "landing_page": "BILLING",
                        "user_action": "PAY_NOW",
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                    },
                },
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"PayPal order error {r.status_code}: {r.text[:200]}")
        order = r.json()
        approve_url = next((l["href"] for l in order.get("links", []) if l.get("rel") == "approve"), None)
        logger.info("checkout order=%s plan=%s amount=%s", order.get("id"), plan_slug, amount)
        return {"success": True, "redirectUrl": approve_url, "checkout_url": approve_url, "orderId": order.get("id")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("checkout error: %s", e)
        raise HTTPException(502, f"Checkout failed: {str(e)}")


@router.post("/capture")
async def capture_payment(req: CaptureRequest):
    """Capture a PayPal order after user approves and update subscription."""
    order_id = req.token or req.orderId or req.order_id
    if not order_id:
        raise HTTPException(400, "orderId / token is required.")

    client_id = PAYPAL_CLIENT_ID
    secret     = PAYPAL_SECRET
    if not client_id or not secret:
        raise HTTPException(503, "PayPal not configured.")

    plan_map = {"church": "church", "premium": "premium", "trial": "trial", "free": "free"}
    plan_key = plan_map.get((req.planName or "church").lower(), "church")
    cycle    = req.billingCycle or "monthly"

    try:
        pp_token = await _get_token()
        async with httpx.AsyncClient(timeout=20) as c:
            # Check current status first
            check = await c.get(
                f"{_base()}/v2/checkout/orders/{order_id}",
                headers={"Authorization": f"Bearer {pp_token}"},
            )
            check_data = check.json()
            logger.info("capture check order=%s status=%s", order_id, check_data.get("status"))

            if check_data.get("status") == "COMPLETED":
                return {"success": True, "already_captured": True, "plan": plan_key,
                        "message": "Payment already confirmed. Welcome to Pastor AI!"}

            if check_data.get("status") != "APPROVED":
                raise HTTPException(402, f"Cannot capture — order status is {check_data.get('status')}")

            # Capture
            cap_r = await c.post(
                f"{_base()}/v2/checkout/orders/{order_id}/capture",
                json={},
                headers={"Authorization": f"Bearer {pp_token}", "Content-Type": "application/json"},
            )
        cap = cap_r.json()
        if cap.get("status") != "COMPLETED":
            logger.error("capture failed: %s", cap)
            raise HTTPException(402, f"Payment capture failed: {cap.get('status')}")

        capture_id  = cap.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [{}])[0].get("id")
        amount_paid = cap.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [{}])[0].get("amount", {}).get("value")
        payer_email = cap.get("payer", {}).get("email_address") or req.userEmail

        logger.info("capture SUCCESS order=%s captureId=%s amount=%s payer=%s", order_id, capture_id, amount_paid, payer_email)
        return {
            "success": True,
            "plan": plan_key,
            "billing_cycle": cycle,
            "amount_paid": amount_paid,
            "capture_id": capture_id,
            "order_id": order_id,
            "payer_email": payer_email,
            "message": f"Payment complete! Welcome to Pastor AI {plan_key.capitalize()}!",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("capture error: %s", e)
        raise HTTPException(502, f"Capture failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════
# TerrellOS /v1/checkout/* — AI credit plan checkout via PayPal Live
# Called by: Pricing.jsx → createCheckoutSession(planId, email)
# ═══════════════════════════════════════════════════════════════════

TERRELLOS_FRONTEND_URL = os.getenv("TERRELLOS_FRONTEND_URL", "https://app.tm-dezigns.com")

TERRELLOS_PLANS = {
    "starter":    {"price": "29.00",  "name": "TerrellOS Starter — Monthly",      "credits": 1000},
    "pro":        {"price": "99.00",  "name": "TerrellOS Professional — Monthly", "credits": 5000},
    "enterprise": {"price": "249.00", "name": "TerrellOS Enterprise — Monthly",   "credits": 20000},
}

checkout_router = APIRouter(prefix="/v1/checkout", tags=["TerrellOS Checkout"])


class TerrellOSCheckoutRequest(BaseModel):
    plan: str
    email: Optional[str] = ""
    success_url: Optional[str] = None
    cancel_url:  Optional[str] = None


class TerrellOSCaptureRequest(BaseModel):
    order_id: Optional[str] = None
    token:    Optional[str] = None
    plan:     Optional[str] = None
    email:    Optional[str] = None


@checkout_router.post("/create")
async def terrellos_checkout_create(req: TerrellOSCheckoutRequest):
    """Create a live PayPal order for TerrellOS credit plans. Called by Pricing.jsx."""
    plan_info = TERRELLOS_PLANS.get(req.plan)
    if not plan_info:
        raise HTTPException(400, f"Unknown plan '{req.plan}'. Valid: {list(TERRELLOS_PLANS.keys())}")

    cid  = PAYPAL_CLIENT_ID
    csec = PAYPAL_SECRET
    if not cid or not csec:
        raise HTTPException(503, "Payment processor not configured.")

    origin      = TERRELLOS_FRONTEND_URL
    return_url  = req.success_url or f"{origin}/thank-you?plan={req.plan}"
    cancel_url  = req.cancel_url  or f"{origin}/pricing"

    try:
        token = await _get_token()
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{_base()}/v2/checkout/orders",
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "amount": {"currency_code": "USD", "value": plan_info["price"]},
                        "description": plan_info["name"],
                    }],
                    "application_context": {
                        "brand_name": "TerrellOS",
                        "landing_page": "BILLING",
                        "user_action": "PAY_NOW",
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                    },
                },
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"PayPal error {r.status_code}: {r.text[:200]}")
        order = r.json()
        checkout_url = next((l["href"] for l in order.get("links", []) if l.get("rel") == "approve"), None)
        logger.info("TerrellOS checkout order=%s plan=%s amount=%s email=%s",
                    order.get("id"), req.plan, plan_info["price"], req.email)
        return {
            "success":     True,
            "checkoutUrl": checkout_url,
            "url":         checkout_url,
            "orderId":     order.get("id"),
            "plan":        req.plan,
            "amount":      plan_info["price"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("terrellos_checkout_create error: %s", e)
        raise HTTPException(502, f"Checkout failed: {e}")


@checkout_router.post("/capture")
async def terrellos_checkout_capture(req: TerrellOSCaptureRequest):
    """Capture a TerrellOS PayPal order after buyer approval."""
    order_id = req.order_id or req.token
    if not order_id:
        raise HTTPException(400, "order_id required")
    try:
        pp_token = await _get_token()
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"{_base()}/v2/checkout/orders/{order_id}/capture",
                json={},
                headers={"Authorization": f"Bearer {pp_token}", "Content-Type": "application/json"},
            )
        data = r.json()
        if data.get("status") != "COMPLETED":
            raise HTTPException(402, f"Capture failed: {data.get('status')}")
        capture_id  = data.get("purchase_units",[{}])[0].get("payments",{}).get("captures",[{}])[0].get("id")
        amount_paid = data.get("purchase_units",[{}])[0].get("payments",{}).get("captures",[{}])[0].get("amount",{}).get("value")
        logger.info("TerrellOS captured order=%s capture=%s amount=%s", order_id, capture_id, amount_paid)
        return {
            "success":    True,
            "plan":       req.plan,
            "capture_id": capture_id,
            "amount_paid":amount_paid,
            "order_id":   order_id,
            "message":    f"Payment complete! Welcome to TerrellOS {req.plan}!",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("terrellos_capture error: %s", e)
        raise HTTPException(502, f"Capture failed: {e}")
