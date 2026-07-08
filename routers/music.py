"""
/v1/music/* — Christian Music Studio (Pastor AI Connect)
Generates full song lyrics + chord charts (text only — no audio synthesis)
using the shared ai_provider fallback (OpenAI primary, Perplexity fallback),
the same pattern as pastor.py / word_study.py / bible.py. Every generation is
auto-logged to music_songs; the "Save to Music Vault" button flips is_saved=true.
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from ai_provider import chat_complete
from pastor_db import save_music_song, mark_music_song_saved, get_user_music_songs

logger = logging.getLogger("music")
router = APIRouter(prefix="/v1/music", tags=["Music Studio"])

MUSIC_SYSTEM = """You are a professional Christian songwriter and music theorist with deep
expertise across Gospel, CCM, Hymns, Christian Rock, Christian Country, Christian Rap/Hip-Hop,
and Worship/Anthem styles. You write complete, singable, theologically sound original songs —
never a copyrighted song's lyrics, always a new original composition inspired by the requested
style/mood/theme.

STANDARDS:
- Write a COMPLETE song: Intro (chord cue only) -> Verse(s) -> Pre-Chorus (if natural) -> Chorus ->
  Bridge (if requested) -> Final Chorus/Outro.
- Every section header includes the chord progression above the lyrics, in both standard chord
  names AND the Nashville Number System (e.g. "G - D - Em - C  (I - V - vi - IV)").
- Lyrics must be original, scripture-consistent, singable (natural syllable count/rhythm), and
  emotionally resonant with the requested mood and theme.
- If a reference songwriter/artist style is given, emulate their PHRASING, STRUCTURE, and VOCAL
  DELIVERY STYLE — never copy their actual lyrics or melody.
- Close with a one-line "Performance Note" describing feel/dynamics/instrumentation.
- Format in clean plain text with clear section headers (VERSE 1, CHORUS, BRIDGE, etc.)."""


class MusicGenerateRequest(BaseModel):
    prompt:      str
    style:       Optional[str] = ""
    style_label: Optional[str] = ""
    key:         Optional[str] = "G"
    mood:        Optional[str] = ""
    theme:       Optional[str] = ""
    tempo:       Optional[str] = ""
    songwriter:  Optional[str] = ""
    email:       Optional[str] = ""


@router.post("/generate")
async def generate_music(req: MusicGenerateRequest, request: Request):
    """Generate a complete original Christian song (lyrics + chord chart). Premium-gated,
    same as Sermon Generator / Bible Study Builder."""
    from routers.pastor import _require_access
    uid = await _require_access(request, req.email or "")

    try:
        song_text = chat_complete(
            system=MUSIC_SYSTEM,
            user_prompt=req.prompt,
            max_tokens=2500,
            temperature=0.85,
        )
    except Exception as e:
        logger.error("music generation failed: %s", e)
        raise HTTPException(status_code=500, detail={"success": False, "error": f"Song generation failed: {e}"})

    if not song_text or not song_text.strip():
        raise HTTPException(status_code=500, detail={"success": False, "error": "No song generated. Please try again."})

    title = f"{req.theme or 'Untitled'} ({req.style_label or req.style}) — Key of {req.key}"

    song_id = await save_music_song(
        user_id=uid,
        title=title,
        song_text=song_text,
        style=req.style or "",
        style_label=req.style_label or "",
        song_key=req.key or "",
        mood=req.mood or "",
        theme=req.theme or "",
        tempo=req.tempo or "",
        songwriter_ref=req.songwriter or "",
        is_saved=False,
    )

    return {
        "success": True,
        "song": song_text,
        "title": title,
        "song_id": song_id,
    }


class MusicSaveRequest(BaseModel):
    song_id: str
    email:   Optional[str] = ""


@router.post("/save")
async def save_music(req: MusicSaveRequest, request: Request):
    """Flip is_saved=true on a previously generated song — the 'Save to Music Vault' action."""
    from routers.pastor import _require_auth_and_usage
    uid = await _require_auth_and_usage(request, req.email or "")
    ok = await mark_music_song_saved(req.song_id, uid)
    if not ok:
        raise HTTPException(status_code=500, detail={"success": False, "error": "Could not save this song. Please try again."})
    return {"success": True}


@router.get("/history")
async def music_history(request: Request, saved_only: bool = True):
    """Fetch this user's saved songs (Music Vault). Matches the Content Vault history pattern."""
    from routers.auth import email_from_request as _auth_email
    email = _auth_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Please log in to view your Music Vault.")
    songs = await get_user_music_songs(email, saved_only=saved_only)
    return {"success": True, "songs": songs, "count": len(songs)}
