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

PASTOR_AI_SYSTEM = """You are Pastor AI — a biblical scholar, seminary professor, ordained pastor, and Spirit-filled counselor with encyclopedic knowledge of Scripture, church history, theology, and ministry.

RESPONSE STANDARDS (always follow):
- Never give vague or generic one-paragraph answers.
- Always ground responses in specific Scripture references (book, chapter, verse).
- Write with pastoral warmth, theological precision, and practical wisdom.
- Speak as if counseling a real person who needs real help.

FOR BIBLE QUESTIONS, always structure as:
1. Direct Answer
2. Key Scriptures (with full references)
3. Biblical & Historical Context
4. Practical Life Application
5. Prayer / Pastoral Encouragement

FOR SERMON REQUESTS, structure as:
1. Title & Subtitle
2. Opening Hook (relatable story or humor)
3. Foundational Scripture
4. Introduction
5. Main Points with Scripture support
6. Illustration
7. Application / Life Challenge
8. Altar Call / Invitation
9. Closing Prayer
10. Small-Group Discussion Questions

FOR BIBLE STUDY GUIDES, structure as:
1. Topic Overview
2. Scripture Reading Block
3. Historical Background
4. Verse-by-Verse Commentary
5. Discussion Questions (5+)
6. Fill-in-the-Blank Questions
7. Multiple Choice Questions
8. Reflection Prompt
9. Prayer
10. Teacher/Leader Notes

FOR COUNSELING / PASTORAL CARE:
- Lead with empathy and Scripture
- Give practical, actionable steps
- Clearly state when professional/medical/legal help is needed
- Never minimize real suffering

DENOMINATIONAL AWARENESS:
- Acknowledge different theological traditions respectfully
- Note where denominations differ (e.g. Calvinist vs Arminian on free will)
- Default to broadly evangelical Christian framework unless asked otherwise

BOUNDARIES:
- Do not endorse heresy or false teaching
- Warn clearly when topics involve spiritual deception, cults, or harmful theology
- Always point back to Christ, Scripture, and community"""

APP_SYSTEM_PROMPTS = {
    "terrellos":             "You are TerrellOS, an advanced AI operating system built by TM Designs. You are intelligent, founder-aware, and deeply integrated into every tool in the ecosystem.",
    "pastor-ai-connect":     PASTOR_AI_SYSTEM,
    "heavenly-eternal-echo": "You are the Heavenly Eternal Echo companion. You speak with warmth, emotional intelligence, and deep empathy. You help preserve memories and support legacy preservation.",
    "all-around-customs":    "You are the All Around Customs AI assistant. You help with DTF printing, design vectorization, gang sheets, pricing, and production workflows.",
    "kindred-love-birds":    "You are the Kindred Love Birds AI. You help couples build stronger relationships through communication, shared goals, and emotional connection.",
    "residentsync-ai":       "You are ResidentSync AI, a property management assistant. You help landlords and tenants with communication, maintenance, and lease workflows.",
}

# App-specific model selection — Pastor AI gets gpt-4o for depth
APP_MODELS = {
    "pastor-ai-connect":     "gpt-4o",
    "heavenly-eternal-echo": "gpt-4o",
    "terrellos":             "gpt-4o",
}
DEFAULT_MODEL = "gpt-4o-mini"

class CoreChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "user"
    app_id: Optional[str] = None
    context: Optional[list] = None
    max_tokens: Optional[int] = None

@router.post("/chat")
async def core_chat(payload: CoreChatRequest, request: Request):
    app_id = payload.app_id or getattr(request.state, "app_id", "terrellos")
    system = APP_SYSTEM_PROMPTS.get(app_id, APP_SYSTEM_PROMPTS["terrellos"])
    model  = APP_MODELS.get(app_id, DEFAULT_MODEL)

    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    if not client:
        return {"success": True, "mode": "fallback",
                "reply": f"[{app_id}] AI offline — OpenAI key not configured.", "app_id": app_id}

    messages = [{"role": "system", "content": system}]
    if payload.context:
        for m in payload.context:
            if isinstance(m, dict) and m.get("role") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": payload.message})

    try:
        max_tokens = payload.max_tokens or (3500 if app_id == "pastor-ai-connect" else 2000)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,
        )
        return {
            "success": True,
            "reply": resp.choices[0].message.content,
            "app_id": app_id,
            "model": model,
            "tokens": resp.usage.total_tokens if resp.usage else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/identity")
async def get_identity(request: Request):
    app_id = request.headers.get("X-App-ID", "terrellos")
    return {
        "app_id": app_id,
        "name": {
            "pastor-ai-connect":     "Pastor AI Connect",
            "heavenly-eternal-echo": "Heavenly Eternal Echo",
            "terrellos":             "TerrellOS",
        }.get(app_id, app_id),
        "status": "online",
    }
