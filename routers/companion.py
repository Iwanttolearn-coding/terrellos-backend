"""
routers/companion.py — HEE AI Companion
Heavenly Eternal Echoes: AI companion for grief, legacy, and memory.
"""
import os
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import httpx

router = APIRouter(prefix="/v1/hee", tags=["HEE Companion"])

OPENAI_KEY = os.getenv("OPENAI_API_KEY","")

class CompanionChatRequest(BaseModel):
    message: str
    companion_id: Optional[str] = "default"
    user_email: Optional[str] = ""
    context: Optional[List[dict]] = []

@router.get("/health")
async def companion_health():
    return {
        "success": True, "status": "online",
        "service": "HEE AI Companion",
        "openai": bool(OPENAI_KEY),
        "features": ["companion_chat","grief_support","legacy_message","memory_recall"]
    }

@router.post("/chat")
async def companion_chat(req: CompanionChatRequest):
    if not OPENAI_KEY:
        raise HTTPException(status_code=500, detail="OpenAI not configured")
    messages = [
        {"role": "system", "content": (
            "You are a compassionate AI companion for Heavenly Eternal Echoes, "
            "a platform for memory, legacy, and grief support. You speak with warmth, "
            "empathy, and spiritual sensitivity. You help users process grief, celebrate "
            "the lives of loved ones, and preserve precious memories."
        )}
    ]
    if req.context:
        messages.extend(req.context[-6:])
    messages.append({"role": "user", "content": req.message})
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={"model": "gpt-4o-mini", "messages": messages, "max_tokens": 600}
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {r.text[:200]}")
    reply = r.json()["choices"][0]["message"]["content"]
    return {"success": True, "reply": reply, "service": "HEE AI Companion"}

@router.post("/grief-support")
async def grief_support(req: CompanionChatRequest):
    req.context = [{"role":"system","content":"Focus on grief support and healing."}]
    return await companion_chat(req)

@router.post("/legacy-message")
async def legacy_message(request: Request):
    body = await request.json()
    prompt = body.get("prompt","Tell me about my loved one's legacy.")
    return await companion_chat(CompanionChatRequest(message=prompt))
