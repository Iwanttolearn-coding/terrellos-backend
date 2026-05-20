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
    if not client: return "OpenAI not configured."
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a biblical scholar, seminary professor, and pastor with deep knowledge of Scripture, church history, theology, and pastoral ministry. Always produce thorough, scripturally grounded, pastorally warm content."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens, temperature=0.7,
    )
    return resp.choices[0].message.content

class SermonRequest(BaseModel):
    scripture: Optional[str] = ""
    topic: Optional[str] = ""
    sermonType: Optional[str] = "expository"
    denomination: Optional[str] = ""

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
    result = ai(f"Generate a complete, deep sermon on: {ref}. Type: {req.sermonType}. Denomination: {req.denomination or 'Non-denominational'}. Return as JSON with title, subtitle, scripture, introduction, keyPoints, applications, closingPrayer, smallGroupQuestions, discipleshipChallenge.")
    return {"success": True, "content": result}

@router.post("/bible-study")
async def bible_study(req: SimpleRequest):
    ref = req.scripture or req.topic or "John 3:16"
    result = ai(f"Create a comprehensive Bible study guide for: {ref}. Include background, key verses, discussion questions, application points, and prayer prompts.")
    return {"success": True, "content": result}

@router.post("/devotional")
async def devotional(req: SimpleRequest):
    topic_text = req.topic or req.scripture or "God's grace"
    result = ai(f"Write a daily devotional on: {topic_text}. Include scripture, reflection, prayer, and a challenge.")
    return {"success": True, "content": result}

@router.post("/martyr-study")
async def martyr_study(req: MartyrStudyRequest):
    result = ai(f"Provide a detailed study of Christian martyr: {req.figure_name}. Include historical context, faith story, persecution details, theological significance, and legacy for modern Christians.")
    return {"success": True, "figure": req.figure_name, "content": result}

@router.post("/church-history")
async def church_history(req: BlackChristianHistoryRequest):
    query = f"{req.topic} {req.era} {req.region}".strip() or "African American Christian history"
    result = ai(f"Provide detailed historical analysis of: {query}. Include key figures, theological contributions, cultural impact, and modern significance.")
    return {"success": True, "content": result}

@router.post("/theology")
async def theology(req: SimpleRequest):
    result = ai(f"Provide a thorough theological analysis of: {req.topic or req.question}. Cover biblical foundation, historical church perspective, denominational views, and practical application.")
    return {"success": True, "content": result}

@router.post("/counseling")
async def pastoral_counseling(req: SimpleRequest):
    result = ai(f"Provide pastoral counseling guidance for: {req.topic or req.question}. Ground response in Scripture, pastoral wisdom, and practical steps.")
    return {"success": True, "content": result}

@router.post("/discipleship")
async def discipleship(req: SimpleRequest):
    result = ai(f"Create a discipleship plan/study for: {req.topic or 'new believers'}. Include weekly modules, scripture readings, accountability questions, and spiritual disciplines.")
    return {"success": True, "content": result}

@router.post("/history/search")
async def history_search(req: HistorySearchRequest):
    result = ai(f"Research and provide detailed information about: {req.query}. Category: {req.category or 'general church history'}.")
    return {"success": True, "query": req.query, "content": result}
