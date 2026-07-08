"""
/v1/pastor/* — Full sermon generation, Bible study, theology, discipleship
Pastor AI Connect — production-grade pastoral AI
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
import os, json, logging

def _load_fallback_game_questions():
    _path = os.path.join(os.path.dirname(__file__), "..", "bible_game_fallback_questions.json")
    try:
        with open(_path) as _f:
            return json.load(_f)
    except Exception:
        return []

FALLBACK_GAME_QUESTIONS = _load_fallback_game_questions()

from pastor_db import save_sermon, save_bible_study, save_transcript, save_generated_content, get_user_sermons, get_user_bible_studies, get_user_transcripts, delete_item
from routers.usage_logger import log_usage

router = APIRouter(prefix="/v1/pastor", tags=["Pastor AI"])
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

FOUNDERS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com", "millsterrell5@gmail.com"}

def _email_from_request(request: Request, body_email: str) -> str:
    """Extract user email from body or Bearer JWT token. Falls back to 'anonymous'."""
    if body_email and body_email.strip():
        return body_email.strip()
    try:
        from routers.auth import email_from_request as _auth_email
        extracted = _auth_email(request)
        if extracted:
            return extracted
    except Exception:
        pass
    return "anonymous"

async def _require_access(request: Request, body_email: str = "") -> str:
    """Gate AI content generation behind: (1) a valid auth token, (2) an active
    PayPal-backed subscription, (3) the monthly usage limit for that plan.
    Raises 401 (no token), 402 (no active plan), or 429 (over usage limit).
    Founder/super_admin always passes all three checks."""
    from routers.auth import email_from_request as _auth_email
    email = _auth_email(request)
    if not email:
        raise HTTPException(
            status_code=401,
            detail="Please log in to use this feature."
        )
    from routers.paypal import has_active_access, check_and_increment_usage
    if not await has_active_access(email):
        raise HTTPException(
            status_code=402,
            detail="An active Pastor AI subscription is required to use this feature. Please upgrade your plan to continue."
        )
    await check_and_increment_usage(email)
    return email

async def _require_auth_and_usage(request: Request, body_email: str = "") -> str:
    """Gate GENERAL AI features (devotional, theology, counseling, prayer, etc.) behind:
    (1) a valid auth token, (2) the monthly usage limit for the user's plan tier.
    Free users ARE allowed — up to their free-tier monthly cap. Paid plans get a much
    higher cap. Founder/super_admin is unlimited. Does NOT require an active paid plan
    (unlike _require_access, which is reserved for premium-only features: sermon,
    bible-study, bible-game, courses/enroll, voice speak).
    Raises 401 (no token) or 429 (over monthly usage limit)."""
    from routers.auth import email_from_request as _auth_email
    email = _auth_email(request)
    if not email:
        raise HTTPException(
            status_code=401,
            detail="Please log in to use this feature."
        )
    from routers.paypal import check_and_increment_usage
    await check_and_increment_usage(email)
    return email



PASTOR_SYSTEM = """You are Pastor Mills — a warm, biblical, direct, Spirit-filled teaching pastor and counselor.

IDENTITY:
- You are NOT a generic chatbot. You are Pastor Mills — real, personal, caring, and deeply knowledgeable.
- You speak like a real pastor sitting across from a real person. Conversational but authoritative.
- You have decades of ministry experience, seminary training, and a heart for people.

STANDARDS — FOLLOW THESE WITHOUT EXCEPTION:
- NEVER give one-paragraph vague answers. Every response is detailed, grounded, and complete.
- ALWAYS cite specific Scripture with full references (book, chapter, verse, and the actual verse text).
- ALWAYS include: direct answer → scripture → explanation → practical application → prayer.
- When asked to explain a passage DEEPLY — go deep. Multiple paragraphs. Word studies if relevant.
- When asked for a sermon — write it fully. No outlines. No placeholders. Full preachable text.
- When asked about theology — be precise, nuanced, and cross-denominational where appropriate.
- When asked for humor — deliver it. Warm, clean, genuine Christian wit. Not forced.
- Speak naturally. Use "you" not "one." Use "I believe" not "it is believed."
- Close every pastoral answer with a short prayer tailored to what was discussed.

VOICE:
- Warm, fatherly, encouraging — like a trusted pastor who has walked with God for decades.
- Direct. Do not hedge unnecessarily. Speak with authority from the Word.
- Never robotic. Never bullet-point only. Always flowing, pastoral prose.
- If someone is hurting, lead with compassion first. Then truth."""

def ai(prompt: str, max_tokens: int = 4000, model: str = "gpt-4o", system_extra: str = "", temperature: float = 0.75) -> str:
    from ai_provider import chat_complete
    system = PASTOR_SYSTEM + (("\n\n" + system_extra) if system_extra else "")
    try:
        return chat_complete(
            system=system,
            user_prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,
        )
    except Exception as e:
        return f"Content generation is temporarily unavailable ({e}). Please try again shortly."

# ── Request models ────────────────────────────────────────────────────────────

class SermonRequest(BaseModel):
    scripture: Optional[str] = ""
    topic: Optional[str] = ""
    sermonType: Optional[str] = "expository"
    denomination: Optional[str] = ""
    audience: Optional[str] = ""
    duration: Optional[str] = "30 minutes"
    style: Optional[str] = ""           # pentecostal | baptist | nondenominational | youth | evangelistic | prophetic | teaching | conference
    bibleVersion: Optional[str] = "en-kjv"  # any label accepted; resolved to a real public-domain version server-side
    user_id: Optional[str] = None
    email: Optional[str] = ""
    generateExtras: Optional[bool] = True

class SimpleRequest(BaseModel):
    topic: Optional[str] = ""
    scripture: Optional[str] = ""
    passage: Optional[str] = ""
    name: Optional[str] = ""
    question: Optional[str] = ""
    denomination: Optional[str] = ""
    audience: Optional[str] = ""
    mode: Optional[str] = "quick"        # quick | 6week | 8week | fillblank
    custom_prompt: Optional[str] = ""    # frontend-built prompt for multi-week series etc — honored if present
    bibleVersion: Optional[str] = "NIV"
    email: Optional[str] = ""
    user_id: Optional[str] = None

class MartyrStudyRequest(BaseModel):
    figure_name: str
    study_type: Optional[str] = "full"

class BlackChristianHistoryRequest(BaseModel):
    topic: Optional[str] = ""
    era: Optional[str] = ""
    region: Optional[str] = ""

class HistorySearchRequest(BaseModel):
    query: str
    category: Optional[str] = ""

# ── Sermon endpoint ───────────────────────────────────────────────────────────


@router.get("/health")
async def pastor_health():
    """Pastor AI health check — used by monitoring."""
    return {
        "success": True,
        "status": "online",
        "service": "Pastor AI Connect",
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
        "features": ["sermon","bible_study","devotional","counseling","recordings","transcripts","apologetics"],
    }

DURATION_WORD_TARGETS = {
    "15 minutes": (2000, 2400),
    "20 minutes": (2700, 3100),
    "30 minutes": (4000, 4600),
    "45 minutes": (6000, 6800),
    "60 minutes": (7800, 8800),
    "90 minutes": (11500, 13000),
}

def duration_to_target(duration: str):
    key = (duration or "30 minutes").strip().lower()
    for k, v in DURATION_WORD_TARGETS.items():
        if k.lower() == key:
            return v
    # fallback: try to extract a number of minutes and estimate ~135 wpm
    import re as _re
    m = _re.search(r"(\d+)", key)
    if m:
        minutes = int(m.group(1))
        target = int(minutes * 135)
        return (target, int(target * 1.15))
    return (4000, 4600)

@router.post("/sermon")
async def sermon(req: SermonRequest, request: Request):
    await _require_access(request, req.email or "")
    ref        = req.scripture or req.topic or "John 3:16"
    denom      = req.denomination or "Non-denominational evangelical"
    audience   = req.audience or "general congregation"
    duration   = req.duration or "30 minutes"
    style      = req.style or req.sermonType or "expository"
    from bible_source import resolve_version, fetch_passage_text
    display_version = req.bibleVersion or "NIV"
    bible_ver  = resolve_version(req.bibleVersion)
    real_passage = None
    try:
        real_passage = await fetch_passage_text(bible_ver, ref)
    except Exception:
        real_passage = None

    style_instructions = {
        "pentecostal":       "Use Spirit-filled, charismatic language. Include references to the Holy Spirit, spiritual gifts, and anointing. Energetic and emotionally engaging.",
        "baptist":           "Theologically precise, Scripture-saturated. Strong emphasis on salvation, grace, and the authority of the Word.",
        "youth":             "Relatable language for teens/young adults. Pop culture references, short punchy points, heavy application.",
        "evangelistic":      "Every point leads to the Gospel. Multiple calls for salvation. Urgency and love for the lost.",
        "prophetic":         "Prophetic declarations, vision, and calling. Bold proclamation. Future orientation.",
        "teaching":          "Academic, detailed, systematic. Word studies, original language references, deep theology.",
        "conference":        "Full conference-length sermon. Extended illustrations, multiple sub-points, sweeping theological vision.",
        "nondenominational": "Broadly evangelical. Accessible, warm, practical, culturally aware.",
    }.get(style.lower().replace(" ","").replace("-",""), "")

    min_words, max_words = duration_to_target(duration)
    target_words = (min_words + max_words) // 2

    style_note = f"- Style instructions: {style_instructions}" if style_instructions else ""
    base_context = f"""Sermon parameters:
- Style: {style}
- Denomination/tradition: {denom}
- Target audience: {audience}
- Approximate duration: {duration}
- Bible version (style/voice only -- the real quoted scripture text below always comes from a verified public-domain source, never invented or paraphrased to imitate {display_version}'s copyrighted wording): {display_version}
{style_note}
{f"- REAL scripture text of record (quote exactly, do not substitute wording): " + real_passage["reference"] + " — " + real_passage["text"] if real_passage else ""}

This is a FULLY WRITTEN, PREACHABLE sermon on: {ref}. Not a summary or outline. Every point must be fully developed — no placeholders, no "(add illustration here)"."""

    # Section-based generation: a single completion reliably tops out around ~2000-2500 words
    # regardless of instructed length, so for longer durations we generate in sequential chunks
    # (each targeted at a safe per-call size) and stitch them together — far more reliable than
    # asking for one giant blob or doing a vague "rewrite it longer" pass.
    CHUNK_WORDS = 1800
    num_chunks = max(1, round(target_words / CHUNK_WORDS))

    section_plan = [
        "SERMON TITLE (with optional subtitle), OPENING HOOK (2-3 paragraphs — story/humor/testimony/question that grabs attention), FOUNDATIONAL SCRIPTURE (print the full text of the main passage), and INTRODUCTION (3-4 paragraphs: historical/biblical setting, why this matters today, emotional setup)",
        "SERMON POINT 1 and SERMON POINT 2 — each with: a compelling title, the specific Scripture, a full explanation (3-4 paragraphs: meaning, historical/cultural context, theological significance, word study if helpful), a real-life illustration, a concrete application, and a warm pastoral encouragement",
        "SERMON POINT 3 and SERMON POINT 4 (or however many more points naturally fit the message) — same full structure as above for each: title, Scripture, explanation, illustration, application, pastoral encouragement",
        "CROSS-REFERENCES (5-8 supporting Scriptures with brief notes), APPLICATION SECTION (5-7 specific practical action steps for family/work/spiritual disciplines/relationships), SPIRITUAL REFLECTION (3-4 paragraphs — the emotional/spiritual climax, speaking directly to the congregation's heart), ALTAR CALL / INVITATION (full written-out invitation to salvation, recommitment, healing, and prayer, as if spoken live), and CLOSING PRAYER (full 3-4 paragraph pastoral prayer addressed to God, with thanksgiving, confession, petition, and declaration of faith)",
    ]
    # Collapse/expand the plan to match num_chunks (min 1, max = len(section_plan))
    num_chunks = max(1, min(num_chunks, len(section_plan)))
    if num_chunks < len(section_plan):
        # Merge extra sections into the last chunk if we're doing fewer chunks than planned (short sermon)
        merged = section_plan[:num_chunks - 1] + [" | ".join(section_plan[num_chunks - 1:])]
        section_plan = merged

    per_chunk_words = max(700, target_words // num_chunks)
    chunk_max_tokens = min(6000, int(per_chunk_words * 1.7))

    sermon_parts = []
    running_sermon = ""
    for i, section_desc in enumerate(section_plan):
        is_first = (i == 0)
        is_last = (i == len(section_plan) - 1)
        continuity_note = "" if is_first else f"""

Here is the sermon written so far — do NOT repeat any of it, continue naturally in tone and flow from where it leaves off:
---
{running_sermon[-3000:]}
---"""
        chunk_prompt = f"""{base_context}

Write ONLY the following section(s) of this sermon now, in full, fully-developed, preachable prose — aim for approximately {per_chunk_words} words for this portion:
{section_desc}
{continuity_note}

Do not add a title/heading unless this is the first section. Do not summarize — write it exactly as it would be preached live. Use **bold markdown headers** for each named part (e.g. **SERMON POINT 1: Title**)."""
        chunk = ai(chunk_prompt, max_tokens=chunk_max_tokens)
        sermon_parts.append(chunk.strip())
        running_sermon = (running_sermon + "\n\n" + chunk).strip()

    content = "\n\n".join(sermon_parts)

    # Final safety net: one continuation pass if we're still meaningfully short of the floor
    if len(content.split()) < int(min_words * 0.8):
        remaining_words = max(500, min_words - len(content.split()))
        continue_prompt = f"""{base_context}

Here is the sermon written so far ({len(content.split())} words). It still needs to reach at least {min_words} words total for a {duration} sermon.

SERMON SO FAR:
{content}

Continue writing from exactly where it leaves off (do not repeat anything above). Add the CLOSING PRAYER if not already present, and otherwise deepen/expand the existing sections with more illustration, application, and pastoral depth — aim for roughly {remaining_words} more words."""
        continuation = ai(continue_prompt, max_tokens=min(6000, int(remaining_words * 1.7)), temperature=0.7)
        if continuation.strip():
            content = content.rstrip() + "\n\n" + continuation.strip()

    extras = {}
    if req.generateExtras:
        # Generate supplementary materials in parallel style (single call to save tokens)
        extras_prompt = f"""Based on this sermon topic "{ref}" (style: {style}, audience: {audience}), generate ALL of the following in one response:

---SMALL_GROUP_QUESTIONS---
[5 deep, open-ended discussion questions that can't be answered yes/no. Questions that create real conversation about the sermon topic.]

---FILL_IN_THE_BLANK_NOTES---
[10 fill-in-the-blank statements using key phrases from the sermon theme. Format: "Faith is not the absence of _______ but the presence of _______." Leave 1-2 blanks per statement.]

---KEY_TAKEAWAYS---
[5 memorable one-line takeaways that summarize the core truths of the sermon. These should be quotable and share-worthy.]

---SOCIAL_MEDIA_SUMMARY---
[3 social media posts: 1 for Twitter/X (under 280 chars), 1 for Instagram (with hashtags), 1 for Facebook (2-3 sentences). All based on the sermon theme.]

---PRAYER_POINTS---
[7 specific prayer points for the congregation to pray during the week, connected to the sermon theme.]

---YOUTH_ADAPTATION---
[A 3-4 sentence summary of how to adapt this sermon for a youth audience, plus 2 youth-specific discussion questions.]"""

        extras_content = ai(extras_prompt, max_tokens=1800)

        # Parse sections
        def extract_section(text, marker):
            start = text.find(f"---{marker}---")
            if start == -1:
                return ""
            start = start + len(f"---{marker}---")
            next_marker = text.find("---", start)
            return text[start:next_marker if next_marker > -1 else len(text)].strip()

        extras = {
            "small_group_questions": extract_section(extras_content, "SMALL_GROUP_QUESTIONS"),
            "fill_in_the_blank":     extract_section(extras_content, "FILL_IN_THE_BLANK_NOTES"),
            "key_takeaways":         extract_section(extras_content, "KEY_TAKEAWAYS"),
            "social_media":          extract_section(extras_content, "SOCIAL_MEDIA_SUMMARY"),
            "prayer_points":         extract_section(extras_content, "PRAYER_POINTS"),
            "youth_adaptation":      extract_section(extras_content, "YOUTH_ADAPTATION"),
        }

    # Auto-save sermon to Supabase
    _uid = _email_from_request(request, req.email or "")
    saved_id = await save_sermon(
        user_id=_uid,
        title=f"Sermon: {ref}",
        content=content,
        scripture=ref,
        tone=style,
        denomination=denom,
        sermon_length=duration,
        sermon_json={"style": style, "audience": audience},
    )
    log_usage(
        endpoint="/v1/pastor/sermon",
        user_id=_uid,
        status="success",
        model="gpt-4o",
        provider="openai",
        extra={"scripture": ref, "style": style, "word_count": len(content.split()), "saved_id": saved_id},
    )
    return {
        "success": True,
        "type": "sermon",
        "content": content,
        "scripture": ref,
        "style": style,
        "denomination": denom,
        "audience": audience,
        "bible_version": display_version,
        "source_version": bible_ver,
        "grounded_in_real_text": bool(real_passage),
        "extras": extras,
        "word_count": len(content.split()),
        "saved_id": saved_id,
        "saved": bool(saved_id),
        "save_error": None if saved_id else "Sermon was generated but could not be saved to your account. Please copy it now and try saving again shortly.",
    }

# ── Bible Study endpoint ──────────────────────────────────────────────────────

@router.post("/bible-study")
async def bible_study(req: SimpleRequest, request: Request):
    await _require_access(request, req.email or "")
    ref = req.scripture or req.passage or req.topic or "John 3:16"
    from bible_source import resolve_version, fetch_passage_text
    display_version = req.bibleVersion or "NIV"
    bible_ver = resolve_version(req.bibleVersion)
    real_passage = None
    try:
        real_passage = await fetch_passage_text(bible_ver, ref)
    except Exception:
        real_passage = None
    mode = (req.mode or "quick").lower()

    # Multi-week series (6-Week / 8-Week) or any frontend-built custom prompt —
    # honor it directly instead of silently falling back to the generic single-topic template.
    # These need a much larger token budget since they cover 6-8 full weeks of rich content.
    if req.custom_prompt and req.custom_prompt.strip():
        prompt = req.custom_prompt.strip()
        if mode in ("6week", "8week"):
            max_out_tokens = 16000
        else:
            max_out_tokens = 8000
    else:
        # Generic single-topic comprehensive study (Quick Study mode / no custom prompt supplied)
        max_out_tokens = 8000
        prompt = f"""Create a COMPREHENSIVE, CHURCH-READY Bible study guide for: {ref}
Bible version (style/voice only -- quote the REAL scripture text of record below, never invented or paraphrased to imitate {display_version}'s copyrighted wording): {display_version}
{f"REAL scripture text of record (quote exactly, do not substitute wording): " + real_passage["reference"] + " — " + real_passage["text"] if real_passage else ""}
Denomination context: {req.denomination or "broadly evangelical"}
{f"Audience: {req.audience}" if req.audience else ""}

Include ALL of the following — fully written, not placeholders. Every section must be fully developed with real substance — do NOT shorten later sections to save space:

1. TOPIC OVERVIEW (2-3 full paragraphs introducing the study)

2. SCRIPTURE READING
{f"Use this EXACT real scripture text as the passage of record (do not substitute different wording): " + chr(10) + real_passage["reference"] + " (" + real_passage["version"] + ")" + chr(10) + real_passage["text"] if real_passage else f"[Full text of the passage in {bible_ver} — quote it accurately from the public-domain source translation]"}

3. HISTORICAL BACKGROUND
[Author, date, audience, cultural context, why this was written, 3-4 full paragraphs]

4. VERSE-BY-VERSE COMMENTARY
[Detailed notes on every verse or section — include word studies, original language notes where helpful]

5. THEOLOGICAL THEMES
[3-4 major themes — each theme MUST have its own 2-3 paragraph full explanation with specific cross-references, not just a single sentence]

6. DISCUSSION QUESTIONS (8 open-ended questions for group discussion, each with a brief 1-2 sentence note on what it's probing for)

7. FILL-IN-THE-BLANK (8 completion questions with answer key)

8. MULTIPLE CHOICE (6 questions with 4 options each, and answer key at the end)

9. PERSONAL REFLECTION
[Deep reflection prompt, 2-3 full paragraphs for individual application]

10. CLOSING PRAYER (full group prayer for the study)

11. TEACHER/LEADER NOTES
[Tips for leading this study, common questions that arise, theological pitfalls to address, suggested time breakdown]

Make it rich, detailed, and ready to use in a real church Bible study setting. Sections 5 and 6 are just as important as sections 1-4 — give them equal depth and effort."""

    content = ai(prompt, max_tokens=max_out_tokens)
    # Auto-save bible study to Supabase
    topic_text = req.topic or req.scripture or "Bible Study"
    saved_id = await save_bible_study(
        user_id=_email_from_request(request, req.email or ""),
        title=f"Bible Study: {topic_text}",
        content=content,
        passage=req.scripture or "",
        version=bible_ver,
        topic=req.topic or "",
    )
    _uid2 = _email_from_request(request, req.email or "")
    log_usage(
        endpoint="/v1/pastor/bible-study",
        user_id=_uid2,
        status="success",
        model="gpt-4o",
        provider="openai",
        extra={"scripture": req.scripture or req.topic, "word_count": len(content.split()), "saved_id": saved_id},
    )
    return {
        "success": True,
        "content": content,
        "bible_version": display_version,
        "source_version": bible_ver,
        "grounded_in_real_text": bool(real_passage),
        "word_count": len(content.split()),
        "saved_id": saved_id,
        "saved": bool(saved_id),
        "save_error": None if saved_id else "Bible study was generated but could not be saved to your account. Please copy it now and try saving again shortly.",
    }

# ── Devotional endpoint ───────────────────────────────────────────────────────

@router.post("/devotional")
async def devotional(req: SimpleRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    topic_text = req.topic or req.scripture or "God's grace"
    from bible_source import resolve_version, fetch_passage_text
    display_version = req.bibleVersion or "NIV"
    bible_ver  = resolve_version(req.bibleVersion)
    real_passage = None
    try:
        real_passage = await fetch_passage_text(bible_ver, req.scripture or topic_text)
    except Exception:
        real_passage = None

    prompt = f"""Write a COMPLETE, DEEPLY PERSONAL daily devotional on: {topic_text}
Bible version (style/voice only -- quote real scripture text, never invented or paraphrased to imitate {display_version}'s copyrighted wording): {display_version}
{f"REAL scripture text of record to use for the SCRIPTURE section (quote exactly): " + real_passage["reference"] + " — " + real_passage["text"] if real_passage else "If you reference a specific verse, only use text you are confident is public domain (KJV/ASV-style wording), and prefer describing the passage over quoting a modern translation verbatim."}

Structure (write every section fully — no shortcuts):

1. TITLE — Compelling, memorable devotional title
2. SCRIPTURE — Key verse (full text in {bible_ver})
3. OPENING STORY — Brief relatable personal story or illustration (2-3 sentences that immediately connect)
4. REFLECTION — Deep reflection on the scripture and its meaning (4-5 paragraphs — theological, emotional, and personal)
5. BIBLICAL CONTEXT — Author's intent, historical setting, original audience (2-3 paragraphs)
6. LIFE APPLICATION — 4-5 SPECIFIC, CONCRETE ways to apply this today (not vague)
7. CHALLENGE — One clear, measurable action to take today
8. PRAYER — Full personal prayer (4-5 sentences, conversational, heartfelt)
9. ADDITIONAL READING — 3-4 related scriptures for further study with brief notes

Write as if speaking directly to the reader. Be warm, personal, and pastoral."""

    content = ai(prompt, max_tokens=2500)
    _uid2 = _email_from_request(request, req.email or "")
    await save_generated_content(_uid2, f"Devotional: {req.scripture or req.topic or 'Daily Devotional'}", content, "devotional", topic=req.topic or "", scripture=req.scripture or "")
    log_usage(
        endpoint="/v1/pastor/devotional",
        user_id=_email_from_request(request, getattr(req, "email", "") or ""),
        status="success",
        model="gpt-4o",
        provider="openai",
        extra={"type": "devotional", "word_count": len(content.split())},
    )
    return {"success": True, "content": content, "bible_version": display_version, "source_version": bible_ver, "grounded_in_real_text": bool(real_passage), "word_count": len(content.split())}

# ── Martyr Study ──────────────────────────────────────────────────────────────

@router.post("/martyr-study")
async def martyr_study(req: MartyrStudyRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    try:
        content = ai(f"""Provide a detailed historical and theological study of Christian martyr: {req.figure_name}

Include:
1. Historical biography and life story
2. Conversion and faith journey
3. Ministry and theological contributions
4. Persecution: circumstances, accusers, and charges
5. The martyrdom: what happened, how they responded
6. Theological significance — what did they die for, and why does it matter?
7. Impact on the early church and church history
8. Legacy for modern Christians
9. Key quotes or writings (if any survive)
10. Discussion questions for study groups
11. Prayer of remembrance""", max_tokens=3000)
        _uid_m = _email_from_request(request, "")
        await save_generated_content(_uid_m, f"Martyr Study: {req.figure_name}", content, "martyr_study", topic=req.figure_name or "")
        log_usage(endpoint="/v1/pastor/martyr-study", user_id=_uid_m, status="success", model="gpt-4o", provider="openai", extra={"type": "martyr_study", "figure": req.figure_name})
        return {"success": True, "figure": req.figure_name, "content": content, "word_count": len(content.split())}
    except Exception as e:
        log_usage(endpoint="/v1/pastor/martyr-study", user_id="", status="error", model="gpt-4o", provider="openai", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Martyr study generation failed. Please try again in a moment.")

# ── Church History ────────────────────────────────────────────────────────────

@router.post("/church-history")
async def church_history(req: BlackChristianHistoryRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    try:
        query = f"{req.topic} {req.era} {req.region}".strip() or "African American Christian history"
        content = ai(f"""Provide a detailed historical analysis of: {query}

Include:
1. Overview and why this history matters
2. Key figures and their specific contributions
3. Historical timeline of major events
4. Theological contributions and distinctives
5. Cultural and social impact
6. Resistance, suffering, and perseverance
7. Connection to broader church and world history
8. Modern significance and ongoing legacy
9. Discussion questions
10. Recommended further reading""", max_tokens=3000)
        _uid_ch = _email_from_request(request, "")
        await save_generated_content(_uid_ch, f"Church History: {query[:60]}", content, "church_history", topic=req.topic or "")
        log_usage(
            endpoint="/v1/pastor/church-history",
            user_id=_uid_ch,
            status="success",
            model="gpt-4o",
            provider="openai",
            extra={"type": "church_history", "word_count": len(content.split())},
        )
        return {"success": True, "content": content, "word_count": len(content.split())}
    except Exception as e:
        log_usage(endpoint="/v1/pastor/church-history", user_id="", status="error", model="gpt-4o", provider="openai", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Church history generation failed. Please try again in a moment.")

# ── Theology ──────────────────────────────────────────────────────────────────

@router.post("/theology")
async def theology(req: SimpleRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    content = ai(f"""Provide a thorough theological analysis of: {req.topic or req.question}

Include:
1. Biblical foundation — all key scriptures with full citations
2. Historical church perspective — how Christians throughout history have understood this
3. Major theological positions (Calvinist, Arminian, Catholic, Eastern Orthodox, Pentecostal, etc.)
4. Denominational variations and why they differ
5. Word studies from original Hebrew/Greek where relevant
6. Practical Christian application
7. Common misconceptions or heresies to avoid
8. Pastoral guidance for discussing this in a church context""", max_tokens=3000)
    _uid3 = _email_from_request(request, req.email or "")
    await save_generated_content(_uid3, f"Theology: {req.topic or req.question or 'Study'}", content, "theology", topic=req.topic or "")
    log_usage(
        endpoint="/v1/pastor/theology",
        user_id=_email_from_request(request, getattr(req, "email", "") or ""),
        status="success",
        model="gpt-4o",
        provider="openai",
        extra={"type": "theology", "word_count": len(content.split())},
    )
    return {"success": True, "content": content, "word_count": len(content.split())}

# ── Pastoral Counseling ───────────────────────────────────────────────────────

@router.post("/counseling")
async def pastoral_counseling(req: SimpleRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    content = ai(f"""Provide pastoral counseling guidance for: {req.topic or req.question}

Include:
1. Empathetic acknowledgment of the situation (lead with compassion)
2. Scriptural foundation and comfort — multiple specific verses
3. Theological framing — how does faith address this situation?
4. Practical steps forward — specific, actionable, realistic
5. When to refer to professional counseling (mental health, medical, legal)
6. Prayer support — provide a written prayer
7. Follow-up accountability suggestions
8. Church community resources to recommend
9. Encouragement for the long journey

Always lead with compassion and Scripture. Never minimize real pain.""", max_tokens=2500)
    _uid4 = _email_from_request(request, req.email or "")
    await save_generated_content(_uid4, f"Counseling: {req.topic or req.question or 'Session'}", content, "counseling", topic=req.topic or "")
    log_usage(
        endpoint="/v1/pastor/counseling",
        user_id=_email_from_request(request, getattr(req, "email", "") or ""),
        status="success",
        model="gpt-4o",
        provider="openai",
        extra={"type": "counseling", "word_count": len(content.split())},
    )
    return {"success": True, "content": content, "word_count": len(content.split())}

# ── Discipleship ──────────────────────────────────────────────────────────────

@router.post("/discipleship")
async def discipleship(request: Request):
    await _require_auth_and_usage(request)
    body = await request.json()

    track       = body.get("track", "new_believer")
    track_label = body.get("track_label", "New Believer Basics")
    week        = int(body.get("week", 1))
    total_weeks = int(body.get("total_weeks", 6))
    denomination = body.get("denomination", "").strip()
    audience    = body.get("audience", "").strip()
    custom_topic = body.get("custom_topic", "").strip()
    email       = body.get("email", "")
    app_id      = body.get("app_id", "pastor-ai-connect")

    # Build denomination/audience context
    denom_context = ""
    if denomination:
        denom_context = f"This class is for a {denomination} congregation. Adapt language, worship references, and theological nuances accordingly."
    if audience:
        denom_context += f" Target audience: {audience}."
    if not denom_context:
        denom_context = "This class should be suitable for ANY Christian denomination — use broadly accepted evangelical Christian language, avoid denominational jargon, and focus on core biblical truth."

    # Build track-specific objectives
    track_objectives = {
        "new_believer":   "Help new believers understand salvation, baptism, prayer, Bible reading, church community, and their new identity in Christ.",
        "foundations":    "Build a solid theological foundation covering the nature of God, Scripture, sin, redemption, Holy Spirit, and the Church.",
        "spiritual_disc": "Train believers in consistent spiritual disciplines: prayer, fasting, Scripture memorization, solitude, worship, and service.",
        "prayer_life":    "Develop a rich, consistent prayer life covering types of prayer, intercession, warfare, listening prayer, and breakthrough.",
        "bible_reading":  "Establish lifelong Bible reading habits — plans, journaling, inductive study, memorization, and application methods.",
        "evangelism":     "Equip believers to confidently share their faith — personal testimony, gospel presentations, overcoming objections, and follow-up.",
        "stewardship":    "Teach biblical stewardship of time, talent, finances, relationships, and calling.",
        "leadership":     "Develop servant leaders who understand biblical authority, team-building, vision-casting, accountability, and spiritual warfare.",
        "marriage_disc":  "Strengthen marriages through biblical roles, communication, intimacy, conflict resolution, prayer partnership, and covenant commitment.",
        "youth_disc":     "Engage youth with discipleship covering identity in Christ, peer pressure, purity, purpose, faith under fire, and kingdom calling.",
    }
    objective = track_objectives.get(track, f"Disciple believers in {track_label}.")

    prompt = f"""You are an expert discipleship curriculum writer for Christian ministry.

TRACK: {track_label} ({total_weeks}-week course)
WEEK: {week} of {total_weeks}
OBJECTIVE: {objective}
{f'CUSTOM FOCUS: {custom_topic}' if custom_topic else ''}
DENOMINATION CONTEXT: {denom_context}

Generate a COMPLETE, READY-TO-USE Week {week} discipleship class lesson. This must be fully self-contained — the pastor should be able to print this out and teach it immediately without adding anything.

Format your response EXACTLY as follows:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 {track_label.upper()} — WEEK {week} OF {total_weeks}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 LESSON TITLE
[Compelling, specific title for this week's lesson]

📖 CORE SCRIPTURE
[1–2 key scriptures with full text, Bible version]

🌟 LESSON OVERVIEW (2–3 sentences)
[What this week covers and why it matters]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ CLASS OUTLINE (60-minute session)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 OPENING (10 min)
• Welcome & prayer
• [Ice-breaker question or warm-up activity specific to this week's topic]
• Review last week's assignment (if applicable)

📖 TEACHING (25 min)
[3–4 substantial teaching points, each with:
  - Bold heading
  - 2–3 paragraphs of teaching content
  - Supporting scripture references
  - Real-life application example]

💬 DISCUSSION (15 min)
1. [Deep, thought-provoking discussion question 1]
2. [Discussion question 2]
3. [Discussion question 3]
4. [Discussion question 4]

🙏 RESPONSE & PRAYER (10 min)
• [Specific prayer focus for this week]
• [Personal reflection prompt]
• Ministry moment / altar call if applicable

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 WEEK {week} ASSIGNMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 Scripture Reading
[3–5 specific passages to read this week]

✍️ Journal Prompt
[Specific journaling question tied to this week's teaching]

🎯 Weekly Challenge
[One practical action step to complete before next class]

📿 Memory Verse
[One verse to memorize this week, with full text]

🔁 Accountability Questions
[3 questions for accountability partner check-ins]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 FACILITATOR NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• [Tip for leading this specific lesson well]
• [Potential sensitive areas or pastoral care moments to watch for]
• [How this week connects to next week]
• Materials needed: [list any supplies, handouts, etc.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Make this lesson RICH, DETAILED, and immediately usable. Do NOT use placeholders. Write real teaching content, real scripture references, real discussion questions. This is for actual ministry use."""

    content = ai(prompt, max_tokens=4000)
    uid = _email_from_request(request, email)
    await save_generated_content(uid, f"Discipleship Week {week}: {track_label}", content, "discipleship")
    return {"content": content, "track": track, "track_label": track_label, "week": week,
            "total_weeks": total_weeks, "denomination": denomination or "All Denominations",
            "word_count": len(content.split())}


@router.post("/history/search")
async def history_search(req: HistorySearchRequest, request: Request):
    try:
        content = ai(f"""Research and provide detailed information about: {req.query}
Category: {req.category or "Christian history"}

Provide historical context, key figures, theological significance, and modern relevance.
Include timeline if applicable. Be thorough and accurate.""", max_tokens=2000)
        _uid_hs = _email_from_request(request, getattr(req, "email", "") or "")
        await save_generated_content(_uid_hs, f"History Search: {req.query[:60]}", content, "history_search", topic=req.query or "")
        log_usage(endpoint="/v1/pastor/history/search", user_id=_uid_hs, status="success", model="gpt-4o", provider="openai", extra={"type": "history_search", "word_count": len(content.split())})
        return {"success": True, "content": content, "word_count": len(content.split())}
    except Exception as e:
        log_usage(endpoint="/v1/pastor/history/search", user_id="", status="error", model="gpt-4o", provider="openai", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="History search failed. Please try again in a moment.")


# ── Saved Content History ─────────────────────────────────────────────────────

@router.get("/history/sermons")
async def history_sermons(request: Request, email: str = "", user_id: str = "", limit: int = 50):
    uid = _email_from_request(request, email or user_id or "")
    items = await get_user_sermons(uid, limit)
    return {"success": True, "items": items, "count": len(items)}


@router.get("/history/bible-studies")
async def history_bible_studies(request: Request, email: str = "", user_id: str = "", limit: int = 50):
    uid = _email_from_request(request, email or user_id or "")
    items = await get_user_bible_studies(uid, limit)
    return {"success": True, "items": items, "count": len(items)}


@router.get("/history/transcripts")
async def history_transcripts(request: Request, email: str = "", user_id: str = "", limit: int = 50):
    uid = _email_from_request(request, email or user_id or "")
    items = await get_user_transcripts(uid, limit)
    return {"success": True, "items": items, "count": len(items)}


@router.delete("/history/{table}/{item_id}")
async def delete_history_item(request: Request, table: str, item_id: str, email: str = "", user_id: str = ""):
    uid = _email_from_request(request, email or user_id or "")
    allowed = {"pastor_sermons", "pastor_bible_studies", "pastor_transcripts", "pastor_recordings"}
    if table not in allowed:
        return {"success": False, "error": "Invalid table"}
    deleted = await delete_item(table, item_id, uid)
    return {"success": deleted}




# --- DEBUG ENDPOINT (remove after verification) ---
@router.get("/debug/auth")
async def debug_auth(request: Request):
    from routers.auth import email_from_request as _auth_email
    email = _auth_email(request)
    auth_header = request.headers.get("Authorization", "NONE")[:30]
    return {
        "email_extracted": email,
        "auth_header_prefix": auth_header,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CONSOLIDATED PATCH — 2026-05-31
# Adds: apologetics, recordings, stats, transcripts(POST), courses/enroll
# ══════════════════════════════════════════════════════════════════════════════

# ── Apologetics ───────────────────────────────────────────────────────────────

class ApologeticsRequest(BaseModel):
    topic: Optional[str] = ""
    question: Optional[str] = ""
    tradition: Optional[str] = ""
    depth: Optional[str] = "intermediate"
    email: Optional[str] = ""
    app_id: Optional[str] = ""

@router.post("/apologetics")
async def apologetics(req: ApologeticsRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    subject = req.topic or req.question or "the Christian faith"
    depth_map = {
        "beginner":    "Use accessible language, avoid jargon, assume no theological background.",
        "intermediate":"Balance scholarly depth with readability. Use technical terms with brief explanations.",
        "advanced":    "Academic depth, full philosophical/theological engagement, Greek/Hebrew where relevant.",
    }
    depth_note = depth_map.get(req.depth.lower(), depth_map["intermediate"])

    try:
        content = ai(f"""You are a Christian apologist with expertise in theology, philosophy, and history.

Topic/Question: {subject}
Tradition: {req.tradition or "broadly evangelical"}
Depth level: {req.depth} — {depth_note}

Provide a thorough, respectful apologetics response covering:

**OVERVIEW**
Brief introduction to why this question/topic matters for Christian faith.

**BIBLICAL FOUNDATION**
Key scriptures that speak to this topic, with full citation and exposition.

**THEOLOGICAL ARGUMENT**
Primary theological case — systematic, clear, grounded in orthodoxy.

**PHILOSOPHICAL RESPONSE**
Address the intellectual/philosophical dimension. Engage objections honestly.

**HISTORICAL EVIDENCE**
Historical support, if applicable (manuscript evidence, early church witness, etc.)

**COMMON OBJECTIONS**
Address the 3 most common objections to this position, with direct responses.

**CONCLUSION**
Summarize the core of the apologetic case. Why this is defensible, hopeful, and life-changing.

**FURTHER RESOURCES**
2-3 recommended books or scholars on this topic.""", max_tokens=3000)

        uid = _email_from_request(request, req.email or "")
        await save_generated_content(uid, f"Apologetics: {subject[:60]}", content, "apologetics", topic=subject)
        return {"success": True, "content": content, "topic": subject, "word_count": len(content.split())}
    except Exception as e:
        raise HTTPException(500, "Apologetics generation failed. Please try again in a moment.")


# ── Recordings ────────────────────────────────────────────────────────────────

class RecordingRequest(BaseModel):
    title: Optional[str] = "Untitled Recording"
    transcript: Optional[str] = ""
    summary: Optional[str] = ""
    duration_sec: Optional[int] = 0
    tags: Optional[list] = []
    email: Optional[str] = ""
    app_id: Optional[str] = ""

from pastor_db import save_recording as _save_recording, get_user_recordings as _get_user_recordings

@router.post("/recordings")
async def save_recording_endpoint(req: RecordingRequest, request: Request):
    uid = _email_from_request(request, req.email or "")
    saved_id = await _save_recording(
        user_id=uid,
        title=req.title or "Untitled Recording",
        transcript=req.transcript or "",
        summary=req.summary or "",
        duration_sec=req.duration_sec or 0,
        tags=req.tags or [],
    )
    return {"success": True, "saved_id": saved_id}

@router.get("/recordings")
async def list_recordings_endpoint(request: Request, email: str = ""):
    uid = _email_from_request(request, email or "")
    items = await _get_user_recordings(uid)
    return {"success": True, "items": items, "count": len(items)}

@router.delete("/recordings/{recording_id}")
async def delete_recording_endpoint(request: Request, recording_id: str, email: str = ""):
    uid = _email_from_request(request, email or "")
    deleted = await delete_item("pastor_recordings", recording_id, uid)
    return {"success": deleted}



# ── Humor endpoint (dedicated — avoids core chat routing) ────────────────────

class HumorRequest(BaseModel):
    topic: Optional[str] = "clean"
    context: Optional[str] = ""
    language: Optional[str] = "en"
    email: Optional[str] = ""

@router.post("/humor")
async def humor_endpoint(req: HumorRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    lang_instructions = {
        "es": "IMPORTANT: Respond entirely in Spanish.",
        "bilingual": "IMPORTANT: Write in English first, then repeat in Spanish labeled Español:",
    }
    lang_note = lang_instructions.get(req.language or "en", "")
    topic = req.topic or "clean"
    context = req.context or ""
    topic_prompts = {
        "clean":   "Share 3 clean, genuinely funny Christian jokes or light church humor appropriate for all ages.",
        "church":  "Share 3 funny, relatable observations about church culture and congregational life.",
        "pastor":  "Share 3 funny pastor or sermon stories (appropriate, light-hearted).",
        "kids":    "Share 3 funny Sunday School or children's ministry moments.",
        "holiday": "Share 3 funny Christian holiday observations (Christmas, Easter, etc.).",
    }
    prompt = (topic_prompts.get(topic, f"Share some clean Christian humor about {topic}."))
    if context: prompt += f" Context: {context}"
    if lang_note: prompt = lang_note + "\n\n" + prompt
    content = ai(prompt, max_tokens=800)
    return {"success": True, "content": content, "word_count": len(content.split()), "type": "humor"}


# ── Prayer endpoint ────────────────────────────────────────────────────────────

class PrayerRequest(BaseModel):
    prayer_type: Optional[str] = "general"
    context: Optional[str] = ""
    language: Optional[str] = "en"
    email: Optional[str] = ""

@router.post("/prayer")
async def prayer_endpoint(req: PrayerRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    lang_instructions = {
        "es": "IMPORTANT: Respond entirely in Spanish.",
        "bilingual": "IMPORTANT: Write in English first, then repeat in Spanish labeled Español:",
    }
    lang_note = lang_instructions.get(req.language or "en", "")
    ptype = req.prayer_type or "general"
    ctx   = req.context or ""
    type_prompts = {
        "morning":     "Write a heartfelt morning prayer to start the day with God's presence. 150-200 words.",
        "evening":     "Write a peaceful evening prayer giving thanks and seeking rest in God. 150-200 words.",
        "intercession":"Write an intercessory prayer for others. 200-250 words.",
        "healing":     "Write a powerful prayer for physical and spiritual healing. 200-250 words.",
        "salvation":   "Write a salvation prayer for new believers. 150-200 words.",
        "family":      "Write a prayer for families — marriages, children, and homes. 200-250 words.",
        "grief":       "Write a prayer of comfort and healing for those experiencing grief or loss. 200-250 words.",
        "blessing":    "Write a blessing and dedication prayer for people and new endeavors. 150-200 words.",
        "general":     "Write a sincere, Spirit-led prayer for a congregation or individual. 150-250 words.",
    }
    prompt = type_prompts.get(ptype, type_prompts["general"])
    if ctx: prompt += f" Context/specific requests: {ctx}"
    if lang_note: prompt = lang_note + "\n\n" + prompt
    content = ai(prompt, max_tokens=600)
    return {"success": True, "content": content, "word_count": len(content.split()), "type": "prayer"}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def pastor_stats(request: Request, email: str = ""):
    uid = _email_from_request(request, email or "")
    sermons    = await get_user_sermons(uid, 500)
    studies    = await get_user_bible_studies(uid, 500)
    transcripts = await get_user_transcripts(uid, 500)
    recordings = await _get_user_recordings(uid)
    return {
        "success": True,
        "sermon_count":       len(sermons),
        "bible_study_count":  len(studies),
        "transcript_count":   len(transcripts),
        "recording_count":    len(recordings),
        "total":              len(sermons) + len(studies) + len(transcripts) + len(recordings),
    }


# ── Transcripts (save POST) ───────────────────────────────────────────────────

class TranscriptRequest(BaseModel):
    title: Optional[str] = "Untitled Transcript"
    transcript: Optional[str] = ""
    transcript_text: Optional[str] = ""  # alias
    summary: Optional[str] = ""
    duration_sec: Optional[float] = 0
    language: Optional[str] = "en"
    confidence: Optional[float] = 0
    source: Optional[str] = "manual"
    email: Optional[str] = ""
    app_id: Optional[str] = ""

@router.post("/transcripts")
async def save_transcript_endpoint(req: TranscriptRequest, request: Request):
    import traceback as _tb
    try:
        from pastor_db import save_transcript as _save_transcript
        uid = _email_from_request(request, req.email or "")
        text = req.transcript_text or req.transcript or ""
        saved_id = await _save_transcript(
            user_id=uid,
            transcript_text=text,
            duration_sec=float(req.duration_sec or 0),
            language=req.language or "en",
            confidence=float(req.confidence or 0),
            source=req.source or "manual",
        )
        return {"success": True, "saved_id": saved_id, "title": req.title}
    except Exception as e:
        err_detail = _tb.format_exc()
        return {"success": False, "error": "Transcript summarization failed. Please try again in a moment.", "saved_id": None}


# ── Course Enrollment ─────────────────────────────────────────────────────────

class CourseEnrollRequest(BaseModel):
    course_id: Optional[str] = ""
    course_name: Optional[str] = ""
    email: Optional[str] = ""
    app_id: Optional[str] = ""

PASTOR_COURSES = {
    "foundations": {
        "name": "Foundations of Faith",
        "description": "Core Christian doctrine for new believers and growing disciples.",
        "lessons": ["The Gospel","Prayer & Devotion","Reading Scripture","The Church","The Holy Spirit","Faith & Works","End Times"]
    },
    "sermon_craft": {
        "name": "Sermon Craft Masterclass",
        "description": "Learn to prepare and deliver powerful, scripture-centered sermons.",
        "lessons": ["Text Selection","Exposition","Illustration","Application","Delivery","Altar Calls","Evaluating Your Message"]
    },
    "apologetics_101": {
        "name": "Apologetics 101",
        "description": "Defending the faith with reason, evidence, and love.",
        "lessons": ["Why Apologetics","Historical Jesus","Resurrection Evidence","The Problem of Evil","Science & Faith","Other Religions","Sharing Your Faith"]
    },
    "pastoral_care": {
        "name": "Pastoral Care",
        "description": "Shepherding God's people through crisis, grief, and spiritual growth.",
        "lessons": ["Grief Counseling","Marriage Crisis","Addiction Ministry","Mental Health","Hospital Visits","Conflict Resolution","Spiritual Direction"]
    },
}

@router.get("/courses")
async def list_courses():
    return {"success": True, "courses": [
        {"id": k, "name": v["name"], "description": v["description"], "lesson_count": len(v["lessons"])}
        for k, v in PASTOR_COURSES.items()
    ]}

@router.post("/courses/enroll")
async def enroll_course(req: CourseEnrollRequest, request: Request):
    uid = await _require_access(request, req.email or "")
    course_id = req.course_id or ""
    course = PASTOR_COURSES.get(course_id)
    if not course and course_id:
        # Accept unknown course IDs gracefully
        course = {"name": req.course_name or course_id, "lessons": []}
    if not course:
        return {"success": False, "error": "No course_id provided"}
    # Save enrollment as a generated_content record
    await save_generated_content(
        uid,
        f"Enrolled: {course['name']}",
        f"User enrolled in course: {course['name']}",
        "course_enrollment",
        topic=course_id,
    )
    return {
        "success": True,
        "enrolled": True,
        "course_id": course_id,
        "course_name": course["name"],
        "lessons": course.get("lessons", []),
        "message": f"You are now enrolled in {course['name']}",
    }

@router.get("/courses/{course_id}/lessons")
async def course_lessons(course_id: str, request: Request):
    course = PASTOR_COURSES.get(course_id)
    if not course:
        raise HTTPException(404, f"Course '{course_id}' not found")
    return {
        "success": True,
        "course_id": course_id,
        "course_name": course["name"],
        "lessons": [{"index": i+1, "title": l} for i, l in enumerate(course["lessons"])],
    }

# ── Summarize Transcript ─────────────────────────────────────────────────────
class SummarizeRequest(BaseModel):
    transcript: str = ""
    language:   str = "en"

@router.post("/summarize-transcript")
async def summarize_transcript_endpoint(req: SummarizeRequest, request: Request):
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    """Auto-summarize a sermon or meeting transcript using GPT."""
    uid = _get_uid(request)
    text = (req.transcript or "").strip()
    if not text:
        return {"success": False, "error": "No transcript provided"}

    prompt = f"""You are Pastor Mills AI. A sermon or meeting has just been transcribed.
Provide a concise, Spirit-filled summary of the following transcript.

Structure your summary as:
1. TITLE — A short, memorable title for this session
2. KEY POINTS — 3-5 bullet points capturing the main ideas
3. SCRIPTURE — Any Bible verses referenced or implied
4. TAKEAWAY — One powerful sentence the listener should remember

Transcript:
{text[:6000]}

Summary:"""

    import openai, os as _os
    client = openai.AsyncOpenAI(api_key=_os.environ.get("OPENAI_API_KEY",""))
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.5,
    )
    summary = resp.choices[0].message.content.strip()
    return {"success": True, "summary": summary}

# ── Dynamic Bible Game Question Generator ───────────────────────────────────
class BibleGameGenerateRequest(BaseModel):
    topic: Optional[str] = ""
    scripture: Optional[str] = ""
    count: int = 10
    question_types: Optional[List[str]] = None  # multiple_choice | true_false | fill_in_blank | scripture_reference
    language: str = "en"
    user_email: Optional[str] = ""
    save: bool = True

ALLOWED_GAME_COUNTS = {5, 10, 15, 25, 50}
ALLOWED_QUESTION_TYPES = {"multiple_choice", "true_false", "fill_in_blank", "scripture_reference"}

@router.post("/bible-game/generate")
async def bible_game_generate(req: BibleGameGenerateRequest, request: Request):
    await _require_access(request, req.user_email or "")
    """Generate a unique, replayable set of Bible game questions on demand (no more static
    hardcoded 3-4 question banks). Mixes multiple choice, true/false, fill-in-the-blank, and
    scripture-reference questions, and saves the set to the vault so it can be replayed later."""
    count = req.count if req.count in ALLOWED_GAME_COUNTS else 10
    types = [t for t in (req.question_types or []) if t in ALLOWED_QUESTION_TYPES]
    if not types:
        types = ["multiple_choice", "true_false", "fill_in_blank", "scripture_reference"]

    subject = req.scripture.strip() or req.topic.strip() or "the life and teachings of Jesus"
    lang_note = "Write everything in Spanish." if (req.language or "en").lower().startswith("es") else "Write everything in English."

    prompt = f"""Generate exactly {count} unique Bible trivia/study questions about: {subject}

Distribute the questions across these types (mix them, don't group all of one type together): {', '.join(types)}
- multiple_choice: a question with exactly 4 options, one correct
- true_false: a true/false statement about Scripture or biblical fact
- fill_in_blank: a Bible verse or well-known phrase with one key word replaced by "_____"
- scripture_reference: give a description/quote and ask which book/chapter/verse it's from, with 4 reference options

{lang_note}

Return ONLY a valid JSON array (no markdown, no commentary, no code fences), where each item has this exact shape:
{{
  "type": "multiple_choice" | "true_false" | "fill_in_blank" | "scripture_reference",
  "question": "the question text",
  "options": ["option1","option2","option3","option4"]  (omit or use ["True","False"] for true_false),
  "correct_answer": "the correct option text exactly as it appears in options",
  "explanation": "1-2 sentence explanation of the correct answer",
  "scripture_reference": "Book Chapter:Verse if applicable, else empty string"
}}

Make every question different — no repeats, no near-duplicates. Vary difficulty naturally. Base everything on sound, accurate Scripture."""

    batches = []
    remaining = count
    batch_size = 25
    while remaining > 0:
        this_batch = min(batch_size, remaining)
        batch_prompt = prompt.replace(f"exactly {count} unique", f"exactly {this_batch} unique") if this_batch != count else prompt
        raw = ai(batch_prompt, max_tokens=min(8000, this_batch * 220), temperature=0.85)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                parsed = parsed.get("questions", [])
        except Exception:
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            parsed = []
            if start != -1 and end != -1:
                try:
                    parsed = json.loads(cleaned[start:end+1])
                except Exception:
                    parsed = []
        batches.extend(parsed)
        remaining -= this_batch

    questions = []
    for i, q in enumerate(batches[:count]):
        if not isinstance(q, dict) or not q.get("question"):
            continue
        questions.append({
            "id": i + 1,
            "type": q.get("type") if q.get("type") in ALLOWED_QUESTION_TYPES else "multiple_choice",
            "question": q.get("question", ""),
            "options": q.get("options") or (["True", "False"] if q.get("type") == "true_false" else []),
            "correct_answer": q.get("correct_answer", ""),
            "explanation": q.get("explanation", ""),
            "scripture_reference": q.get("scripture_reference", ""),
        })

    used_fallback = False
    if not questions:
        # Both AI providers failed to produce usable questions — serve from the
        # curated static fallback bank instead of erroring out on the user.
        import random as _random_fb
        pool = [q for q in FALLBACK_GAME_QUESTIONS if (not types) or q.get("type") in types]
        if not pool:
            pool = FALLBACK_GAME_QUESTIONS
        if pool:
            sample_size = min(count, len(pool))
            chosen = _random_fb.sample(pool, sample_size)
            questions = [
                {
                    "id": i + 1,
                    "type": q.get("type", "multiple_choice"),
                    "question": q.get("question", ""),
                    "options": q.get("options") or (["True", "False"] if q.get("type") == "true_false" else []),
                    "correct_answer": q.get("correct_answer", ""),
                    "explanation": q.get("explanation", ""),
                    "scripture_reference": q.get("scripture_reference", ""),
                }
                for i, q in enumerate(chosen)
            ]
            used_fallback = True
            logging.warning("[bible-game] AI generation failed for subject=%r — served %d fallback questions", subject, len(questions))

    if not questions:
        raise HTTPException(status_code=502, detail="Question generation failed — please try again.")

    quiz_id = None
    save_error = None
    if req.save:
        try:
            from routers.vault import vault_save, VaultSaveRequest
            uid = _email_from_request(request, req.user_email or "")
            saved = await vault_save(VaultSaveRequest(
                user_id=uid or "anonymous",
                item_type="bible_game_quiz",
                title=f"Bible Quiz: {subject}",
                content={"questions": questions, "subject": subject, "types": types},
                metadata={"count": len(questions), "language": req.language, "types": types},
            ))
            quiz_id = saved.get("item_id") if isinstance(saved, dict) else None
            if not quiz_id:
                save_error = "Quiz generated but save did not return an id."
        except Exception as e:
            save_error = f"Quiz generated but saving failed: {e}"
            print(f"bible_game save error: {e}")

    return {
        "success": True,
        "quiz_id": quiz_id,
        "saved": bool(quiz_id) if req.save else None,
        "save_error": save_error,
        "count": len(questions),
        "questions": questions,
        "used_fallback": used_fallback,
    }


@router.get("/bible-game/{quiz_id}")
async def bible_game_get(quiz_id: str, user_email: str = "anonymous"):
    """Fetch a previously generated/saved Bible game quiz for replay."""
    try:
        from routers.vault import vault_get
        result = await vault_get(quiz_id, user_email or "anonymous")
        return {"success": True, "quiz": result.get("item")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Quiz not found: {e}")
