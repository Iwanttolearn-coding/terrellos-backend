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
    user_id: str
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
    name = payload.loved_one_name or "your loved one"
    if not client:
        return {"success": True, "message": f"A message of love and legacy for {name}."}
    prompt = f"Write a heartfelt legacy message for {name}. Prompt: {payload.prompt}. Make it warm, specific, and meaningful for future generations."
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
