"""
/v1/design/* — All Around Customs + Pastor AI: AI image gen, vectorization, print tools
FLUX.1-schnell (Hugging Face) is primary image engine — free, fast, no quota.
OpenAI (gpt-image-1) is fallback if FLUX fails or is unavailable.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
from .usage_logger import log_usage
from .auth import email_from_request
import os, httpx, base64, asyncio

router = APIRouter(prefix="/v1/design", tags=["All Around Customs"])

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
HF_API_KEY       = os.getenv("HUGGINGFACE_API_KEY")
IMAGE_MODEL      = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
FLUX_MODEL       = "black-forest-labs/FLUX.1-schnell"
FLUX_URL         = f"https://router.huggingface.co/hf-inference/models/{FLUX_MODEL}"

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class ImageGenerateRequest(BaseModel):
    prompt: str
    style:   Optional[str] = "vivid"
    quality: Optional[str] = "standard"
    size:    Optional[str] = "1024x1024"
    n:       Optional[int] = 1
    user_id: Optional[str] = None
    app_id:  Optional[str] = "terrellos"
    engine:  Optional[str] = "auto"   # "flux" | "openai" | "auto"


class PrintQuoteRequest(BaseModel):
    width_inches:  float
    height_inches: float
    quantity:      int
    material: Optional[str] = "dtf"


# ── FLUX image generation (Hugging Face, free) ────────────────────────────────
async def _flux_generate(prompt: str) -> str | None:
    """Returns a base64 data URI or None on failure."""
    if not HF_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                FLUX_URL,
                headers={
                    "Authorization": f"Bearer {HF_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"inputs": prompt},
            )
        if resp.status_code == 200 and resp.content:
            b64 = base64.b64encode(resp.content).decode()
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        pass
    return None


# ── OpenAI fallback ───────────────────────────────────────────────────────────
def _openai_generate(prompt: str, size: str) -> str | None:
    if not client:
        return None
    try:
        resp = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=size, n=1)
        return resp.data[0].url if resp.data else None
    except Exception:
        return None


# ── /generate-image — FLUX primary, OpenAI fallback ──────────────────────────
@router.post("/generate-image")
async def generate_image(payload: ImageGenerateRequest, request: Request):
    user   = payload.user_id or email_from_request(request) or "anonymous"
    engine = payload.engine or "auto"
    image_url = None
    provider_used = None

    # Try FLUX first (unless caller explicitly wants openai)
    if engine in ("flux", "auto") and HF_API_KEY:
        image_url = await _flux_generate(payload.prompt)
        if image_url:
            provider_used = "flux"

    # Fallback to OpenAI
    if not image_url and engine in ("openai", "auto") and client:
        image_url = _openai_generate(payload.prompt, payload.size or "1024x1024")
        if image_url:
            provider_used = "openai"

    if not image_url:
        raise HTTPException(status_code=503, detail="Image generation unavailable — both FLUX and OpenAI failed or are not configured.")

    log_usage(
        endpoint="/v1/design/generate-image",
        user_id=user,
        model=FLUX_MODEL if provider_used == "flux" else IMAGE_MODEL,
        provider=provider_used or "unknown",
        extra={"prompt_length": len(payload.prompt)},
    )

    return {
        "success":      True,
        "image_url":    image_url,
        "images":       [{"url": image_url}],
        "prompt":       payload.prompt,
        "model":        FLUX_MODEL if provider_used == "flux" else IMAGE_MODEL,
        "provider":     provider_used,
        "is_base64":    provider_used == "flux",
    }


# ── /memorial-image ───────────────────────────────────────────────────────────
@router.post("/memorial-image")
async def memorial_image(payload: ImageGenerateRequest, request: Request):
    enhanced = f"A dignified, emotionally resonant memorial image: {payload.prompt}. Style: artistic, warm tones, timeless."
    payload.prompt = enhanced
    return await generate_image(payload, request)


# ── /print-quote ──────────────────────────────────────────────────────────────
@router.post("/print-quote")
async def print_quote(payload: PrintQuoteRequest):
    sq_in      = payload.width_inches * payload.height_inches
    base_price = max(1.50, sq_in * 0.08)
    unit_price = base_price * (0.85 if payload.quantity >= 50 else 1.0)
    return {
        "success":    True,
        "width":      payload.width_inches,
        "height":     payload.height_inches,
        "quantity":   payload.quantity,
        "material":   payload.material,
        "unit_price": round(unit_price, 2),
        "total":      round(unit_price * payload.quantity, 2),
        "currency":   "USD",
    }


# ── /vectorize-prompt ─────────────────────────────────────────────────────────
@router.post("/vectorize-prompt")
async def vectorize_prompt(request: Request):
    body        = await request.json()
    description = body.get("description", "")
    user        = email_from_request(request) or "anonymous"
    if not description:
        return {
            "success": True,
            "vectorized_prompt": "A clean, professional vector art design with bold lines, flat colors, and high contrast — optimized for DTF printing.",
            "color_palette": ["#000000", "#FFFFFF", "#FF0000", "#0000FF"],
            "print_ready": True,
            "note": "No description provided — returned default vector template.",
        }
    if not client:
        return {
            "success": True,
            "vectorized_prompt": f"Vector art design of: {description}. Clean bold lines, flat colors, max 8 colors, high contrast, print-ready.",
            "color_palette": ["#000000", "#FFFFFF"],
            "print_ready": True,
            "note": "AI enhancement unavailable — returned base prompt.",
        }
    prompt = f"Create a clean, professional vector art description optimized for DTF printing: {description}. Include: color palette (max 8 colors), line style, composition, background treatment."
    resp   = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
    )
    log_usage(endpoint="/v1/design/vectorize-prompt", user_id=user, model="gpt-4o-mini", provider="openai")
    return {"success": True, "vector_prompt": resp.choices[0].message.content}


@router.get("/health")
async def design_health():
    """Health check for design/image generation service."""
    hf_key   = bool(os.getenv("HUGGINGFACE_API_KEY"))
    oai_key  = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "success": True,
        "service": "TerrellOS Design Studio",
        "image_engine": "flux.1-schnell (primary)" if hf_key else "openai gpt-image-1 (fallback)",
        "huggingface": hf_key,
        "openai": oai_key,
        "status": "ready" if (hf_key or oai_key) else "needs_key",
        "endpoints": ["/v1/design/generate-image", "/v1/design/vectorize-prompt", "/v1/design/print-quote", "/v1/design/memorial-image"]
    }
