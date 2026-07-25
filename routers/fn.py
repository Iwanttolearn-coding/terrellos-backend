"""
routers/fn.py — TerrellOS Function Invoke Router
Maps base44.functions.invoke(name, payload) → POST /v1/fn/:name
Routes to the appropriate existing backend module.
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Any, Dict
from pydantic import BaseModel
import os

router = APIRouter(prefix="/v1/fn", tags=["Functions"])

class FnPayload(BaseModel):
    payload: Dict[str, Any] = {}

# Function name → backend route map
FN_ROUTE_MAP = {
    "generateSermon":       "/v1/pastor/sermon",
    "generateBibleStudy":   "/v1/bible/study",
    "generateVoice":        "/v1/voice/speak",
    "analyzeTexas":         "/v1/texas/analyze",
    "generateMotion":       "/v1/texas/motion/generate",
    "companionRespond":     "/v1/echo/companion/respond",
    "transcribeAudio":      "/v1/voice/transcribe",
    "generateTattoo":       "/v1/tattoo/generate",
    "generatePoem":         "/v1/core/chat",
}

@router.post("/{fn_name}")
async def invoke_function(fn_name: str, request: Request):
    """Proxy function invoke calls to the correct backend route."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    target = FN_ROUTE_MAP.get(fn_name)
    if not target:
        # Unknown function — return empty success (graceful degradation)
        return {"ok": True, "result": None, "fn": fn_name, "note": "unmapped function"}
    
    # Forward to internal route
    import httpx
    backend_base = os.getenv("SELF_URL", "http://localhost:8000")
    auth_header  = request.headers.get("Authorization", "")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{backend_base}{target}",
                json=body,
                headers={"Authorization": auth_header, "Content-Type": "application/json"},
            )
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e), "fn": fn_name}
