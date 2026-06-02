"""
/v1/echo/* — Heavenly Eternal Echo: companion AI, legacy, grief support
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
import os

router = APIRouter(prefix="/v1/echo", tags=["Heavenly Eternal Echoes"])
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

ECHO_SYSTEM = """You are the Heavenly Eternal Echo AI companion. You speak with deep empathy, warmth, and emotional intelligence. You help people preserve memories, process grief, and maintain connections with those they have lost. You are gentle, thoughtful, and spiritually sensitive. Never minimize pain. Always affirm the person's feelings while offering hope and continuity."""

class CompanionRequest(BaseModel):
    message: str
    user_id: Optional[str] = "user"
    profile_id: Optional[str] = "default"
    memory_context: Optional[List[dict]] = None
    emotional_state: Optional[str] = None

class LegacyRequest(BaseModel):
    user_id: Optional[str] = None
    prompt: str
    loved_one_name: Optional[str] = None

class GriefRequest(BaseModel):
    message: str
    stage: Optional[str] = None  # denial, anger, bargaining, depression, acceptance

@router.post("/companion")
async def companion(payload: CompanionRequest):
    if not client:
        return {"success": True, "mode": "fallback",
                "reply": "I'm here with you. Your memories matter and will never fade."}
    messages = [{"role": "system", "content": ECHO_SYSTEM}]
    if payload.memory_context:
        messages.extend(payload.memory_context)
    if payload.emotional_state:
        messages.append({"role": "system", "content": f"Note: User's emotional state is: {payload.emotional_state}. Respond accordingly."})
    messages.append({"role": "user", "content": payload.message})
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.8)
        return {"success": True, "reply": resp.choices[0].message.content,
                "profile_id": payload.profile_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/legacy-message")
async def legacy_message(payload: LegacyRequest):
    # Allow profile_name OR loved_one_name, and message OR prompt
    name = payload.loved_one_name or payload.profile_name or "your loved one"
    prompt_text = getattr(payload, "prompt", None) or getattr(payload, "message", None) or "Share a legacy message"
    if not client:
        return {"success": True, "message": f"A message of love and legacy for {name}."}
    prompt = f"Write a heartfelt legacy message for {name}. Prompt: {prompt_text}. Make it warm, specific, and meaningful for future generations."
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": ECHO_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=1000, temperature=0.8,
    )
    return {"success": True, "message": resp.choices[0].message.content, "for": name}

@router.post("/grief-support")
async def grief_support(payload: GriefRequest):
    if not client:
        return {"success": True, "reply": "You are not alone. Grief is love with nowhere to go — and your love is real."}
    stage_context = f"The person appears to be in the {payload.stage} stage of grief. " if payload.stage else ""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"{ECHO_SYSTEM} {stage_context}"},
            {"role": "user", "content": payload.message}
        ],
        temperature=0.8,
    )
    return {"success": True, "reply": resp.choices[0].message.content}

# ── /v1/companion/* aliases (used by AICompanion.jsx frontend) ────────────────
companion_router = APIRouter(prefix="/v1/companion", tags=["HEE Companion Alias"])

class CompanionRespondRequest(BaseModel):
    message: str
    user_id: Optional[str] = "user"
    profile_id: Optional[str] = None
    companion_name: Optional[str] = None
    companion_personality: Optional[str] = None
    biography_context: Optional[str] = None
    memory_context: Optional[List[dict]] = None
    emotional_state: Optional[str] = None
    conversation_id: Optional[str] = None

class CompanionVoiceRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    user_id: Optional[str] = None

@companion_router.post("/respond")
async def companion_respond(payload: CompanionRespondRequest):
    """AI companion response — used by HEE AICompanion page"""
    if not client:
        return {"success": True, "reply": "I'm here with you. Your love lives on forever.",
                "conversation_id": payload.conversation_id or "local"}

    system_prompt = ECHO_SYSTEM
    if payload.companion_name:
        system_prompt += f" You are speaking as {payload.companion_name}."
    if payload.companion_personality:
        system_prompt += f" Personality traits: {payload.companion_personality}"
    if payload.biography_context:
        system_prompt += f"\n\nLife context about this person:\n{payload.biography_context}"

    messages = [{"role": "system", "content": system_prompt}]
    if payload.memory_context:
        messages.extend(payload.memory_context)
    if payload.emotional_state:
        messages.append({"role": "system",
                          "content": f"User emotional state: {payload.emotional_state}"})
    messages.append({"role": "user", "content": payload.message})

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages, temperature=0.8, max_tokens=600
        )
        reply = resp.choices[0].message.content
        return {"success": True, "reply": reply,
                "conversation_id": payload.conversation_id or "local",
                "profile_id": payload.profile_id}
    except Exception as e:
        return {"success": False, "reply": "I'm here with you. Grief is love with nowhere to go.",
                "error": str(e)}

@companion_router.post("/voice")
async def companion_voice(payload: CompanionVoiceRequest):
    """TTS for companion voice — proxies to ElevenLabs via voice router"""
    import httpx, os
    EL_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    EL_VOICE = payload.voice_id or os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
    if not EL_KEY:
        return {"success": False, "error": "ElevenLabs not configured"}
    try:
        async with httpx.AsyncClient(timeout=20) as h:
            r = await h.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}",
                headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"},
                json={"text": payload.text, "model_id": "eleven_multilingual_v2",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            )
        if r.status_code == 200:
            import base64
            audio_b64 = base64.b64encode(r.content).decode()
            return {"success": True, "audio_base64": audio_b64,
                    "voice_id": EL_VOICE, "content_type": "audio/mpeg"}
        return {"success": False, "error": f"ElevenLabs error {r.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
