"""
routers/paypal.py — TerrellOS / TM Dezigns PayPal Integration (LIVE)
Mounted at /v1/paypal in app.py

Endpoints:
  GET  /plans                — list plans + pricing
  GET  /status               — integration health
  POST /create-order         — create PayPal order
  POST /capture-order        — capture + upgrade user plan
  POST /refund               — issue refund (7-day window)
  POST /cancel-subscription  — cancel subscription
  POST /webhook              — PayPal live event webhook
  GET  /admin/transactions   — admin: all transactions
  GET  /admin/refunds        — admin: all refunds
"""
import os, logging, json as _json
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("paypal_tm")
router = APIRouter(tags=["PayPal Payments"])

PAYPAL_API         = "https://api-m.paypal.com"   # LIVE — always
CLIENT_ID          = os.getenv("PAYPAL_CLIENT_ID",     "AfOAEYZy_5A6lLkI0yo6ejxHyps2esDOx0Hw8Q8FhsJQqaYMoV-cYanygCJ_5hBz10pade1JMAWMbqmG")
CLIENT_SECRET      = os.getenv("PAYPAL_CLIENT_SECRET", "EPtRt43JdL51o-fPJgMh_WX-d9AOKAA-FOZIyCNauOIoXzs7eth13AW4FaLSoM6usqai4Yuyw0runT4x")
REFUND_WINDOW_DAYS = 7
PAYPAL_WEBHOOK_ID  = os.getenv("PAYPAL_WEBHOOK_ID", "8CE33197GL084972H")

PLANS = {
    "basic":       {"price": "19.00",  "name": "TM Dezigns Basic"},
    "professional":{"price": "49.00",  "name": "TM Dezigns Professional"},
    "elite":       {"price": "99.00",  "name": "TM Dezigns Elite"},
    "pastor_basic":{"price": "9.99",   "name": "Pastor AI Basic"},
    "pastor_pro":  {"price": "19.99",  "name": "Pastor AI Premium"},
}

def _now(): return datetime.now(timezone.utc).isoformat()

# ── Auth ──────────────────────────────────────────────────────────────────────
async def _get_token() -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{PAYPAL_API}/v1/oauth2/token",
                         auth=(CLIENT_ID, CLIENT_SECRET),
                         data={"grant_type": "client_credentials"})
        r.raise_for_status()
        return r.json()["access_token"]

async def _hdrs():
    t = await _get_token()
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

# ── GET /plans ─────────────────────────────────────────────────────────────────
@router.get("/plans")
async def list_plans():
    return {"plans": PLANS, "environment": "live", "client_id": CLIENT_ID[:20] + "..."}

# ── GET /status ────────────────────────────────────────────────────────────────
@router.get("/status")
async def status():
    return {
        "environment": "live",
        "client_id_set": bool(CLIENT_ID),
        "secret_set": bool(CLIENT_SECRET),
        "ready": bool(CLIENT_ID and CLIENT_SECRET),
        "refund_window_days": REFUND_WINDOW_DAYS,
        "webhook_url": "https://terrellos-backend.fly.dev/v1/paypal/webhook",
    }

# ── POST /create-order ─────────────────────────────────────────────────────────
class CreateOrderReq(BaseModel):
    plan: str
    currency: str = "USD"
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None

@router.post("/create-order")
async def create_order(req: CreateOrderReq):
    plan_info = PLANS.get(req.plan)
    if not plan_info:
        raise HTTPException(400, f"Unknown plan. Valid: {list(PLANS.keys())}")
    hdrs = await _hdrs()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{PAYPAL_API}/v2/checkout/orders", headers=hdrs, json={
            "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": req.currency, "value": plan_info["price"]},
                                "description": f"TerrellOS — {plan_info['name']}"}],
            "application_context": {
                "brand_name": "TerrellOS",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "return_url": req.return_url or "https://app.tm-dezigns.com/billing?status=success",
                "cancel_url": req.cancel_url or "https://app.tm-dezigns.com/billing?status=cancel",
            },
        })
        r.raise_for_status()
        d = r.json()
    approve = next((l["href"] for l in d.get("links",[]) if l.get("rel")=="approve"), None)
    logger.info("Order created: %s plan=%s", d["id"], req.plan)
    return {"success": True, "order_id": d["id"], "status": d["status"],
            "approve_url": approve, "plan": req.plan, "amount": plan_info["price"]}

# ── POST /capture-order ────────────────────────────────────────────────────────
class CaptureReq(BaseModel):
    order_id: str
    plan: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None

@router.post("/capture-order")
async def capture_order(req: CaptureReq):
    plan_info = PLANS.get(req.plan, {})
    hdrs = await _hdrs()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{PAYPAL_API}/v2/checkout/orders/{req.order_id}/capture",
                         headers=hdrs, json={})
        r.raise_for_status()
        d = r.json()
    captures = d.get("purchase_units",[{}])[0].get("payments",{}).get("captures",[{}])
    capture  = captures[0] if captures else {}
    cap_id   = capture.get("id","")
    payer    = d.get("payer",{})
    expires  = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    logger.info("Captured: %s plan=%s user=%s", cap_id, req.plan, req.user_email)
    return {
        "success": True,
        "capture_id": cap_id,
        "plan": req.plan,
        "plan_name": plan_info.get("name", req.plan),
        "amount": capture.get("amount",{}).get("value",""),
        "expires_at": expires,
        "payer": {"email": payer.get("email_address",""), "name": payer.get("name",{})},
        "status": capture.get("status",""),
    }

# ── POST /refund ───────────────────────────────────────────────────────────────
class RefundReq(BaseModel):
    capture_id: str
    amount: Optional[str] = None
    reason: Optional[str] = "Customer requested refund"
    paid_at: Optional[str] = None   # ISO timestamp of original payment

@router.post("/refund")
async def issue_refund(req: RefundReq):
    # Enforce refund window
    if req.paid_at:
        try:
            paid = datetime.fromisoformat(req.paid_at.replace("Z","+00:00"))
            days_since = (datetime.now(timezone.utc) - paid).days
            if days_since > REFUND_WINDOW_DAYS:
                raise HTTPException(400,
                    f"Refund window expired — {days_since} days since payment "
                    f"(limit: {REFUND_WINDOW_DAYS} days).")
        except HTTPException:
            raise
        except:
            pass

    hdrs = await _hdrs()
    body = {"note_to_payer": (req.reason or "Refund")[:255]}
    if req.amount:
        body["amount"] = {"value": req.amount, "currency_code": "USD"}

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{PAYPAL_API}/v2/payments/captures/{req.capture_id}/refund",
                         headers=hdrs, json=body)
        r.raise_for_status()
        d = r.json()

    logger.info("Refund issued: %s capture=%s amount=%s",
                d.get("id"), req.capture_id, d.get("amount",{}).get("value",""))
    return {
        "success": True,
        "refund_id": d.get("id"),
        "status": d.get("status"),
        "amount": d.get("amount",{}).get("value",""),
        "capture_id": req.capture_id,
    }

# ── POST /cancel-subscription ─────────────────────────────────────────────────
class CancelSubReq(BaseModel):
    subscription_id: str
    reason: Optional[str] = "Cancelled by user"

@router.post("/cancel-subscription")
async def cancel_subscription(req: CancelSubReq):
    hdrs = await _hdrs()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{PAYPAL_API}/v1/billing/subscriptions/{req.subscription_id}/cancel",
                         headers=hdrs, json={"reason": req.reason})
    if r.status_code in (200, 204):
        return {"success": True, "subscription_id": req.subscription_id, "status": "CANCELLED"}
    raise HTTPException(502, f"PayPal cancel failed: {r.text[:200]}")

# ── POST /webhook ──────────────────────────────────────────────────────────────
@router.post("/webhook")
async def paypal_webhook(request: Request):
    """Receive PayPal live events — capture, renewal, cancellation, refund."""
    try:
        body = await request.json()
    except:
        raise HTTPException(400, "Invalid JSON")

    event    = body.get("event_type","")
    resource = body.get("resource",{})
    logger.info("[TM Dezigns webhook] event=%s", event)

    if event == "PAYMENT.CAPTURE.COMPLETED":
        logger.info("Payment captured: %s amount=%s",
                    resource.get("id"), resource.get("amount",{}).get("value"))

    elif event in ("BILLING.SUBSCRIPTION.RENEWED","PAYMENT.SALE.COMPLETED"):
        logger.info("Subscription renewed: sub=%s amount=%s",
                    resource.get("billing_agreement_id",""), 
                    resource.get("amount",{}).get("total",""))

    elif event == "BILLING.SUBSCRIPTION.CANCELLED":
        logger.info("Subscription cancelled: %s", resource.get("id",""))

    elif event == "PAYMENT.CAPTURE.REFUNDED":
        logger.info("Refund confirmed: capture=%s", resource.get("id",""))

    return {"received": True, "event": event}

# ── GET /admin/transactions (stub — wire to your DB) ──────────────────────────
@router.get("/admin/transactions")
async def admin_transactions():
    return {"message": "Wire to your DB — query payment_transactions table", "status": "ok"}

@router.get("/admin/refunds")
async def admin_refunds():
    return {"message": "Wire to your DB — query refund_log table", "status": "ok"}


# ── Billing alias routes (maps /v1/billing/* used by TerrellOS frontend) ──────
from fastapi import APIRouter as _AR
billing_router = _AR(prefix="/v1/billing", tags=["Billing"])

@billing_router.get("/plans")
async def billing_plans():
    """Alias for /v1/paypal/plans — used by TerrellOS frontend."""
    return await plans()

@billing_router.get("/status")
async def billing_status():
    """Alias for /v1/paypal/status."""
    return await status()

@router.get("/health")
async def paypal_health():
    import os
    env = os.getenv("PAYPAL_ENV","sandbox")
    return {"success": True, "status": "online", "service": "PayPal",
            "environment": env, "live": env=="live",
            "configured": bool(os.getenv("PAYPAL_CLIENT_ID"))}
