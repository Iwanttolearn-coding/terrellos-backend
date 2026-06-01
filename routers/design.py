"""
/v1/design/* — All Around Customs: AI image gen, vectorization, print tools
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
from .usage_logger import log_usage
from .auth import email_from_request
import os

router = APIRouter(prefix="/v1/design", tags=["All Around Customs"])
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Use env-configurable model; gpt-image-1 is the default (dall-e-3 is unavailable on this key tier)
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

class ImageGenerateRequest(BaseModel):
    prompt: str
    style: Optional[str] = "vivid"
    quality: Optional[str] = "standard"
    size: Optional[str] = "1024x1024"
    n: Optional[int] = 1
    user_id: Optional[str] = None
    app_id: Optional[str] = "terrellos"

class PrintQuoteRequest(BaseModel):
    width_inches: float
    height_inches: float
    quantity: int
    material: Optional[str] = "dtf"

@router.post("/generate-image")
async def generate_image(payload: ImageGenerateRequest, request: Request):
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    user = payload.user_id or email_from_request(request) or "anonymous"
    try:
        resp = client.images.generate(
            model=IMAGE_MODEL,
            prompt=payload.prompt,
            size=payload.size or "1024x1024",
            n=1,
        )
        image_url = resp.data[0].url if resp.data else None
        # Fire-and-forget usage log — never blocks response
        log_usage(
            endpoint="/v1/design/generate-image",
            user_id=user,
            model=IMAGE_MODEL,
            provider="openai",
            extra={"prompt_length": len(payload.prompt)},
        )
        return {
            "success": True,
            "image_url": image_url,
            "images": [{"url": img.url} for img in resp.data],
            "prompt": payload.prompt,
            "model": IMAGE_MODEL,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/memorial-image")
async def memorial_image(payload: ImageGenerateRequest, request: Request):
    enhanced_prompt = f"A dignified, emotionally resonant memorial image: {payload.prompt}. Style: artistic, warm tones, timeless."
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    user = payload.user_id or email_from_request(request) or "anonymous"
    try:
        resp = client.images.generate(
            model=IMAGE_MODEL,
            prompt=enhanced_prompt,
            size=payload.size or "1024x1024",
            n=1,
        )
        log_usage(
            endpoint="/v1/design/memorial-image",
            user_id=user,
            model=IMAGE_MODEL,
            provider="openai",
        )
        return {
            "success": True,
            "images": [{"url": img.url} for img in resp.data],
            "type": "memorial",
            "model": IMAGE_MODEL,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/print-quote")
async def print_quote(payload: PrintQuoteRequest):
    sq_in = payload.width_inches * payload.height_inches
    base_price = max(1.50, sq_in * 0.08)
    unit_price = base_price * (0.85 if payload.quantity >= 50 else 1.0)
    return {
        "success": True,
        "width": payload.width_inches, "height": payload.height_inches,
        "quantity": payload.quantity, "material": payload.material,
        "unit_price": round(unit_price, 2),
        "total": round(unit_price * payload.quantity, 2),
        "currency": "USD",
    }

@router.post("/vectorize-prompt")
async def vectorize_prompt(request: Request):
    body = await request.json()
    description = body.get("description", "")
    user = email_from_request(request) or "anonymous"
    if not client or not description:
        raise HTTPException(status_code=400, detail="Description required and OpenAI must be configured")
    prompt = f"Create a clean, professional vector art description optimized for DTF printing: {description}. Include: color palette (max 8 colors), line style, composition, background treatment."
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
    )
    log_usage(
        endpoint="/v1/design/vectorize-prompt",
        user_id=user,
        model="gpt-4o-mini",
        provider="openai",
    )
    return {"success": True, "vector_prompt": resp.choices[0].message.content}
