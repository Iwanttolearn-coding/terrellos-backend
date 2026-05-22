"""
/v1/tattoo/* — AI Tattoo Studio for All Around Customs
Models: gpt-image-1 (primary), dall-e-2 (fallback for size/quality combos)
Outline: accepts both JSON prompt and multipart file upload
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
import os, base64, io

router = APIRouter(prefix="/v1/tattoo", tags=["AI Tattoo Studio"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ── Style prompt builders ─────────────────────────────────────────────────────

STYLE_PROMPTS = {
    "concept":        "Professional tattoo concept art, highly detailed, artistic rendering, realistic shading, tattoo industry quality",
    "stencil":        "Pure black and white tattoo stencil, clean bold outlines only, no shading, no grey tones, transfer-ready linework, white background, professional tattoo stencil",
    "blackwork":      "Bold blackwork tattoo design, solid black fills, geometric precision, strong contrast, tribal-influenced, tattoo flash sheet style",
    "realism":        "Black and grey realism tattoo concept, photorealistic shading, fine detail work, smooth gradients, professional tattoo artist quality",
    "fineline":       "Fine line tattoo design, delicate thin lines, minimalist, elegant, single needle style, precise linework",
    "neotraditional": "Neo-traditional tattoo design, bold outlines, rich colors, ornate detail, Art Nouveau influence, tattoo flash quality",
    "japanese":       "Traditional Japanese tattoo design (Irezumi), bold outlines, classic color palette, flowing composition",
    "geometric":      "Sacred geometry tattoo design, precise geometric shapes, mandala elements, dotwork shading, symmetrical composition",
}

PLACEMENT_CONTEXT = {
    "sleeve":   "full arm sleeve tattoo layout, wraparound composition",
    "forearm":  "forearm tattoo placement, portrait orientation",
    "chest":    "chest piece tattoo, centered composition, symmetrical",
    "back":     "full back tattoo piece, large scale composition",
    "leg":      "leg sleeve or thigh tattoo placement",
    "neck":     "neck tattoo design, compact composition",
    "hand":     "hand tattoo design, fingers and knuckles considered",
    "ribcage":  "ribcage/side tattoo, vertical flowing composition",
}

# ── Pydantic models — Optional app_id/output_format so frontend payload is accepted ──

class TattooGenerateRequest(BaseModel):
    prompt:        str
    style:         Optional[str] = "concept"
    placement:     Optional[str] = None
    size:          Optional[str] = "1024x1024"
    quality:       Optional[str] = "high"
    color_mode:    Optional[str] = "color"
    output_format: Optional[str] = "concept"   # accepted but not used server-side
    app_id:        Optional[str] = None         # accepted but not used server-side
    language:      Optional[str] = "en"
    user_id:       Optional[str] = None

class TattooVariationRequest(BaseModel):
    prompt:    str
    image_url: Optional[str] = None
    count:     Optional[int] = 2
    styles:    Optional[List[str]] = None
    app_id:    Optional[str] = None

class VectorizeRequest(BaseModel):
    description:   Optional[str] = None
    image_url:     Optional[str] = None
    output_format: Optional[str] = "svg"
    app_id:        Optional[str] = None
    user_id:       Optional[str] = None

class UpscaleRequest(BaseModel):
    prompt:         str
    original_style: Optional[str] = "concept"
    size:           Optional[str] = "1536x1024"
    app_id:         Optional[str] = None
    user_id:        Optional[str] = None

def build_tattoo_prompt(prompt: str, style: str, placement: Optional[str], color_mode: str) -> str:
    style_ctx     = STYLE_PROMPTS.get(style, STYLE_PROMPTS["concept"])
    placement_ctx = PLACEMENT_CONTEXT.get(placement, "") if placement else ""
    color_ctx = {
        "color":     "vibrant full color palette",
        "blackgrey": "black and grey only, no color",
        "blackwork": "solid black ink only, no grey tones",
    }.get(color_mode, "")
    parts = [f"Tattoo design: {prompt}", style_ctx]
    if placement_ctx: parts.append(placement_ctx)
    if color_ctx:     parts.append(color_ctx)
    parts.append("No background clutter. Clean professional tattoo artist quality. High contrast.")
    return ". ".join(parts)

def generate_image(prompt: str, size: str = "1024x1024", quality: str = "high") -> str:
    """Try gpt-image-1 first, fall back to dall-e-2 on error."""
    # gpt-image-1 uses quality: low/medium/high (not hd/standard)
    safe_size    = size if size in ("1024x1024","1536x1024","1024x1536") else "1024x1024"
    safe_quality = quality if quality in ("low","medium","high") else "high"
    try:
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=safe_size,
            quality=safe_quality,
            n=1,
        )
        # gpt-image-1 returns b64_json
        if resp.data[0].b64_json:
            b64 = resp.data[0].b64_json
            return f"data:image/png;base64,{b64}"
        if resp.data[0].url:
            return resp.data[0].url
    except Exception as primary_err:
        # Fall back to dall-e-2 (256x256/512x512/1024x1024 only, no quality param)
        try:
            fb_size = "1024x1024"  # dall-e-2 max
            resp2 = client.images.generate(
                model="dall-e-2",
                prompt=prompt[:1000],
                size=fb_size,
                n=1,
            )
            if resp2.data[0].url:
                return resp2.data[0].url
        except Exception as fb_err:
            raise HTTPException(status_code=500, detail=f"Image generation failed: {primary_err} | fallback: {fb_err}")
    raise HTTPException(status_code=500, detail="No image returned from API")

# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_tattoo(payload: TattooGenerateRequest):
    """Generate tattoo art in specified style from a text prompt."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    enhanced = build_tattoo_prompt(payload.prompt, payload.style, payload.placement, payload.color_mode)
    image_url = generate_image(enhanced, payload.size or "1024x1024", "high")
    return {
        "success":         True,
        "image_url":       image_url,
        "prompt_used":     enhanced,
        "original_prompt": payload.prompt,
        "style":           payload.style,
        "placement":       payload.placement,
        "output_format":   payload.output_format,
        "type":            "tattoo_concept",
    }

@router.post("/outline")
async def generate_outline(
    file:          Optional[UploadFile] = File(None),
    style:         str = Form("stencil"),
    app_id:        Optional[str] = Form(None),
    language:      Optional[str] = Form("en"),
    prompt:        Optional[str] = Form(None),
):
    """
    Create a tattoo stencil/outline.
    Accepts multipart/form-data with an uploaded image file.
    Uses GPT-4o vision to analyze the image, then generates a stencil prompt,
    then calls gpt-image-1 to produce the outline.
    """
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")

    # If a file was uploaded, analyze it with vision first
    image_description = prompt or "the uploaded reference image"
    if file and file.filename:
        try:
            raw = await file.read()
            b64 = base64.b64encode(raw).decode()
            mime = file.content_type or "image/jpeg"
            vision_resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": (
                            "Describe this image in detail as if you are briefing a professional tattoo artist "
                            "who needs to create a tattoo stencil from it. Focus on: main subject, key shapes, "
                            "important details, composition, and which elements should be outlines vs filled. "
                            "Be concise and technical. 3-4 sentences max."
                        )}
                    ]
                }],
                max_tokens=300,
            )
            image_description = vision_resp.choices[0].message.content
        except Exception as e:
            image_description = prompt or "tattoo reference design"

    OUTLINE_STYLE_PROMPTS = {
        "stencil":  "Professional tattoo transfer stencil. Pure black outlines on white background. Bold outer lines, finer detail lines. No shading, no grey, no color. Transfer-ready.",
        "clean":    "Clean black tattoo outline. Smooth confident linework. No fills, no shading. Professional tattoo line drawing.",
        "dtf":      "DTF print-ready tattoo design. Clean outlined art with solid fills. High contrast. Print production quality.",
        "vector":   "Vector-style tattoo outline. Geometric clean lines, minimal anchor points. Suitable for vinyl cutting or screen printing.",
        "coloring": "Tattoo coloring page style. Clear bold outlines with blank interior areas ready to be colored. Adult coloring book quality.",
    }
    style_instruction = OUTLINE_STYLE_PROMPTS.get(style, OUTLINE_STYLE_PROMPTS["stencil"])
    outline_prompt = f"Tattoo design based on: {image_description}. {style_instruction} No background. High contrast. Professional tattoo artist quality."

    image_url = generate_image(outline_prompt, "1024x1024", "high")
    return {
        "success":           True,
        "image_url":         image_url,
        "source_description":image_description,
        "style":             style,
        "type":              "tattoo_outline",
    }

@router.post("/variations")
async def generate_variations(payload: TattooVariationRequest):
    """Generate style variations of a tattoo concept."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    styles  = (payload.styles or ["concept", "stencil", "blackwork"])[:max(1, payload.count or 2)]
    results = []
    for s in styles:
        enhanced = build_tattoo_prompt(payload.prompt, s, None,
                                        "blackgrey" if s in ("stencil","blackwork","realism") else "color")
        try:
            url = generate_image(enhanced, "1024x1024", "medium")
            results.append({"style": s, "image_url": url, "prompt_used": enhanced})
        except Exception as e:
            results.append({"style": s, "error": str(e)})
    variation_urls = [r["image_url"] for r in results if "image_url" in r]
    return {
        "success":   bool(variation_urls),
        "variations": variation_urls,
        "detailed":  results,
        "total":     len(results),
    }

@router.post("/vectorize")
async def vectorize_tattoo(payload: VectorizeRequest):
    """Return a GPT-4o vector production guide for the design."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    desc = payload.description or "the provided tattoo design"
    vector_prompt = (
        f"You are a professional tattoo artist and vector designer.\n"
        f"Analyze: {desc}\n\n"
        f"Provide a concise technical guide:\n"
        f"1. Main vector shapes and paths\n"
        f"2. Color palette (max 6 hex codes)\n"
        f"3. Line weights (outer vs detail)\n"
        f"4. Layer order\n"
        f"5. DTF/stencil print notes\n"
        f"6. Refined image generation prompt optimized for clean vector output\n\n"
        f"Output format: {(payload.output_format or 'SVG').upper()}. Be specific and production-ready."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": vector_prompt}],
        max_tokens=800, temperature=0.2,
    )
    return {
        "success":      True,
        "vector_guide": resp.choices[0].message.content,
        "description":  desc,
        "output_format":payload.output_format,
        "type":         "vector_analysis",
    }

@router.post("/upscale")
async def upscale_tattoo(payload: UpscaleRequest):
    """Re-generate at higher quality for print production."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    enhanced = build_tattoo_prompt(payload.prompt, payload.original_style, None, "color")
    enhanced += ". Maximum detail, print-production ready, professional quality."
    image_url = generate_image(enhanced, payload.size or "1536x1024", "high")
    return {"success": True, "image_url": image_url, "size": payload.size, "type": "upscaled"}

@router.get("/styles")
async def list_styles():
    """All available tattoo styles, placements, color modes, and output formats."""
    return {
        "success":        True,
        "styles":         list(STYLE_PROMPTS.keys()),
        "placements":     list(PLACEMENT_CONTEXT.keys()),
        "color_modes":    ["color", "blackgrey", "blackwork"],
        "output_formats": ["concept", "stencil", "vector_guide"],
    }
