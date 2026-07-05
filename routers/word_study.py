"""
routers/word_study.py — Pastor AI Connect
Word Studies in Hebrew, Greek, and Aramaic
Integrated into terrellos-backend.

Endpoints:
  POST /v1/word-study/analyze     — full word study for a biblical word/phrase
  POST /v1/word-study/passage     — word studies for every key word in a passage
  GET  /v1/word-study/languages   — list supported languages
"""

import os
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI

router = APIRouter(prefix="/v1/word-study", tags=["Word Study"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

WORD_STUDY_SYSTEM = """You are a world-class biblical scholar specializing in:
- Biblical Hebrew (Old Testament / Tanakh)
- Koine Greek (New Testament)  
- Biblical Aramaic (Daniel, Ezra, portions of Nehemiah)
- Ancient Near Eastern language and culture

When performing a word study, you ALWAYS:
1. Identify the original language (Hebrew, Greek, or Aramaic)
2. Give the original script AND transliteration
3. Provide the Strong's number if applicable
4. Break down the root/etymology
5. List every major usage of the word across Scripture
6. Explain cultural/historical context that a modern English reader would miss
7. Note how different Bible translations handle the word (KJV, ESV, NIV, NASB, NLT)
8. Show the theological significance
9. Give practical application insight

Be scholarly but accessible. Use real Strong's numbers. Cite actual Scripture references."""


class WordStudyRequest(BaseModel):
    word: str                              # The word or phrase to study
    passage: Optional[str] = ""           # Context passage (e.g. "John 3:16")
    language: Optional[str] = "auto"      # hebrew | greek | aramaic | auto
    testament: Optional[str] = "auto"     # old | new | auto
    depth: Optional[str] = "standard"     # quick | standard | deep
    email: Optional[str] = ""


class PassageWordStudyRequest(BaseModel):
    passage: str                           # e.g. "John 1:1-5" or "Genesis 1:1"
    version: Optional[str] = "NIV"
    depth: Optional[str] = "standard"
    focus_words: Optional[int] = 5        # how many key words to study
    email: Optional[str] = ""


def ai(prompt: str, max_tokens: int = 3000) -> str:
    if not client:
        raise HTTPException(503, "OpenAI not configured")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": WORD_STUDY_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,   # Lower temp for scholarly accuracy
    )
    return resp.choices[0].message.content.strip()


def build_word_study_prompt(req: WordStudyRequest) -> str:
    depth_instructions = {
        "quick":    "Provide a concise word study (400–600 words). Hit the key points: original word, transliteration, Strong's, root meaning, key usage, and one practical application.",
        "standard": "Provide a thorough word study (800–1200 words) with full etymology, usage survey, translation comparison, theological significance, and practical application.",
        "deep":     "Provide an exhaustive academic word study (1500–2500 words). Include: full lexical analysis, Septuagint (LXX) usage if applicable, Dead Sea Scrolls or Patristic references if relevant, complete usage survey, all major translation choices with reasons, full theological significance, and multiple practical applications.",
    }
    
    lang_hint = ""
    if req.language != "auto":
        lang_map = {"hebrew": "Biblical Hebrew", "greek": "Koine Greek", "aramaic": "Biblical Aramaic"}
        lang_hint = f"\nThe word is from {lang_map.get(req.language, req.language)}."
    
    passage_hint = f"\nContext passage: {req.passage}" if req.passage else ""
    
    return f"""Perform a complete word study on the biblical word/phrase: "{req.word}"{lang_hint}{passage_hint}

{depth_instructions.get(req.depth, depth_instructions['standard'])}

Structure your response with these clear sections:

## 📖 The Word: "{req.word}"
[Original language identification]

## 🔤 Original Language
- **Script:** [original script, e.g. Hebrew: אָהַב | Greek: ἀγάπη | Aramaic: אֱלָהָא]
- **Transliteration:** [phonetic pronunciation]
- **Strong's Number:** [H#### or G####]
- **Part of Speech:** [noun, verb, adjective, etc.]
- **Root:** [root word and its base meaning]

## 📚 Etymology & Root Meaning
[Detailed breakdown of the word's origins and linguistic roots]

## 📜 Usage in Scripture
[List key passages where this word appears — minimum 5 examples with verse references and how the word is used in each context]

## 🌍 Cultural & Historical Context
[What would a first-century reader or ancient Israelite understand by this word that modern readers miss?]

## 📖 Translation Comparison
| Translation | Rendering | Notes |
|-------------|-----------|-------|
| KJV         | ...       | ...   |
| ESV         | ...       | ...   |
| NIV         | ...       | ...   |
| NASB        | ...       | ...   |
| NLT         | ...       | ...   |

## ✝️ Theological Significance
[What this word reveals about God, salvation, covenant, or biblical theology]

## 💡 Practical Application
[How understanding this word in its original language changes or deepens how we live out this truth]

## 🔗 Related Words
[2–3 related biblical words worth studying alongside this one, with brief descriptions]
"""


def build_passage_prompt(req: PassageWordStudyRequest) -> str:
    return f"""Perform word studies for the {req.focus_words} most theologically significant words in: {req.passage} ({req.version})

For EACH key word, provide:

### WORD [N]: [English Word] ([Original: script + transliteration])
- **Strong's:** H#### or G####
- **Language:** Hebrew / Greek / Aramaic
- **Root meaning:** ...
- **How it's translated:** KJV: "..." | ESV: "..." | NIV: "..."  
- **Key insight:** [1–2 sentences on what understanding this word adds to the passage]
- **Other notable uses:** [2–3 other Scripture references where this word appears]

---

After all word studies, add:

## 🔍 Passage Summary: How the Original Languages Deepen {req.passage}
[3–4 paragraphs explaining how these original language insights change or enrich our understanding of the full passage]
"""


@router.post("/analyze")
async def analyze_word(req: WordStudyRequest, request: Request):
    """Full word study: Hebrew, Greek, or Aramaic analysis of a biblical word."""
    from routers.pastor import _require_auth_and_usage
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    if not req.word or not req.word.strip():
        raise HTTPException(400, "Word is required")
    
    prompt     = build_word_study_prompt(req)
    max_tokens = {"quick": 1200, "standard": 2500, "deep": 4000}.get(req.depth, 2500)
    
    try:
        content = ai(prompt, max_tokens=max_tokens)
    except Exception as e:
        raise HTTPException(500, "Word study generation failed. Please try again in a moment.")
    
    # Try to save if user is authenticated
    saved_id = None
    try:
        from pastor_db import save_generated_content
        from routers.auth import email_from_request as _auth_email
        email = req.email or _auth_email(request) or "anonymous"
        saved_id = await save_generated_content(
            user_id=email,
            content_type="word_study",
            title=f"Word Study: {req.word}" + (f" ({req.passage})" if req.passage else ""),
            content=content,
            topic=req.word,
            scripture=req.passage or "",
        )
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("word_study save failed: %s", _e)

    return {
        "success":   True,
        "word":      req.word,
        "passage":   req.passage,
        "language":  req.language,
        "depth":     req.depth,
        "content":   content,
        "word_count": len(content.split()),
        "saved_id":  saved_id,
    }


@router.post("/passage")
async def passage_word_studies(req: PassageWordStudyRequest, request: Request):
    """Generate word studies for all key words in a Scripture passage."""
    from routers.pastor import _require_auth_and_usage
    await _require_auth_and_usage(request, getattr(req, "email", "") or "")
    if not req.passage or not req.passage.strip():
        raise HTTPException(400, "Scripture passage is required")
    
    prompt     = build_passage_prompt(req)
    max_tokens = 4000
    
    try:
        content = ai(prompt, max_tokens=max_tokens)
    except Exception as e:
        raise HTTPException(500, "Passage word study failed. Please try again in a moment.")

    saved_id = None
    try:
        from pastor_db import save_generated_content
        from routers.auth import email_from_request as _auth_email
        email = req.email or _auth_email(request) or "anonymous"
        saved_id = await save_generated_content(
            user_id=email,
            content_type="word_study_passage",
            title=f"Word Study: {req.passage}",
            content=content,
            topic="",
            scripture=req.passage or "",
        )
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("passage_word_study save failed: %s", _e)

    return {
        "success":    True,
        "passage":    req.passage,
        "version":    req.version,
        "content":    content,
        "word_count": len(content.split()),
        "saved_id":   saved_id,
    }


@router.get("/languages")
async def get_languages():
    """Return supported languages and capabilities."""
    return {
        "success": True,
        "languages": [
            {
                "id":       "hebrew",
                "name":     "Biblical Hebrew",
                "script":   "Hebrew (right-to-left)",
                "testament":"Old Testament / Tanakh",
                "books":    "All OT books",
                "strongs":  "H0001–H8674",
                "note":     "Used in most of the Old Testament. Highly pictographic root system.",
            },
            {
                "id":       "greek",
                "name":     "Koine Greek",
                "script":   "Greek alphabet",
                "testament":"New Testament",
                "books":    "All 27 NT books",
                "strongs":  "G0001–G5624",
                "note":     "The Greek of the common people (1st century AD). Rich in nuance.",
            },
            {
                "id":       "aramaic",
                "name":     "Biblical Aramaic",
                "script":   "Aramaic (similar to Hebrew script)",
                "testament":"Old Testament (portions)",
                "books":    "Daniel 2:4–7:28 · Ezra 4:8–6:18 · Ezra 7:12-26 · Jeremiah 10:11 · Genesis 31:47",
                "strongs":  "Uses Hebrew Strong's (Aramaic cognates noted)",
                "note":     "Also spoken by Jesus. Overlaps with Hebrew but distinct vocabulary.",
            },
        ]
    }
