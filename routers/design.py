"""
/v1/design/* — All Around Customs: AI image gen, vectorization, print tools
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
import os

router = APIRouter(prefix="/v1/design", tags=["All Around Customs"])
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
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
async def generate_image(payload: ImageGenerateRequest):
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    try:
        resp = client.images.generate(
            model="dall-e-3", prompt=payload.prompt,
            size=payload.size, quality=payload.quality,
            style=payload.style, n=payload.n,
        )
        return {"success": True, "images": [{"url": img.url} for img in resp.data],
                "prompt": payload.prompt}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/memorial-image")
async def memorial_image(payload: ImageGenerateRequest):
    enhanced_prompt = f"A dignified, emotionally resonant memorial image: {payload.prompt}. Style: artistic, warm tones, timeless."
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    try:
        resp = client.images.generate(
            model="dall-e-3", prompt=enhanced_prompt,
            size=payload.size, quality="hd", style="natural", n=1,
        )
        return {"success": True, "images": [{"url": img.url} for img in resp.data],
                "type": "memorial"}
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
async def vectorize_prompt(request: dict):
    description = request.get("description", "")
    if not client or not description:
        raise HTTPException(status_code=400, detail="Description required and OpenAI must be configured")
    prompt = f"Create a clean, professional vector art description optimized for DTF printing: {description}. Include: color palette (max 8 colors), line style, composition, background treatment."
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
    )
    return {"success": True, "vector_prompt": resp.choices[0].message.content}
