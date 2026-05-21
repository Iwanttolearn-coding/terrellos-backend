"""
/v1/pastor/* — Sermon, Bible study, theology, discipleship, church history
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
import os

router = APIRouter(prefix="/v1/pastor", tags=["Pastor AI"])
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def ai(prompt: str, max_tokens: int = 3500, model: str = "gpt-4o") -> str:
    if not client:
        return "OpenAI not configured. Please add OPENAI_API_KEY to backend secrets."
    system = """You are Pastor AI — a biblical scholar, seminary professor, and ordained pastor.
Always give detailed, scripturally grounded, pastorally warm responses.
Never give vague one-paragraph answers. Always include Scripture references, context, and practical application."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return resp.choices[0].message.content

class SermonRequest(BaseModel):
    scripture: Optional[str] = ""
    topic: Optional[str] = ""
    sermonType: Optional[str] = "expository"
    denomination: Optional[str] = ""
    audience: Optional[str] = ""
    duration: Optional[str] = "30 minutes"

class SimpleRequest(BaseModel):
    topic: Optional[str] = ""
    scripture: Optional[str] = ""
    name: Optional[str] = ""
    question: Optional[str] = ""
    denomination: Optional[str] = ""

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

@router.post("/sermon")
async def sermon(req: SermonRequest):
    ref = req.scripture or req.topic or "John 3:16"
    denom = req.denomination or "Non-denominational evangelical"
    audience = req.audience or "general congregation"
    duration = req.duration or "30 minutes"
    prompt = f"""Generate a COMPLETE, DETAILED sermon outline on: {ref}
Sermon type: {req.sermonType}
Denomination/tradition: {denom}
Target audience: {audience}
Approximate duration: {duration}

Return as structured JSON with these exact fields:
{{
  "title": "...",
  "subtitle": "...",
  "scripture": "...",
  "opening_hook": "A relatable story, illustration, or appropriate humor to open",
  "introduction": "Full introduction paragraph",
  "key_points": [
    {{"point": "...", "scripture": "...", "explanation": "...", "illustration": "..."}}
  ],
  "applications": ["practical application 1", "practical application 2", "practical application 3"],
  "altar_call": "Full altar call / invitation text",
  "closing_prayer": "Full closing prayer text",
  "small_group_questions": ["question 1", "question 2", "question 3", "question 4", "question 5"],
  "discipleship_challenge": "Weekly challenge for congregation",
  "additional_scriptures": ["verse 1", "verse 2"],
  "historical_context": "Brief historical/church context",
  "denominational_notes": "Any denomination-specific notes"
}}"""
    result = ai(prompt)
    return {"success": True, "content": result}

@router.post("/bible-study")
async def bible_study(req: SimpleRequest):
    ref = req.scripture or req.topic or "John 3:16"
    prompt = f"""Create a COMPREHENSIVE Bible study guide for: {ref}
Denomination context: {req.denomination or "broadly evangelical"}

Include ALL of the following sections:
1. TOPIC OVERVIEW — What this passage/topic is about
2. SCRIPTURE READING — The full passage text
3. HISTORICAL BACKGROUND — Time period, author, audience, cultural context
4. VERSE-BY-VERSE COMMENTARY — Detailed notes on each verse
5. THEOLOGICAL THEMES — Key doctrines and themes
6. DISCUSSION QUESTIONS — 6-8 open-ended questions for group discussion
7. FILL-IN-THE-BLANK — 5 completion questions with answers
8. MULTIPLE CHOICE — 5 questions with 4 options each, answer key
9. PERSONAL REFLECTION — Deep personal application prompt
10. PRAYER — Closing prayer for the study group
11. TEACHER NOTES — Tips for leading this study, common questions, pitfalls

Make it rich, detailed, and ready to use in a real church setting."""
    result = ai(prompt)
    return {"success": True, "content": result}

@router.post("/devotional")
async def devotional(req: SimpleRequest):
    topic_text = req.topic or req.scripture or "God's grace"
    prompt = f"""Write a COMPLETE daily devotional on: {topic_text}

Structure:
1. TITLE — Compelling devotional title
2. SCRIPTURE — Key verse (full text)
3. OPENING STORY — Brief relatable story or illustration (2-3 sentences)
4. REFLECTION — Deep reflection on the scripture and its meaning (3-4 paragraphs)
5. BIBLICAL CONTEXT — Brief historical/textual context
6. LIFE APPLICATION — Specific, practical ways to apply this today
7. CHALLENGE — One concrete action to take today
8. PRAYER — Full prayer (3-4 sentences)
9. ADDITIONAL READING — 2-3 related scriptures for further study

Write as if speaking directly to the reader. Be warm, personal, and encouraging."""
    result = ai(prompt)
    return {"success": True, "content": result}

@router.post("/martyr-study")
async def martyr_study(req: MartyrStudyRequest):
    result = ai(f"""Provide a detailed study of Christian martyr: {req.figure_name}
Include:
1. Historical background and life story
2. Faith journey and conversion
3. Persecution details and circumstances of martyrdom
4. Theological significance and what they died for
5. Impact on the early church
6. Legacy for modern Christians
7. Key quotes or writings (if any)
8. Discussion questions for study groups
9. Prayer of remembrance""")
    return {"success": True, "figure": req.figure_name, "content": result}

@router.post("/church-history")
async def church_history(req: BlackChristianHistoryRequest):
    query = f"{req.topic} {req.era} {req.region}".strip() or "African American Christian history"
    result = ai(f"""Provide detailed historical analysis of: {query}
Include:
1. Overview and significance
2. Key figures and their contributions
3. Historical timeline of major events
4. Theological contributions
5. Cultural and social impact
6. Connection to broader church history
7. Modern significance and legacy
8. Discussion questions
9. Recommended further reading""")
    return {"success": True, "content": result}

@router.post("/theology")
async def theology(req: SimpleRequest):
    result = ai(f"""Provide a THOROUGH theological analysis of: {req.topic or req.question}
Include:
1. Biblical foundation — key scriptures
2. Historical church perspective — how the church has understood this
3. Major theological positions (Calvinist, Arminian, Catholic, etc. where relevant)
4. Denominational variations
5. Practical Christian application
6. Common misconceptions or errors
7. Pastoral guidance""")
    return {"success": True, "content": result}

@router.post("/counseling")
async def pastoral_counseling(req: SimpleRequest):
    result = ai(f"""Provide pastoral counseling guidance for: {req.topic or req.question}
Include:
1. Empathetic acknowledgment of the situation
2. Scriptural foundation and comfort
3. Practical steps forward
4. When to refer to professional counseling (mental health, medical, legal)
5. Prayer support
6. Follow-up accountability suggestions
7. Church community resources to recommend

Always lead with compassion and Scripture. Never minimize real pain.""")
    return {"success": True, "content": result}

@router.post("/discipleship")
async def discipleship(req: SimpleRequest):
    result = ai(f"""Create a COMPLETE discipleship plan for: {req.topic or "new believers"}
Include:
1. Overview and discipleship goals
2. Week-by-week curriculum (4-6 weeks)
3. Scripture readings for each week
4. Accountability questions
5. Spiritual disciplines to practice
6. Memorization verses
7. Service/outreach component
8. Assessment questions
9. Graduation/completion next steps""")
    return {"success": True, "content": result}

@router.post("/history/search")
async def history_search(req: HistorySearchRequest):
    result = ai(f"""Research and provide detailed information about: {req.query}
Category: {req.category or "Christian history"}
Include historical context, key figures, significance, and modern relevance.""")
    return {"success": True, "content": result}
