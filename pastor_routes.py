"""
Pastor AI Connect — Backend Routes
/v1/pastor/* endpoints for sermon, theology, discipleship
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import os
from openai import OpenAI

router = APIRouter(prefix="/v1/pastor", tags=["Pastor AI"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def ai(prompt: str, max_tokens: int = 3500) -> str:
    if not client:
        return "OpenAI not configured — add OPENAI_API_KEY to environment variables."
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a biblical scholar, seminary professor, and pastor with deep knowledge of Scripture, church history, theology, and pastoral ministry. Always produce thorough, scripturally grounded, pastorally warm content."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=0.7
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

@router.post("/sermon")
async def generate_sermon(req: SermonRequest):
    ref = req.scripture or req.topic or "John 3:16"
    prompt = f"""Generate a COMPLETE, DEEP sermon on: {ref}
Sermon type: {req.sermonType}
Denomination context: {req.denomination or 'Non-denominational evangelical'}

Return a JSON object with ALL of these fields populated (never empty arrays):
{{
  "title": "compelling sermon title",
  "subtitle": "subtitle",
  "scripture": "primary scripture reference",
  "sermonType": "{req.sermonType}",
  "introduction": "5-6 paragraph introduction that hooks the congregation",
  "historicalContext": "3 paragraphs of historical and cultural background",
  "keyPoints": [
    {{"title": "point title", "content": "2 full paragraphs", "scripture": "supporting verse"}}
  ],
  "verseByVerse": "detailed verse-by-verse exposition",
  "applications": ["5+ practical life applications"],
  "apologetics": "address potential doubts or hard questions from this text",
  "discipleshipChallenge": "specific week-long discipleship challenge",
  "reflectionQuestions": ["5+ personal reflection questions"],
  "closingPrayer": "full written pastoral closing prayer",
  "altarCall": "evangelistic altar call text",
  "smallGroupQuestions": ["5+ small group discussion questions"],
  "youthSummary": "teen-friendly summary of the sermon",
  "childrenSummary": "child-friendly summary",
  "denominationalPerspectives": ["3+ different denominational views on this text"],
  "churchHistoryConnections": "how church fathers or historical figures addressed this text"
}}

RULES:
- keyPoints must have minimum 4 points
- Never return empty arrays
- introduction minimum 5 paragraphs
- closingPrayer must be a full written prayer
- smallGroupQuestions minimum 5
- Return ONLY valid JSON, no markdown"""
    import json
    try:
        raw = ai(prompt, 4000)
        raw = raw.strip()
        if raw.startswith("```"): raw = raw.split("\n",1)[1].rsplit("```",1)[0]
        return json.loads(raw)
    except Exception as e:
        return {
            "title": f"Sermon on {ref}",
            "subtitle": "A Biblical Exploration",
            "scripture": ref,
            "sermonType": req.sermonType,
            "introduction": "This sermon explores the profound truth found in our scripture passage. The Word of God speaks to us across centuries with living power. As we open our hearts to receive this message, may the Holy Spirit illuminate every word. This is not merely ancient text — it is the living, breathing Word of God for our lives today. Let us approach with reverence, expectation, and open hearts.",
            "historicalContext": "The historical background of this passage reveals the rich context in which God's Word was first spoken. Understanding the culture, geography, and circumstances of the original audience helps us grasp the full weight of what God was communicating. This context does not diminish the timeless nature of Scripture but rather enriches our understanding of its eternal message.",
            "keyPoints": [
                {{"title": "God's Sovereign Purpose", "content": "God works all things according to the counsel of His will. Nothing in this passage is accidental — every word carries divine intention and eternal significance.", "scripture": ref}},
                {{"title": "The Call to Faith", "content": "Faith is not passive agreement but active trust. This scripture calls us to step beyond our comfort zones into the promises of God.", "scripture": "Hebrews 11:1"}},
                {{"title": "Grace and Transformation", "content": "God's grace is not merely forgiveness — it is transforming power. This passage reveals how encountering God changes us from the inside out.", "scripture": "2 Corinthians 5:17"}},
                {{"title": "Living the Word", "content": "Scripture is not meant to stay on the page. This message carries a practical call to action that must reshape how we live Monday through Saturday.", "scripture": "James 1:22"}}
            ],
            "applications": ["Apply this truth in your daily prayer life", "Share this scripture with someone who needs encouragement this week", "Journal about how this passage speaks to your current season", "Memorize the key verse and meditate on it daily", "Find one way to serve others in light of this message"],
            "reflectionQuestions": ["What does this passage reveal about God's character?", "How does this scripture challenge your current thinking?", "What specific action does this message call you to take?", "How have you seen this truth at work in your life?", "What would change if you fully believed this promise?"],
            "closingPrayer": "Heavenly Father, we thank You for Your living Word that speaks to us today. As we leave this place, let the seeds of this message take deep root in our hearts. Give us courage to live what we have heard. May Your Spirit be our guide as we walk out these truths in the days ahead. In Jesus' name, Amen.",
            "altarCall": "If God has spoken to your heart today, we invite you to respond. You don't have to carry your burdens alone. Come as you are — Jesus receives you.",
            "smallGroupQuestions": ["How does this passage apply to your life right now?", "What was most challenging about this message?", "How can we pray for one another in light of this text?", "What steps will you take this week to live out this scripture?", "How does this passage deepen your understanding of God's love?"],
            "youthSummary": f"Today we talked about {ref} — basically God is reminding us that He is always with us and has a plan for our lives.",
            "childrenSummary": "God loves us so much and this story shows us how He always takes care of His children!",
            "denominationalPerspectives": ["Reformed tradition emphasizes God's sovereignty throughout this passage", "Wesleyan tradition highlights the role of human response and free will", "Pentecostal tradition focuses on the Spirit's active work in applying this truth"],
            "churchHistoryConnections": "The church fathers often cited this passage in their writings on salvation and Christian living.",
            "error": str(e)
        }

@router.post("/bible-study")
async def generate_bible_study(req: SimpleRequest):
    ref = req.scripture or req.topic or "Genesis 1"
    result = ai(f"Create a comprehensive Bible study on {ref}. Include: overview, historical context, verse-by-verse breakdown, key themes, application questions, prayer focus, and memory verse. Format as structured text.")
    return {"content": result, "scripture": ref, "type": "bible_study"}

@router.post("/discipleship")
async def generate_discipleship(req: SimpleRequest):
    topic = req.topic or "Foundations of Faith"
    result = ai(f"Create a complete discipleship lesson on: {topic}. Include: lesson overview, scripture foundation, teaching content (3-4 sections), discussion questions, practical exercises, reflection prompts, and next steps. Make it warm, practical, and spiritually deep.")
    return {"content": result, "topic": topic, "type": "discipleship"}

@router.post("/denomination")
async def generate_denomination(req: SimpleRequest):
    denom = req.name or req.topic or "Baptist"
    result = ai(f"Write a comprehensive study of the {denom} denomination. Include: history and founding, core beliefs, salvation doctrine, baptism and communion views, Holy Spirit doctrine, worship style, church government, end-times view, major theologians, key differences from other traditions, and recommended scriptures. Be accurate, respectful, and thorough.")
    return {"content": result, "denomination": denom, "type": "denomination_study"}

@router.post("/church-history")
async def generate_church_history(req: SimpleRequest):
    topic = req.topic or "Early Church"
    result = ai(f"Write a detailed church history study on: {topic}. Include timeline, key figures, theological developments, controversies, lasting impact on Christianity, and lessons for the modern church.")
    return {"content": result, "topic": topic, "type": "church_history"}

@router.post("/martyr")
async def generate_martyr(req: SimpleRequest):
    name = req.name or req.topic or "Polycarp"
    result = ai(f"Write a full profile of the Christian martyr {name}. Include: biography, historical setting, how they served God, their persecution and martyrdom, spiritual lessons, scripture connections, and sermon application points.")
    return {"content": result, "name": name, "type": "martyr_profile"}

@router.post("/christian-hero")
async def generate_christian_hero(req: SimpleRequest):
    name = req.name or req.topic or "Charles Spurgeon"
    result = ai(f"Write a comprehensive profile of Christian hero {name}. Include: what they did for God, historical impact, key teachings, notable works, controversies if any, doctrinal tradition, timeline, and how their life applies to Christians today.")
    return {"content": result, "name": name, "type": "christian_hero"}

@router.post("/apologetics")
async def generate_apologetics(req: SimpleRequest):
    question = req.question or req.topic or "How do we know the Bible is true?"
    result = ai(f"Provide a thorough Christian apologetics answer to: {question}. Include: direct answer, scriptural support, historical evidence, philosophical reasoning, common objections and responses, and how a believer can explain this to a skeptic.")
    return {"content": result, "question": question, "type": "apologetics"}

@router.post("/prayer")
async def generate_prayer(req: SimpleRequest):
    topic = req.topic or "daily guidance"
    result = ai(f"Write a deep, heartfelt pastoral prayer about: {topic}. Make it personal, scripturally grounded, and suitable for congregational use.")
    return {"content": result, "topic": topic, "type": "prayer"}

@router.post("/lesson-plan")
async def generate_lesson_plan(req: SimpleRequest):
    topic = req.topic or "Introduction to Prayer"
    result = ai(f"Create a complete lesson plan for a church class on: {topic}. Include: learning objectives, scripture references, teaching outline, discussion questions, activities, assessment, and homework.")
    return {"content": result, "topic": topic, "type": "lesson_plan"}
