"""
/v1/tattoo/* — AI Tattoo Studio
Modes: concept art, stencil/outline, placement preview, vector conversion
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
import os

router = APIRouter(prefix="/v1/tattoo", tags=["AI Tattoo Studio"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ── Style prompt builders ────────────────────────────────────────────────────

STYLE_PROMPTS = {
    "concept":   "Professional tattoo concept art, highly detailed, artistic rendering, realistic shading, tattoo industry quality",
    "stencil":   "Pure black and white tattoo stencil, clean bold outlines only, no shading, no grey tones, transfer-ready linework, white background, professional tattoo stencil",
    "blackwork": "Bold blackwork tattoo design, solid black fills, geometric precision, strong contrast, tribal-influenced, tattoo flash sheet style",
    "realism":   "Black and grey realism tattoo concept, photorealistic shading, fine detail work, smooth gradients, professional tattoo artist quality",
    "fineline":  "Fine line tattoo design, delicate thin lines, minimalist, elegant, single needle style, precise linework",
    "neotraditional": "Neo-traditional tattoo design, bold outlines, rich colors, ornate detail, Art Nouveau influence, tattoo flash quality",
    "japanese":  "Traditional Japanese tattoo design (Irezumi), bold outlines, classic color palette, flowing composition, koi/dragon/wave elements",
    "geometric": "Sacred geometry tattoo design, precise geometric shapes, mandala elements, dotwork shading, symmetrical composition",
}

PLACEMENT_CONTEXT = {
    "sleeve":    "full arm sleeve tattoo layout, wraparound composition",
    "forearm":   "forearm tattoo placement, portrait orientation",
    "chest":     "chest piece tattoo, centered composition, symmetrical",
    "back":      "full back tattoo piece, large scale composition",
    "leg":       "leg sleeve or thigh tattoo placement",
    "neck":      "neck tattoo design, compact composition",
    "hand":      "hand tattoo design, fingers and knuckles considered",
    "ribcage":   "ribcage/side tattoo, vertical flowing composition",
}

class TattooGenerateRequest(BaseModel):
    prompt: str
    style: Optional[str] = "concept"          # concept | stencil | blackwork | realism | fineline | neotraditional | japanese | geometric
    placement: Optional[str] = None            # sleeve | forearm | chest | back | leg | neck | hand | ribcage
    size: Optional[str] = "1024x1024"
    quality: Optional[str] = "hd"
    user_id: Optional[str] = None
    color_mode: Optional[str] = "color"        # color | blackgrey | blackwork

class TattooOutlineRequest(BaseModel):
    prompt: str
    placement: Optional[str] = None
    size: Optional[str] = "1024x1024"
    user_id: Optional[str] = None

class TattooVariationRequest(BaseModel):
    prompt: str
    count: Optional[int] = 3
    styles: Optional[List[str]] = None        # Generate multiple style variations

class VectorizeRequest(BaseModel):
    image_url: Optional[str] = None
    description: str
    output_format: Optional[str] = "svg"      # svg | eps | ai
    user_id: Optional[str] = None

class UpscaleRequest(BaseModel):
    prompt: str                               # Re-generate at higher quality
    original_style: Optional[str] = "concept"
    size: Optional[str] = "1792x1024"
    user_id: Optional[str] = None

def build_tattoo_prompt(prompt: str, style: str, placement: Optional[str], color_mode: str) -> str:
    style_context = STYLE_PROMPTS.get(style, STYLE_PROMPTS["concept"])
    placement_context = PLACEMENT_CONTEXT.get(placement, "") if placement else ""
    color_context = {
        "color": "full color palette",
        "blackgrey": "black and grey only, no color",
        "blackwork": "solid black ink only, no grey tones",
    }.get(color_mode, "")
    
    parts = [f"Tattoo design: {prompt}", style_context]
    if placement_context: parts.append(placement_context)
    if color_context: parts.append(color_context)
    parts.append("No background clutter. Clean professional tattoo artist quality. High contrast.")
    return ". ".join(parts)

@router.post("/generate")
async def generate_tattoo(payload: TattooGenerateRequest):
    """Generate tattoo concept art in specified style."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    
    enhanced_prompt = build_tattoo_prompt(
        payload.prompt, payload.style,
        payload.placement, payload.color_mode
    )
    
    try:
        resp = client.images.generate(
            model="dall-e-3",
            prompt=enhanced_prompt,
            size=payload.size,
            quality=payload.quality if payload.style != "stencil" else "natural",
            n=1,
        )
        return {
            "success": True,
            "image_url": resp.data[0].url,
            "prompt_used": enhanced_prompt,
            "original_prompt": payload.prompt,
            "style": payload.style,
            "placement": payload.placement,
            "type": "tattoo_concept",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/outline")
async def generate_outline(payload: TattooOutlineRequest):
    """Generate stencil-ready black outline for tattoo transfer."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    
    stencil_prompt = f"Professional tattoo stencil outline: {payload.prompt}. Pure black lines on white background. Bold clean outlines, no shading, no grey, no color. Transfer-ready tattoo stencil quality. Thick outer lines, thinner detail lines. Print-ready."
    if payload.placement:
        stencil_prompt += f" Layout optimized for {PLACEMENT_CONTEXT.get(payload.placement, payload.placement)}."
    
    try:
        resp = client.images.generate(
            model="dall-e-3",
            prompt=stencil_prompt,
            size=payload.size,
            quality="hd",
            n=1,
        )
        return {
            "success": True,
            "image_url": resp.data[0].url,
            "prompt_used": stencil_prompt,
            "original_prompt": payload.prompt,
            "type": "tattoo_stencil",
            "transfer_ready": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/variations")
async def generate_variations(payload: TattooVariationRequest):
    """Generate multiple style variations of the same tattoo concept."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    
    styles = payload.styles or ["concept", "stencil", "blackwork"][:payload.count]
    results = []
    
    for style in styles:
        enhanced = build_tattoo_prompt(payload.prompt, style, None, "blackgrey" if style in ["stencil","blackwork","realism"] else "color")
        try:
            resp = client.images.generate(
                model="dall-e-3", prompt=enhanced,
                size="1024x1024", quality="standard" if style == "stencil" else "vivid", n=1,
            )
            results.append({
                "style": style,
                "image_url": resp.data[0].url,
                "prompt_used": enhanced,
            })
        except Exception as e:
            results.append({"style": style, "error": str(e)})
    
    return {"success": True, "variations": results, "total": len(results), "original_prompt": payload.prompt}

@router.post("/vectorize")
async def vectorize_tattoo(payload: VectorizeRequest):
    """Generate SVG-optimized vector description and clean linework."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    
    vector_prompt = f"""You are a professional tattoo artist and vector designer.

Analyze this tattoo design concept and provide:

1. SVG_PATHS: Describe the main vector path shapes needed (outline, fill areas, detail lines)
2. COLOR_PALETTE: Exact hex colors (max 6 for tattoos)
3. LINE_WEIGHTS: Stroke widths for outer lines vs inner details
4. LAYER_ORDER: Which elements go on top
5. PRINT_NOTES: Recommendations for DTF/stencil output
6. SIMPLIFIED_PROMPT: A refined DALL-E prompt optimized for clean vector-style output

Design: {payload.description}
Output format: {payload.output_format.upper()}

Be specific and technical. This is for professional tattoo/print production."""
    
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": vector_prompt}],
        max_tokens=1000, temperature=0.3,
    )
    
    return {
        "success": True,
        "vector_guide": resp.choices[0].message.content,
        "description": payload.description,
        "output_format": payload.output_format,
        "type": "vector_analysis",
    }

@router.post("/upscale")
async def upscale_tattoo(payload: UpscaleRequest):
    """Re-generate at maximum quality/size for print production."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    
    enhanced = build_tattoo_prompt(payload.prompt, payload.original_style, None, "color")
    enhanced += ". Maximum detail, print resolution quality, professional production ready."
    
    try:
        resp = client.images.generate(
            model="dall-e-3", prompt=enhanced,
            size=payload.size, quality="hd", n=1,
        )
        return {
            "success": True,
            "image_url": resp.data[0].url,
            "size": payload.size,
            "quality": "hd",
            "type": "upscaled",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/styles")
async def list_styles():
    """Return all available tattoo styles and placements."""
    return {
        "success": True,
        "styles": list(STYLE_PROMPTS.keys()),
        "placements": list(PLACEMENT_CONTEXT.keys()),
        "color_modes": ["color", "blackgrey", "blackwork"],
        "output_formats": ["concept", "stencil", "vector_guide"],
    }
