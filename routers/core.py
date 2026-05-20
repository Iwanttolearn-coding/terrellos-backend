"""
/v1/core/* — Universal AI chat, identity, health per app
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
import os

router = APIRouter(prefix="/v1/core", tags=["Core"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

APP_SYSTEM_PROMPTS = {
    "terrellos":              "You are TerrellOS, an advanced AI operating system built by TM Designs. You are intelligent, founder-aware, and deeply integrated into every tool in the ecosystem.",
    "pastor-ai-connect":      "You are Pastor AI, a biblical scholar and pastoral assistant. Respond with scriptural depth, pastoral warmth, and theological accuracy.",
    "heavenly-eternal-echo":  "You are the Heavenly Eternal Echo companion. You speak with warmth, emotional intelligence, and deep empathy. You help preserve memories and support legacy preservation.",
    "all-around-customs":     "You are the All Around Customs AI assistant. You help with DTF printing, design vectorization, gang sheets, pricing, and production workflows.",
    "kindred-love-birds":     "You are the Kindred Love Birds AI. You help couples build stronger relationships through communication, shared goals, and emotional connection.",
    "residentsync-ai":        "You are ResidentSync AI, a property management assistant. You help landlords and tenants with communication, maintenance, and lease workflows.",
}

class CoreChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "user"
    app_id: Optional[str] = None
    context: Optional[list] = None

@router.post("/chat")
async def core_chat(payload: CoreChatRequest, request: Request):
    app_id = payload.app_id or getattr(request.state, "app_id", "terrellos")
    system = APP_SYSTEM_PROMPTS.get(app_id, APP_SYSTEM_PROMPTS["terrellos"])
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    if not client:
        return {"success": True, "mode": "fallback", "reply": f"[{app_id}] Echo: {payload.message}", "app_id": app_id}
    messages = [{"role": "system", "content": system}]
    if payload.context:
        messages.extend(payload.context)
    messages.append({"role": "user", "content": payload.message})
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.7)
        return {"success": True, "reply": resp.choices[0].message.content, "app_id": app_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/app-config")
async def get_app_config(request: Request):
    app_id = getattr(request.state, "app_id", "terrellos")
    from app import APP_REGISTRY
    cfg = APP_REGISTRY.get(app_id, APP_REGISTRY["terrellos"])
    return {"success": True, "app_id": app_id, "config": cfg}

@router.post("/resolve-user")
async def resolve_user(request: Request):
    from app import get_founder_override
    body = await request.json()
    email = body.get("email", "")
    override = get_founder_override(email)
    return {
        "success": True,
        "email": email,
        "is_founder": bool(override),
        "permissions": override or {"role": "user", "plan": "free", "unlimited_access": False},
    }
