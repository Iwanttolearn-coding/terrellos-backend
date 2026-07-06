"""
/v1/bible/* — Bible reading with Pastor Mills voice
Returns: scripture text + pastoral teaching + optional ElevenLabs audio
"""
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import os, httpx, base64
from openai import OpenAI

from bible_source import get_bible_versions, get_verse, get_chapter, resolve_version, BibleSourceError, ALLOWED_VERSIONS
from pastor_db import save_bible_study

router = APIRouter(prefix="/v1/bible", tags=["Bible"])

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID= os.getenv("ELEVENLABS_VOICE_ID", "nPczCjzI2devNBz1zQrb")
ELEVENLABS_MODEL   = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
ELEVENLABS_BASE    = "https://api.elevenlabs.io/v1"

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

PASTOR_SYSTEM = """You are Pastor Mills — a warm, biblical, Spirit-filled teaching pastor. 
You speak naturally like a real pastor teaching a real person. Never be vague or generic.
Give scripture-rich, deep, practical answers. Use real Bible references. Explain passages in plain language.
Speak with warmth, authority, and pastoral care."""

class BibleReadRequest(BaseModel):
    book:        str
    chapter:     Optional[int] = 1
    verse_start: Optional[int] = None
    verse_end:   Optional[int] = None
    translation: Optional[str] = "NIV"
    language:    Optional[str] = "English"
    voice:       Optional[bool] = True

async def _elevenlabs_speak(text: str) -> Optional[str]:
    """Returns base64 audio or None."""
    if not ELEVENLABS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=45) as h:
            r = await h.post(
                f"{ELEVENLABS_BASE}/text-to-speech/{ELEVENLABS_VOICE_ID}",
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                json={
                    "text": text[:4500],
                    "model_id": ELEVENLABS_MODEL,
                    "voice_settings": {
                        "stability": 0.35,
                        "similarity_boost": 0.85,
                        "style": 0.45,
                        "use_speaker_boost": True
                    }
                },
            )
        if r.status_code == 200 and r.content:
            return base64.b64encode(r.content).decode()
    except Exception:
        pass
    return None

@router.post("/read")
async def read_bible(req: BibleReadRequest, request: Request):
    """Bible Reader with Pastor Mills voice.

    Grounds scripture text in the REAL public-domain source (bible_source.py /
    the wldeh CDN) rather than letting the AI recall/paraphrase verse text from
    memory -- this is required for copyright safety since translations like
    NIV, ESV, NLT, NASB, MSG, AMP, TPT, CSB are all still under active license.

    UX-wise, the user's chosen translation label (e.g. "MSG", "AMP") is kept
    and echoed back for display and used to flavor the AI's teaching *style*
    only -- the actual quoted scripture text always comes from a verified
    public-domain source (KJV/ASV-family), never invented or paraphrased to
    imitate a copyrighted translation's wording.
    """
    from routers.pastor import _require_auth_and_usage
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    if not client:
        return {"success": False, "error": "OpenAI not configured"}

    display_version = req.translation or "NIV"
    real_version = resolve_version(req.translation)

    verse_ref = f"{req.book} {req.chapter}"
    if req.verse_start:
        verse_ref += f":{req.verse_start}"
        if req.verse_end:
            verse_ref += f"-{req.verse_end}"

    # 1) Fetch the REAL, public-domain scripture text first -- this is the
    # scripture of record. Never generated/guessed by the model.
    scripture_text = ""
    fetch_error = None
    try:
        if req.verse_start and not req.verse_end:
            data = await get_verse(real_version, req.book, req.chapter, req.verse_start)
            scripture_text = data["text"]
        else:
            chapter_data = await get_chapter(real_version, req.book, req.chapter)
            verses = chapter_data["verses"]
            if req.verse_start:
                vs, ve = req.verse_start, req.verse_end or req.verse_start
                verses = [v for v in verses if v["verse"] and vs <= int(v["verse"]) <= ve]
            if verses:
                scripture_text = "\n".join(f"{v['verse']}. {v['text']}" for v in verses)
            else:
                scripture_text = chapter_data.get("full_text", "")
    except BibleSourceError as e:
        fetch_error = e.message
    except Exception as e:
        fetch_error = str(e)

    if not scripture_text:
        return {
            "success": False,
            "error": fetch_error or f"Could not retrieve real scripture text for {verse_ref}. Please check the book/chapter/verse and try again.",
        }

    # 2) Generate the teaching, grounded in that real text. The requested
    # translation label only shapes tone/voice -- it never invents wording.
    prompt = f"""You are given the ACTUAL scripture text below -- a real quotation from a
verified public-domain translation, not your memory of any translation. Use ONLY this
text as the scripture of record; do not substitute or paraphrase it into a different
translation's wording (including {display_version}).

REFERENCE: {verse_ref}
TEXT:
{scripture_text}

Requested reading style/voice: {display_version} (use this only to inform tone -- e.g. more
conversational and modern if a paraphrase-style version was requested, more formal/literal if a
study translation was requested -- never to alter or invent the actual scripture wording above).

Now provide a TEACHING section: a deep, pastoral explanation of this passage as Pastor Mills. Include:
- Historical and cultural context
- Key word meanings
- The central message Pastor Mills wants the listener to take away
- At least 2 supporting scriptures from elsewhere in the Bible
- A practical application for daily life today
- A short closing prayer for the listener

Write as if Pastor Mills is sitting with the listener, having just read the passage aloud, and is
now explaining the Word. Warm, direct, biblical, never vague. Language: {req.language}."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PASTOR_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2200,
            temperature=0.7,
        )
        teaching = resp.choices[0].message.content.strip()
    except Exception:
        return {"success": False, "error": "Teaching generation failed. Please try again in a moment."}

    audio_base64 = None
    audio_error  = None
    if req.voice:
        speak_text = (scripture_text + "\n\n" + teaching)[:4500]
        audio_base64 = await _elevenlabs_speak(speak_text)
        if not audio_base64:
            audio_error = "ElevenLabs audio unavailable. Check ELEVENLABS_API_KEY."

    return {
        "success":       True,
        "reference":     verse_ref,
        "translation":   display_version,
        "source_version": real_version,
        "scriptureText": scripture_text,
        "teaching":      teaching,
        "audio_base64":  audio_base64,
        "audio_error":   audio_error,
        "voice_provider": "elevenlabs" if audio_base64 else None,
    }

@router.get("/health")
async def bible_health():
    return {
        "success": True,
        "openai": "configured" if OPENAI_API_KEY else "missing",
        "elevenlabs": "configured" if ELEVENLABS_API_KEY else "missing",
    }


# ══════════════════════════════════════════════════════════════════════════════
# REAL BIBLE TEXT — public-domain CDN source (wldeh/bible-api via jsdelivr)
# No AI-recalled/paraphrased scripture here — real verse/chapter text only,
# from versions confirmed PUBLIC DOMAIN (en-kjv, en-asv). This is intentionally
# separate from the older /v1/bible/read endpoint above, which still generates
# AI teaching text (not used as a scripture-of-record source).
# ══════════════════════════════════════════════════════════════════════════════

def _bible_source_error_to_http(e: "BibleSourceError"):
    status = 400
    if e.kind == "network_error":
        status = 502
    elif e.kind in ("invalid_book", "invalid_chapter", "invalid_verse", "invalid_version"):
        status = 404 if e.kind != "invalid_version" else 400
    raise HTTPException(status_code=status, detail={"success": False, "error_type": e.kind, "message": e.message})


@router.get("/versions")
async def bible_versions():
    """List supported, public-domain-safe Bible versions."""
    try:
        versions = await get_bible_versions()
        return {"success": True, "versions": versions}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"success": False, "error_type": "server_error", "message": str(e)})


@router.get("/verse")
async def bible_verse(
    version: str = Query(..., description="e.g. en-kjv, en-asv"),
    book: str = Query(..., description="e.g. Genesis, 1 Corinthians"),
    chapter: int = Query(...),
    verse: int = Query(...),
):
    """Fetch a single real verse's text from the public-domain Bible source."""
    try:
        result = await get_verse(version, book, chapter, verse)
        return {"success": True, **result}
    except BibleSourceError as e:
        _bible_source_error_to_http(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"success": False, "error_type": "server_error", "message": str(e)})


@router.get("/chapter")
async def bible_chapter(
    version: str = Query(..., description="e.g. en-kjv, en-asv"),
    book: str = Query(..., description="e.g. Genesis, 1 Corinthians"),
    chapter: int = Query(...),
):
    """Fetch a full real chapter's text from the public-domain Bible source."""
    try:
        result = await get_chapter(version, book, chapter)
        return {"success": True, **result}
    except BibleSourceError as e:
        _bible_source_error_to_http(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"success": False, "error_type": "server_error", "message": str(e)})


class BibleTeachRequest(BaseModel):
    reference:   str            # e.g. "John 1" or "Genesis 1:1"
    text:        str            # the REAL retrieved scripture text — grounds the AI, no guessing
    version:     Optional[str] = "en-kjv"
    audience:    Optional[str] = "adults"
    email:       Optional[str] = ""


@router.post("/teach")
async def bible_teach(req: BibleTeachRequest, request: Request):
    """Generate a teaching/study from a REAL retrieved passage (reference + text sent by the
    frontend after calling /verse or /chapter) rather than letting the AI guess scripture from
    memory. Saves the result the same way /v1/pastor/bible-study does."""
    from routers.pastor import _require_auth_and_usage, _email_from_request
    await _require_auth_and_usage(request, req.email or "")
    if not client:
        return {"success": False, "error": "OpenAI not configured"}

    prompt = f"""You are given the ACTUAL scripture text below — a real quotation, not your own memory of it.
Use ONLY this text as the scripture of record. Do not substitute a different translation's wording.

REFERENCE: {req.reference} ({ALLOWED_VERSIONS.get(req.version, req.version)})
TEXT:
{req.text}

Write a complete, church-ready teaching on this passage for a {req.audience} audience, including:
1. TOPIC OVERVIEW (2-3 paragraphs)
2. HISTORICAL BACKGROUND (author, audience, context)
3. VERSE-BY-VERSE COMMENTARY grounded in the exact text given above
4. THEOLOGICAL THEMES (2-3, each with cross-references)
5. LIFE APPLICATION (specific, practical)
6. DISCUSSION QUESTIONS (5-6)
7. CLOSING PRAYER

Do not invent scripture wording beyond what was given — quote it exactly when referencing it."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": PASTOR_SYSTEM}, {"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.65,
        )
        content = resp.choices[0].message.content.strip()
    except Exception:
        raise HTTPException(status_code=500, detail={"success": False, "message": "Teaching generation failed. Please try again."})

    uid = _email_from_request(request, req.email or "")
    saved_id = await save_bible_study(
        user_id=uid,
        title=f"Bible Reader: {req.reference}",
        content=content,
        passage=req.reference,
        version=req.version or "en-kjv",
        topic=req.reference,
    )
    return {
        "success": True,
        "reference": req.reference,
        "content": content,
        "word_count": len(content.split()),
        "saved_id": saved_id,
        "saved": bool(saved_id),
        "save_error": None if saved_id else "Teaching was generated but could not be saved to your account. Please copy it now and try saving again shortly.",
    }
