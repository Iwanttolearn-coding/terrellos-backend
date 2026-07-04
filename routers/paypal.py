"""
routers/paypal.py — Pastor AI Connect PayPal Integration (LIVE)
Mounted at /v1/paypal in app.py

PayPal handles the money. Supabase (user_subscriptions / payment_history) stores access.
The frontend never decides premium access — only the backend, via has_active_access().

Plans:
  free      — no PayPal, default state
  starter   — $19/mo  subscription (PayPal Billing Plan)
  church    — $49/mo  subscription (PayPal Billing Plan)
  pro       — $99/mo  subscription (PayPal Billing Plan)
  lifetime  — one-time checkout (PayPal Orders API)
"""
import os, logging, hashlib, hmac
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("paypal")
router = APIRouter(tags=["PayPal Payments"])

PAYPAL_API      = "https://api-m.paypal.com"   # LIVE
CLIENT_ID       = os.getenv("PAYPAL_CLIENT_ID", "")
CLIENT_SECRET   = os.getenv("PAYPAL_CLIENT_SECRET", "")
WEBHOOK_ID      = os.getenv("PAYPAL_WEBHOOK_ID", "")
FRONTEND_URL    = os.getenv("PASTOR_FRONTEND_URL", "https://pastoraiconnect.com")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

# PayPal Product + Billing Plan IDs (created live in PayPal, 2026-07-04)
PAYPAL_PRODUCT_ID = "PROD-4DX47138BG699520H"

PLANS = {
    "free":     {"type": "none",         "price": "0.00",  "name": "Free"},
    "starter":  {"type": "subscription", "price": "19.00", "name": "Pastor AI Starter",  "paypal_plan_id": "P-879880335R305352MNJEU33Y"},
    "church":   {"type": "subscription", "price": "49.00", "name": "Pastor AI Church",   "paypal_plan_id": "P-78Y31372EL859561ENJEU33Y"},
    "pro":      {"type": "subscription", "price": "99.00", "name": "Pastor AI Pro",      "paypal_plan_id": "P-01J4176396054683LNJEU34A"},
    "lifetime": {"type": "one_time",     "price": "499.00","name": "Pastor AI Lifetime"},
}

def _now(): return datetime.now(timezone.utc).isoformat()

def _sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

# ── PayPal auth ────────────────────────────────────────────────────────────
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

async def verify_webhook_signature(request, raw_body: bytes) -> bool:
    """Verify an inbound PayPal webhook using PayPal's verify-webhook-signature API.
    Returns True only if PayPal itself confirms the signature is valid for WEBHOOK_ID."""
    if not WEBHOOK_ID:
        logger.error("[paypal webhook] PAYPAL_WEBHOOK_ID not configured — rejecting webhook")
        return False
    try:
        import json as _json
        event_body = _json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False

    required = ("paypal-auth-algo", "paypal-cert-url", "paypal-transmission-id",
                "paypal-transmission-sig", "paypal-transmission-time")
    headers_lower = {k.lower(): v for k, v in request.headers.items()}
    if not all(h in headers_lower for h in required):
        logger.error("[paypal webhook] missing required PayPal signature headers")
        return False

    verify_payload = {
        "auth_algo":         headers_lower["paypal-auth-algo"],
        "cert_url":          headers_lower["paypal-cert-url"],
        "transmission_id":   headers_lower["paypal-transmission-id"],
        "transmission_sig":  headers_lower["paypal-transmission-sig"],
        "transmission_time": headers_lower["paypal-transmission-time"],
        "webhook_id":        WEBHOOK_ID,
        "webhook_event":     event_body,
    }
    try:
        hdrs = await _hdrs()
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{PAYPAL_API}/v1/notifications/verify-webhook-signature",
                              headers=hdrs, json=verify_payload)
        if r.status_code != 200:
            logger.error("[paypal webhook] verify call failed %s: %s", r.status_code, r.text[:300])
            return False
        result = r.json().get("verification_status", "")
        return result == "SUCCESS"
    except Exception as e:
        logger.error("[paypal webhook] verify-webhook-signature error: %s", e)
        return False

# ── Supabase helpers ─────────────────────────────────────────────────────────
async def upsert_subscription(user_email: str, **fields) -> bool:
    """Upsert a row in user_subscriptions keyed by user_email (unique index)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    payload = {"user_email": user_email.lower().strip(), **fields}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/user_subscriptions",
            headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            params={"on_conflict": "user_email"},
            json=payload,
        )
    if r.status_code not in (200, 201):
        logger.warning("upsert_subscription failed %s: %s", r.status_code, r.text[:300])
        return False
    return True

async def record_payment(user_email: str, **fields) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    payload = {"user_email": user_email.lower().strip(), **fields}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/payment_history",
            headers=_sb_headers(),
            json=payload,
        )
    if r.status_code not in (200, 201):
        logger.warning("record_payment failed %s: %s", r.status_code, r.text[:300])
        return False
    return True

async def get_subscription(user_email: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/user_subscriptions",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"user_email": f"eq.{user_email.lower().strip()}", "limit": "1"},
        )
    if r.status_code != 200:
        return {}
    rows = r.json()
    return rows[0] if rows else {}

async def has_active_access(user_email: str) -> bool:
    """Central gate — call before generating any premium content (sermons, bible studies,
    bible games, courses, voice, spanish, live transcription)."""
    if not user_email:
        return False
    # Super admin always has access
    if user_email.lower().strip() in ("millsterrell5@gmail.com", "millzterrell5@gmail.com"):
        return True
    sub = await get_subscription(user_email)
    if not sub:
        return False
    if sub.get("plan_name") == "lifetime" and sub.get("status") == "active":
        return True
    if sub.get("status") != "active":
        return False
    period_end = sub.get("current_period_end")
    if period_end:
        try:
            end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
            if end < datetime.now(timezone.utc):
                return False
        except Exception:
            pass
    return True

# ── GET /plans ─────────────────────────────────────────────────────────────
@router.get("/plans")
async def list_plans():
    return {"success": True, "plans": PLANS, "environment": "live"}

# ── GET /status ────────────────────────────────────────────────────────────
@router.get("/status")
async def status(user_email: Optional[str] = None):
    base = {
        "environment": "live",
        "client_id_set": bool(CLIENT_ID),
        "secret_set": bool(CLIENT_SECRET),
        "ready": bool(CLIENT_ID and CLIENT_SECRET),
        "webhook_url": "https://terrellos-backend.fly.dev/v1/paypal/webhook",
    }
    if user_email:
        sub = await get_subscription(user_email)
        active = await has_active_access(user_email)
        base["subscription"] = sub or {"plan_name": "free", "status": "inactive"}
        base["has_access"] = active
    return base

# ── POST /create-subscription (Starter / Church / Pro) ────────────────────
class CreateSubReq(BaseModel):
    plan: str                       # starter | church | pro
    user_email: str
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None

@router.post("/create-subscription")
async def create_subscription(req: CreateSubReq):
    plan_info = PLANS.get(req.plan)
    if not plan_info or plan_info["type"] != "subscription":
        raise HTTPException(400, f"Unknown subscription plan. Valid: starter, church, pro")
    hdrs = await _hdrs()
    body = {
        "plan_id": plan_info["paypal_plan_id"],
        "subscriber": {"email_address": req.user_email},
        "application_context": {
            "brand_name": "Pastor AI Connect",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": req.return_url or f"{FRONTEND_URL}/billing/success?plan={req.plan}",
            "cancel_url": req.cancel_url or f"{FRONTEND_URL}/billing/cancel",
        },
    }
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{PAYPAL_API}/v1/billing/subscriptions", headers=hdrs, json=body)
        r.raise_for_status()
        d = r.json()
    approve = next((l["href"] for l in d.get("links", []) if l.get("rel") == "approve"), None)
    logger.info("Subscription created: %s plan=%s user=%s", d.get("id"), req.plan, req.user_email)
    # Pre-create a pending row so we can find the user when the webhook fires
    await upsert_subscription(
        req.user_email,
        paypal_subscription_id=d.get("id"),
        paypal_plan_id=plan_info["paypal_plan_id"],
        plan_name=req.plan,
        status="pending",
    )
    return {"success": True, "subscription_id": d.get("id"), "approve_url": approve, "plan": req.plan}

# ── POST /create-order + /capture-order (Lifetime one-time) ────────────────
class CreateOrderReq(BaseModel):
    plan: str = "lifetime"
    user_email: str
    currency: str = "USD"
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None

@router.post("/create-order")
async def create_order(req: CreateOrderReq):
    plan_info = PLANS.get(req.plan)
    if not plan_info or plan_info["type"] != "one_time":
        raise HTTPException(400, "Only 'lifetime' uses one-time checkout")
    hdrs = await _hdrs()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{PAYPAL_API}/v2/checkout/orders", headers=hdrs, json={
            "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": req.currency, "value": plan_info["price"]},
                                "description": f"Pastor AI Connect — {plan_info['name']}"}],
            "application_context": {
                "brand_name": "Pastor AI Connect",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "return_url": req.return_url or f"{FRONTEND_URL}/billing/success?plan=lifetime",
                "cancel_url": req.cancel_url or f"{FRONTEND_URL}/billing/cancel",
            },
        })
        r.raise_for_status()
        d = r.json()
    approve = next((l["href"] for l in d.get("links", []) if l.get("rel") == "approve"), None)
    logger.info("Order created: %s plan=lifetime user=%s", d["id"], req.user_email)
    return {"success": True, "order_id": d["id"], "approve_url": approve, "plan": "lifetime"}

class CaptureReq(BaseModel):
    order_id: str
    user_email: str

@router.post("/capture-order")
async def capture_order(req: CaptureReq):
    hdrs = await _hdrs()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{PAYPAL_API}/v2/checkout/orders/{req.order_id}/capture", headers=hdrs, json={})
        r.raise_for_status()
        d = r.json()
    captures = d.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [{}])
    capture = captures[0] if captures else {}
    cap_id = capture.get("id", "")
    amount = capture.get("amount", {}).get("value", "")
    status_ = capture.get("status", "")

    if status_ == "COMPLETED":
        await upsert_subscription(
            req.user_email,
            plan_name="lifetime",
            status="active",
            current_period_start=_now(),
            current_period_end=None,
        )
        await record_payment(
            req.user_email,
            paypal_order_id=req.order_id,
            paypal_capture_id=cap_id,
            amount_cents=int(float(amount) * 100) if amount else None,
            currency="USD",
            status=status_,
            description="Pastor AI Connect — Lifetime access",
        )
    logger.info("Captured: %s user=%s status=%s", cap_id, req.user_email, status_)
    return {"success": status_ == "COMPLETED", "capture_id": cap_id, "amount": amount, "status": status_}

# ── POST /cancel-subscription ───────────────────────────────────────────────
class CancelSubReq(BaseModel):
    subscription_id: str
    user_email: str
    reason: Optional[str] = "Cancelled by user"

@router.post("/cancel-subscription")
async def cancel_subscription(req: CancelSubReq):
    hdrs = await _hdrs()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{PAYPAL_API}/v1/billing/subscriptions/{req.subscription_id}/cancel",
                         headers=hdrs, json={"reason": req.reason})
    if r.status_code in (200, 204):
        await upsert_subscription(req.user_email, status="cancelled", cancel_at_period_end=True)
        return {"success": True, "subscription_id": req.subscription_id, "status": "CANCELLED"}
    raise HTTPException(502, f"PayPal cancel failed: {r.text[:200]}")

# ── POST /webhook ────────────────────────────────────────────────────────────
@router.post("/webhook")
async def paypal_webhook(request: Request):
    """Live PayPal webhook — updates user_subscriptions / payment_history in Supabase.
    Every event is verified against PayPal's verify-webhook-signature API before being
    trusted — unsigned or forged events are rejected with 400 and never processed."""
    raw_body = await request.body()
    try:
        import json as _json
        body = _json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event = body.get("event_type", "")

    verified = await verify_webhook_signature(request, raw_body)
    if not verified:
        logger.warning("[paypal webhook] REJECTED unverified/forged event=%s from %s",
                        event, request.client.host if request.client else "unknown")
        raise HTTPException(status_code=400, detail="Webhook signature verification failed")

    resource = body.get("resource", {})
    logger.info("[paypal webhook] verified event=%s", event)

    try:
        if event == "BILLING.SUBSCRIPTION.ACTIVATED":
            sub_id = resource.get("id")
            plan_id = resource.get("plan_id")
            payer_email = (resource.get("subscriber", {}) or {}).get("email_address", "")
            plan_name = next((k for k, v in PLANS.items() if v.get("paypal_plan_id") == plan_id), "unknown")
            start = resource.get("start_time") or _now()
            billing_info = resource.get("billing_info", {})
            next_bill = billing_info.get("next_billing_time")
            if payer_email:
                await upsert_subscription(
                    payer_email,
                    paypal_subscription_id=sub_id,
                    paypal_plan_id=plan_id,
                    plan_name=plan_name,
                    status="active",
                    current_period_start=start,
                    current_period_end=next_bill,
                    cancel_at_period_end=False,
                )

        elif event == "BILLING.SUBSCRIPTION.UPDATED":
            sub_id = resource.get("id")
            status_ = resource.get("status", "").lower()
            billing_info = resource.get("billing_info", {})
            next_bill = billing_info.get("next_billing_time")
            payer_email = (resource.get("subscriber", {}) or {}).get("email_address", "")
            if payer_email:
                await upsert_subscription(
                    payer_email,
                    paypal_subscription_id=sub_id,
                    status="active" if status_ == "active" else status_,
                    current_period_end=next_bill,
                )

        elif event == "BILLING.SUBSCRIPTION.CANCELLED":
            payer_email = (resource.get("subscriber", {}) or {}).get("email_address", "")
            if payer_email:
                await upsert_subscription(payer_email, status="cancelled", cancel_at_period_end=True)

        elif event in ("PAYMENT.SALE.COMPLETED", "CHECKOUT.ORDER.APPROVED"):
            payer_email = (resource.get("payer", {}) or {}).get("email_address", "") or \
                          (resource.get("subscriber", {}) or {}).get("email_address", "")
            amount = resource.get("amount", {})
            value = amount.get("total") or amount.get("value") or "0"
            if payer_email:
                await record_payment(
                    payer_email,
                    paypal_order_id=resource.get("id") if event == "CHECKOUT.ORDER.APPROVED" else None,
                    paypal_subscription_id=resource.get("billing_agreement_id", ""),
                    amount_cents=int(float(value) * 100) if value else None,
                    currency=amount.get("currency") or amount.get("currency_code") or "USD",
                    status="completed",
                    description=f"PayPal event: {event}",
                )

        elif event == "PAYMENT.CAPTURE.COMPLETED":
            amount = resource.get("amount", {})
            value = amount.get("value", "0")
            payer_email = (resource.get("payer", {}) or {}).get("email_address", "")
            if payer_email:
                await record_payment(
                    payer_email,
                    paypal_capture_id=resource.get("id"),
                    amount_cents=int(float(value) * 100) if value else None,
                    currency=amount.get("currency_code", "USD"),
                    status="completed",
                    description="PayPal capture completed (one-time / lifetime)",
                )
    except Exception as e:
        logger.error("webhook processing error: %s", e)

    return {"received": True, "event": event}

# ── GET /health ──────────────────────────────────────────────────────────────
@router.get("/health")
async def paypal_health():
    return {"success": True, "status": "online", "service": "PayPal",
            "environment": "live", "live": True,
            "configured": bool(CLIENT_ID and CLIENT_SECRET)}

# ── Billing alias routes (maps /v1/billing/* used by TerrellOS/Pastor AI frontend) ──
from fastapi import APIRouter as _AR
billing_router = _AR(prefix="/v1/billing", tags=["Billing"])

@billing_router.get("/plans")
async def billing_plans():
    return await list_plans()

@billing_router.get("/status")
async def billing_status(user_email: Optional[str] = None):
    return await status(user_email)
