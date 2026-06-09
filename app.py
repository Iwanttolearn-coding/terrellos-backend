"""
TerrellOS Backend — v9.0.0-orchestration
Universal AI Operating System Core
Powers: TerrellOS, Pastor AI Connect, Heavenly Eternal Echoes,
        All Around Customs, Kindred Love Birds, ResidentSync AI
Architecture: One backend, isolated app identities via X-App-ID header
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from openai import OpenAI
import os, uuid, base64, httpx, json

# ── Route modules ─────────────────────────────────────────────────────────────
from routers.core    import router as core_router
from routers.memory  import router as memory_router
from routers.voice   import router as voice_router
from routers.pastor      import router as pastor_router
from routers.bible       import router as bible_router
from routers.word_study  import router as word_study_router
from routers.echo    import router as echo_router, companion_router
from routers.design  import router as design_router
from routers.founder import router as founder_router
from routers.admin   import router as admin_router
from routers.uploads import router as uploads_router
from routers.tattoo  import router as tattoo_router
from routers.gallery import router as gallery_router
from routers.auth    import router as auth_router
from routers.system import router as system_router
from routers.paypal          import router as paypal_router, billing_router
from routers.payments        import router as payments_router, checkout_router
from routers.voice_interview import router as voice_interview_router
from routers.db           import router as db_router
from routers.fn           import router as fn_router
from routers.bail          import router as bail_router

# ── App identity registry ──────────────────────────────────────────────────────
APP_REGISTRY = {
    "terrellos": {
        "name": "TerrellOS",
        "domain": "app.tm-dezigns.com",
        "description": "Universal AI Operating System",
        "theme": "purple",
        "modules": ["core","memory","voice","pastor","echo","design","founder","admin","uploads","tattoo","gallery"],
    },
    "pastor-ai-connect": {
        "name": "Pastor AI Connect",
        "domain": "pastoraiconnect.com",
        "description": "AI-Powered Ministry Platform",
        "theme": "gold",
        "modules": ["core","voice","pastor","uploads"],
    },
    "heavenly-eternal-echo": {
        "name": "Heavenly Eternal Echoes",
        "domain": "heavenlyeternalecho.com",
        "description": "AI Memory & Legacy Platform",
        "theme": "blue",
        "modules": ["core","memory","voice","echo","uploads"],
    },
    "all-around-customs": {
        "name": "All Around Customs",
        "domain": "allaroundcustoms.com",
        "description": "AI DTF Print Platform",
        "theme": "orange",
        "modules": ["core","design","uploads","tattoo","gallery"],
    },
    "kindred-love-birds": {
        "name": "Kindred Love Birds",
        "domain": "kindredlovebirds.com",
        "description": "AI Relationship Platform",
        "theme": "rose",
        "modules": ["core","memory","voice"],
    },
    "residentsync-ai": {
        "name": "ResidentSync AI",
        "domain": "residentsyncai.com",
        "description": "AI Property Management Platform",
        "theme": "green",
        "modules": ["core","uploads","admin"],
    },
}

# ── Founder override — server-side, cannot be bypassed ─────────────────────
FOUNDER_EMAILS = {
    "millzterrell210@icloud.com",
    "millzterrell5@gmail.com",
}

def is_founder(email: Optional[str]) -> bool:
    if not email: return False
    return email.lower().strip() in FOUNDER_EMAILS

def get_founder_override(email: Optional[str]) -> Optional[Dict]:
    if not is_founder(email): return None
    return {
        "role": "super_admin",
        "plan": "founder",
        "access_level": "founder_override",
        "unlimited_access": True,
        "all_modules": True,
        "billing_bypass": True,
        "audit_access": True,
    }

# ── FastAPI init ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="TerrellOS Orchestration Core",
    version="9.1.0-creator-studio",
    description="Universal AI OS — Powers entire TM Designs ecosystem",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
_CORS_ENV = os.getenv("CORS_ORIGINS", "")
_CORS_ALLOWED = [o.strip() for o in _CORS_ENV.split(",") if o.strip()] or [
    "https://app.tm-dezigns.com",
    "https://pastoraiconnect.com",
    "https://heavenlyeternalecho.com",
    "https://allaroundcustoms.com",
    "https://kindredlovebirds.com",
    "https://residentsyncai.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "https://hee-frontend.onrender.com",
    "https://terrellos-frontend.onrender.com",
    "https://pro-se-ai.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ALLOWED,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── App identity middleware ────────────────────────────────────────────────────
@app.middleware("http")
async def app_identity_middleware(request: Request, call_next):
    app_id = (
        request.headers.get("X-App-ID") or
        request.headers.get("x-app-id") or
        "terrellos"
    )
    request.state.app_id = app_id
    request.state.app_config = APP_REGISTRY.get(app_id, APP_REGISTRY["terrellos"])
    response = await call_next(request)
    response.headers["X-Powered-By"] = "TerrellOS Orchestration Core"
    response.headers["X-App-Resolved"] = app_id
    return response

# ── Mount routers ──────────────────────────────────────────────────────────────
app.include_router(core_router)
app.include_router(memory_router)
app.include_router(voice_router)
app.include_router(pastor_router)
app.include_router(bible_router)
app.include_router(word_study_router)
app.include_router(echo_router)
app.include_router(companion_router)
app.include_router(design_router)
app.include_router(founder_router)
app.include_router(admin_router)
app.include_router(db_router)
app.include_router(billing_router)
app.include_router(fn_router)
app.include_router(uploads_router)
app.include_router(tattoo_router)
app.include_router(gallery_router)
app.include_router(auth_router)
app.include_router(system_router)
app.include_router(paypal_router, prefix="/v1/paypal", tags=["PayPal Payments"])
app.include_router(payments_router)
app.include_router(checkout_router)
app.include_router(voice_interview_router)
app.include_router(bail_router)

# ── Global env ────────────────────────────────────────────────────────────────
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ── Root endpoints ─────────────────────────────────────────────────────────────
@app.get("/")
async def root(request: Request):
    app_id = getattr(request.state, "app_id", "terrellos")
    cfg = APP_REGISTRY.get(app_id, APP_REGISTRY["terrellos"])
    return {
        "success": True,
        "service": "TerrellOS Orchestration Core",
        "version": "9.1.0-creator-studio",
        "resolved_app": cfg["name"],
        "app_id": app_id,
        "status": "online",
        "docs": "/docs",
        "health": "/health",
        "ecosystem": list(APP_REGISTRY.keys()),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.on_event("startup")
async def _ensure_pastor_tables():
    """Ensure pastor_recordings table exists on startup."""
    try:
        from pastor_db import ensure_pastor_recordings_table
        result = await ensure_pastor_recordings_table()
        if result:
            print("[startup] ✅ pastor_recordings table ready")
        else:
            print("[startup] ⚠️  pastor_recordings table check skipped (no DB config)")
    except Exception as e:
        print(f"[startup] ❌ pastor_recordings ensure error: {e}")


@app.get("/health")
async def health(request: Request):
    app_id = getattr(request.state, "app_id", "terrellos")
    return {
        "success": True,
        "status": "healthy",
        "version": "9.1.0-creator-studio",
        "app_id": app_id,
        "fastapi": "online",
        "openai_configured": bool(OPENAI_API_KEY),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "image_generation": "ready" if OPENAI_API_KEY else "needs_key",
        "voice_synthesis": "ready" if ELEVENLABS_API_KEY else "needs_key",
        "whisper_transcription": "ready" if OPENAI_API_KEY else "needs_key",
        "cors_origins": len(_CORS_ALLOWED),
        "registered_apps": len(APP_REGISTRY),
        "time": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/v1/ecosystem")
async def ecosystem():
    """Returns the full app registry — used by TerrellOS founder dashboard."""
    return {
        "success": True,
        "apps": APP_REGISTRY,
        "total": len(APP_REGISTRY),
        "backend": "terrellos-backend.fly.dev",
        "time": datetime.now(timezone.utc).isoformat(),
    }

@app.post("/v1/founder/identify")
async def founder_identify(request: Request):
    """Server-side founder identity resolution."""
    body = await request.json()
    email = body.get("email", "")
    override = get_founder_override(email)
    if override:
        return {"success": True, "is_founder": True, "override": override}
    return {"success": True, "is_founder": False, "override": None}

# ── Legacy /chat compatibility ─────────────────────────────────────────────────
class LegacyChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "terrell"
    app_id: Optional[str] = "terrellos"

@app.post("/chat")
async def legacy_chat(payload: LegacyChatRequest, request: Request):
    """Legacy /chat — delegates to /v1/core/chat."""
    app_id = payload.app_id or getattr(request.state, "app_id", "terrellos")
    cfg = APP_REGISTRY.get(app_id, APP_REGISTRY["terrellos"])
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Missing message")
    if not openai_client:
        return {"success": True, "mode": "fallback",
                "reply": f"[{cfg['name']}] Received: {payload.message}. (OpenAI key not set)",
                "app": cfg["name"]}
    try:
        system_prompt = f"You are the AI core of {cfg['name']}. {cfg['description']}. Be helpful, focused, and on-brand."
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": payload.message}],
            temperature=0.7,
        )
        return {"success": True, "reply": resp.choices[0].message.content, "app": cfg["name"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def status(request: Request):
    app_id = getattr(request.state, "app_id", "terrellos")
    cfg = APP_REGISTRY.get(app_id, APP_REGISTRY["terrellos"])
    return {
        "service": cfg["name"],
        "version": "9.1.0-creator-studio",
        "status": "online",
        "app_id": app_id,
        "capabilities": {
            "chat": bool(OPENAI_API_KEY),
            "voice": bool(ELEVENLABS_API_KEY),
            "images": bool(OPENAI_API_KEY),
            "transcribe": bool(OPENAI_API_KEY),
            "memory": True,
            "uploads": True,
        },
        "time": datetime.now(timezone.utc).isoformat(),
    }