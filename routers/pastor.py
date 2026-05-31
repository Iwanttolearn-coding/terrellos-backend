"""
/v1/pastor/* — Full sermon generation, Bible study, theology, discipleship
Pastor AI Connect — production-grade pastoral AI
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
import os, json

from pastor_db import save_sermon, save_bible_study, save_transcript, get_user_sermons, get_user_bible_studies, get_user_transcripts, delete_item

router = APIRouter(prefix="/v1/pastor", tags=["Pastor AI"])
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

FOUNDERS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com"}

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



PASTOR_SYSTEM = """You are Pastor AI — a biblical scholar, seminary professor, ordained pastor, and Spirit-filled counselor.

STANDARDS:
- Never give shallow, generic, or one-paragraph responses.
- Ground every point in specific Scripture (book, chapter, verse, full citation).
- Write with pastoral warmth, theological precision, and practical wisdom.
- Each response must feel like it came from a real pastor who prepared deeply."""

def ai(prompt: str, max_tokens: int = 4000, model: str = "gpt-4o", system_extra: str = "") -> str:
    if not client:
        return "OpenAI not configured. Please add OPENAI_API_KEY to backend secrets."
    system = PASTOR_SYSTEM + (("\n\n" + system_extra) if system_extra else "")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=0.75,
    )
    return resp.choices[0].message.content.strip()

# ── Request models ────────────────────────────────────────────────────────────

class SermonRequest(BaseModel):
    scripture: Optional[str] = ""
    topic: Optional[str] = ""
    sermonType: Optional[str] = "expository"
    denomination: Optional[str] = ""
    audience: Optional[str] = ""
    duration: Optional[str] = "30 minutes"
    style: Optional[str] = ""           # pentecostal | baptist | nondenominational | youth | evangelistic | prophetic | teaching | conference
    bibleVersion: Optional[str] = "NIV"
    user_id: Optional[str] = None
    email: Optional[str] = ""
    generateExtras: Optional[bool] = True

class SimpleRequest(BaseModel):
    topic: Optional[str] = ""
    scripture: Optional[str] = ""
    name: Optional[str] = ""
    question: Optional[str] = ""
    denomination: Optional[str] = ""
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

@router.post("/sermon")
async def sermon(req: SermonRequest, request: Request):
    ref        = req.scripture or req.topic or "John 3:16"
    denom      = req.denomination or "Non-denominational evangelical"
    audience   = req.audience or "general congregation"
    duration   = req.duration or "30 minutes"
    style      = req.style or req.sermonType or "expository"
    bible_ver  = req.bibleVersion or "NIV"

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

    prompt = f"""Generate a COMPLETE, FULL-LENGTH, PRODUCTION-QUALITY sermon on: {ref}

Sermon parameters:
- Style: {style}
- Denomination/tradition: {denom}
- Target audience: {audience}
- Approximate duration: {duration}
- Bible version: {bible_ver}
{f"- Style instructions: {style_instructions}" if style_instructions else ""}

This is NOT a summary or outline. This is a FULLY WRITTEN, PREACHABLE sermon. Write every word as if this will be preached to a real congregation this Sunday. Every point must be fully developed — no placeholders, no "(add illustration here)".

REQUIRED STRUCTURE — do not skip any section:

**SERMON TITLE**
[Powerful, memorable title]
[Optional subtitle/tagline]

**OPENING HOOK**
[2-3 paragraphs: Start with a relatable story, Christian humor, surprising statistic, rhetorical question, or testimony that immediately captures attention and connects to the theme]

**FOUNDATIONAL SCRIPTURE**
[Print the FULL TEXT of the main passage in {bible_ver}]

**INTRODUCTION**
[3-4 paragraphs covering: historical/biblical setting of the passage, why this topic matters urgently today, what the congregation will discover, emotional/spiritual setup for the message]

**SERMON POINT 1: [Compelling Title]**
Scripture: [Specific verse]
[Full explanation — minimum 3-4 paragraphs with: what this verse means, historical/cultural context, theological significance, word study if helpful, how it connects to the main theme]
Real-life illustration: [Specific story, example, or analogy]
Application: [Concrete, specific ways to apply this point this week]
Pastoral encouragement: [Warm, personal pastoral note]

**SERMON POINT 2: [Compelling Title]**
[Same structure — full paragraphs, Scripture, illustration, application]

**SERMON POINT 3: [Compelling Title]**
[Same structure]

**SERMON POINT 4: [Compelling Title]**
[Same structure]

**SERMON POINT 5: [Compelling Title]**
[Same structure]

**SERMON POINT 6: [Compelling Title]** (include if message naturally supports it)
[Same structure]

**CROSS-REFERENCES**
[List 5-8 supporting Scriptures with brief notes on each one and how they reinforce the sermon]

**APPLICATION SECTION**
[How do we live this out? Give 5-7 SPECIFIC, PRACTICAL action steps — not vague suggestions. Family applications, work applications, spiritual disciplines, relationship applications]

**SPIRITUAL REFLECTION**
[3-4 paragraphs of conviction, encouragement, and challenge. This is the emotional/spiritual climax of the sermon. Speak directly to the congregation's heart. Address doubt, fear, struggle, and call them to deeper faith.]

**ALTAR CALL / INVITATION**
[Full, written-out altar call — include: invitation to salvation, invitation to recommitment, invitation to healing, invitation to prayer. Write this as if you are speaking it live. Warm, urgent, loving.]

**CLOSING PRAYER**
[Full pastoral prayer, 3-4 paragraphs, directly connected to the sermon theme. Address God directly. Include thanksgiving, confession, petition for the congregation, and declaration of faith.]"""

    content = ai(prompt, max_tokens=4000)

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
    return {
        "success": True,
        "content": content,
        "scripture": ref,
        "style": style,
        "denomination": denom,
        "audience": audience,
        "bible_version": bible_ver,
        "extras": extras,
        "word_count": len(content.split()),
        "saved_id": saved_id,
    }

# ── Bible Study endpoint ──────────────────────────────────────────────────────

@router.post("/bible-study")
async def bible_study(req: SimpleRequest, request: Request):
    ref = req.scripture or req.topic or "John 3:16"
    bible_ver = req.bibleVersion or "NIV"

    prompt = f"""Create a COMPREHENSIVE, CHURCH-READY Bible study guide for: {ref}
Bible version: {bible_ver}
Denomination context: {req.denomination or "broadly evangelical"}

Include ALL of the following — fully written, not placeholders:

1. TOPIC OVERVIEW (2-3 paragraphs introducing the study)

2. SCRIPTURE READING
[Full text of the passage in {bible_ver}]

3. HISTORICAL BACKGROUND
[Author, date, audience, cultural context, why this was written, 3-4 paragraphs]

4. VERSE-BY-VERSE COMMENTARY
[Detailed notes on every verse or section — include word studies, original language notes where helpful]

5. THEOLOGICAL THEMES
[3-4 major themes with full explanations and cross-references]

6. DISCUSSION QUESTIONS (8 open-ended questions for group discussion)

7. FILL-IN-THE-BLANK (8 completion questions with answer key)

8. MULTIPLE CHOICE (6 questions with 4 options each, and answer key at the end)

9. PERSONAL REFLECTION
[Deep reflection prompt, 2-3 paragraphs for individual application]

10. CLOSING PRAYER (full group prayer for the study)

11. TEACHER/LEADER NOTES
[Tips for leading this study, common questions that arise, theological pitfalls to address, suggested time breakdown]

Make it rich, detailed, and ready to use in a real church Bible study setting."""

    content = ai(prompt, max_tokens=4000)
    # Auto-save bible study to Supabase
    topic_text = req.topic or req.scripture or "Bible Study"
    saved_id = await save_bible_study(
        user_id=_email_from_request(request, req.email or ""),
        title=f"Bible Study: {topic_text}",
        content=content,
        passage=req.scripture or "",
        version=req.bibleVersion or "NIV",
        topic=req.topic or "",
    )
    return {"success": True, "content": content, "word_count": len(content.split()), "saved_id": saved_id}

# ── Devotional endpoint ───────────────────────────────────────────────────────

@router.post("/devotional")
async def devotional(req: SimpleRequest, request: Request):
    topic_text = req.topic or req.scripture or "God's grace"
    bible_ver  = req.bibleVersion or "NIV"

    prompt = f"""Write a COMPLETE, DEEPLY PERSONAL daily devotional on: {topic_text}
Bible version: {bible_ver}

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
    return {"success": True, "content": content, "word_count": len(content.split())}

# ── Martyr Study ──────────────────────────────────────────────────────────────

@router.post("/martyr-study")
async def martyr_study(req: MartyrStudyRequest):
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
    return {"success": True, "figure": req.figure_name, "content": content, "word_count": len(content.split())}

# ── Church History ────────────────────────────────────────────────────────────

@router.post("/church-history")
async def church_history(req: BlackChristianHistoryRequest):
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
    return {"success": True, "content": content, "word_count": len(content.split())}

# ── Theology ──────────────────────────────────────────────────────────────────

@router.post("/theology")
async def theology(req: SimpleRequest, request: Request):
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
    return {"success": True, "content": content, "word_count": len(content.split())}

# ── Pastoral Counseling ───────────────────────────────────────────────────────

@router.post("/counseling")
async def pastoral_counseling(req: SimpleRequest, request: Request):
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
    return {"success": True, "content": content, "word_count": len(content.split())}

# ── Discipleship ──────────────────────────────────────────────────────────────

@router.post("/discipleship")
async def discipleship(req: SimpleRequest, request: Request):
    content = ai(f"""Create a complete discipleship curriculum for: {req.topic or "new believers"}

Include:
1. Overview and discipleship goals
2. Week-by-week curriculum (6 weeks minimum)
   - Each week: theme, scripture, discussion questions, assignment, memory verse
3. Spiritual disciplines to practice throughout
4. Accountability questions for weekly check-ins
5. Recommended books/resources
6. Service/outreach component
7. Assessment questions for measuring growth
8. Graduation/completion next steps and celebration ideas""", max_tokens=3000)
    return {"success": True, "content": content, "word_count": len(content.split())}

# ── History Search ────────────────────────────────────────────────────────────

@router.post("/history/search")
async def history_search(req: HistorySearchRequest):
    content = ai(f"""Research and provide detailed information about: {req.query}
Category: {req.category or "Christian history"}

Provide historical context, key figures, theological significance, and modern relevance.
Include timeline if applicable. Be thorough and accurate.""", max_tokens=2000)
    return {"success": True, "content": content, "word_count": len(content.split())}


# ── Saved Content History ─────────────────────────────────────────────────────

@router.get("/history/sermons")
async def history_sermons(email: str = "", user_id: str = "anonymous", limit: int = 50):
    uid = email or user_id
    items = await get_user_sermons(uid, limit)
    return {"success": True, "items": items, "count": len(items)}


@router.get("/history/bible-studies")
async def history_bible_studies(email: str = "", user_id: str = "anonymous", limit: int = 50):
    uid = email or user_id
    items = await get_user_bible_studies(uid, limit)
    return {"success": True, "items": items, "count": len(items)}


@router.get("/history/transcripts")
async def history_transcripts(email: str = "", user_id: str = "anonymous", limit: int = 50):
    uid = email or user_id
    items = await get_user_transcripts(uid, limit)
    return {"success": True, "items": items, "count": len(items)}


@router.delete("/history/{table}/{item_id}")
async def delete_history_item(table: str, item_id: str, email: str = "", user_id: str = "anonymous"):
    uid = email or user_id
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
