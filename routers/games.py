"""
/v1/games/* — Bible Challenge: a leveled campaign over the Bible game engine.

Why this exists: the games were entirely client-side, so nothing was remembered
between visits, there was no progression, and there was no completion reward.

Design notes
------------
* Ten levels of increasing scope, from Genesis foundations to Revelation.
  A level unlocks when the previous one is passed (70%+). Passing awards 1-3
  stars; finishing all ten issues a certificate with a verifiable code.
* Storage reuses the existing `saved_items` table through the vault helpers
  (item_type = bible_game_progress / bible_game_certificate /
  bible_game_quiz_level). No schema migration is required.
* Questions are generated per level with the shared AI fallback and cached, so
  replaying a level costs no AI call. If generation fails, the curated KJV
  fallback bank is used instead and the response says so.
* Correct answers are stripped from the questions sent to the browser and
  grading happens here, so a client cannot submit its own score.
"""
import json
import os
import random
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ai_provider import chat_complete

router = APIRouter(prefix="/v1/games", tags=["Bible Games"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
TABLE = "saved_items"

ITEM_PROGRESS = "bible_game_progress"
ITEM_CERT = "bible_game_certificate"
ITEM_QUIZ = "bible_game_quiz_level"

QUESTIONS_PER_LEVEL = 10
PASS_PERCENT = 70
MAX_LEVEL = 10

# ── Campaign definition ───────────────────────────────────────────────────────
LEVELS: List[Dict[str, Any]] = [
    {"level": 1, "title": "Foundations of Faith", "icon": "🌍",
     "description": "Creation, the garden, the fall, the flood and Babel.",
     "subject": "Genesis 1-11: creation, Adam and Eve, the fall, Cain and Abel, Noah and the flood, the tower of Babel"},
    {"level": 2, "title": "The Patriarchs", "icon": "⛺",
     "description": "Abraham's call, the covenant, Isaac, Jacob and Joseph.",
     "subject": "Genesis 12-50: Abraham, Sarah, Isaac, Jacob, Esau, Joseph in Egypt, the covenant promises"},
    {"level": 3, "title": "Exodus and the Law", "icon": "🔥",
     "description": "Moses, the plagues, the Red Sea and the Ten Commandments.",
     "subject": "Exodus and Leviticus: Moses, the burning bush, the ten plagues, Passover, the Red Sea, Sinai, the Ten Commandments, the tabernacle"},
    {"level": 4, "title": "Wilderness to Conquest", "icon": "🏜️",
     "description": "Forty years of wandering, Joshua, the judges and Ruth.",
     "subject": "Numbers, Deuteronomy, Joshua, Judges and Ruth: the spies, wilderness years, Jericho, the conquest, Gideon, Samson, Ruth"},
    {"level": 5, "title": "The Kingdom Rises", "icon": "👑",
     "description": "Samuel, Saul, David and Solomon's temple.",
     "subject": "1 and 2 Samuel, 1 Kings 1-11: Samuel, Saul, David and Goliath, David as king, the ark, Nathan's prophecy, Solomon's wisdom and temple"},
    {"level": 6, "title": "Prophets and Exile", "icon": "📜",
     "description": "Elijah, Isaiah, Jeremiah, Daniel and the exile.",
     "subject": "1-2 Kings 12-25, Isaiah, Jeremiah, Ezekiel, Daniel: the divided kingdom, Elijah and Elisha, the exile, the fiery furnace, the lions' den, the return"},
    {"level": 7, "title": "The Messiah Arrives", "icon": "✨",
     "description": "The birth, baptism and ministry of Jesus.",
     "subject": "Matthew, Mark, Luke and John: the birth, shepherds and magi, John the Baptist, the baptism, the calling of the disciples, the Sermon on the Mount"},
    {"level": 8, "title": "Parables and Miracles", "icon": "🌾",
     "description": "The stories Jesus told and the wonders He worked.",
     "subject": "The parables and miracles of Jesus: the sower, the prodigal son, the good Samaritan, the talents, feeding the five thousand, calming the storm, healing, raising the dead"},
    {"level": 9, "title": "Cross and Empty Tomb", "icon": "✝️",
     "description": "The passion week, the crucifixion and the resurrection.",
     "subject": "The passion week: the triumphal entry, the last supper, Gethsemane, the trials, the crucifixion, the burial, the empty tomb, the resurrection appearances, the ascension"},
    {"level": 10, "title": "The Church and the End", "icon": "🕊️",
     "description": "Acts, the epistles and the book of Revelation.",
     "subject": "Acts, the epistles and Revelation: Pentecost, Paul's conversion and journeys, the Jerusalem council, fruit of the Spirit, the armor of God, love chapter, Revelation's letters and the New Jerusalem"},
]


def _headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _level_def(level: int) -> Dict[str, Any]:
    for lv in LEVELS:
        if lv["level"] == level:
            return lv
    raise HTTPException(status_code=404, detail=f"Level {level} does not exist")


def _email(request: Request) -> str:
    """Caller's email from the bearer token; empty string for guests."""
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if not token:
        return ""
    try:
        from routers.auth import decode_token
        return (decode_token(token).get("email") or "").lower().strip()
    except Exception:
        return ""


# ── Storage helpers (vault-backed, no schema changes) ────────────────────────
async def _save_item(user_id: str, item_type: str, title: str, content: Any,
                     metadata: Optional[dict] = None) -> Optional[str]:
    from routers.vault import vault_save, VaultSaveRequest
    try:
        saved = await vault_save(VaultSaveRequest(
            user_id=user_id, item_type=item_type, title=title,
            content=content, metadata=metadata or {},
        ))
        return saved.get("item_id")
    except Exception as e:
        print(f"[games] save failed ({item_type}): {e}")
        return None


async def _update_item(item_id: str, user_id: str, content: Any,
                       metadata: Optional[dict] = None) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY or not item_id:
        return False
    payload: Dict[str, Any] = {
        "content": json.dumps(content) if not isinstance(content, str) else content,
        "updated_at": _now(),
    }
    if metadata is not None:
        payload["metadata"] = metadata
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.patch(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers=_headers(),
                params={"id": f"eq.{item_id}", "user_id": f"eq.{user_id}"},
                json=payload,
            )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[games] update failed: {e}")
        return False


async def _list_items(user_id: str, item_type: str, limit: int = 50) -> List[Dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY or not user_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "item_type": f"eq.{item_type}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )
        if r.status_code != 200:
            return []
        out = []
        for row in r.json() or []:
            content = row.get("content")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except Exception:
                    content = {}
            out.append({**row, "content": content or {}})
        return out
    except Exception as e:
        print(f"[games] list failed: {e}")
        return []


def _empty_progress(email: str = "", name: str = "") -> Dict[str, Any]:
    return {
        "user_id": email,
        "display_name": name or (email.split("@")[0] if email else "Friend"),
        "levels": {},
        "xp": 0,
        "total_correct": 0,
        "total_answered": 0,
        "started_at": _now(),
        "updated_at": _now(),
    }


async def _load_progress_row(email: str) -> Dict[str, Any]:
    """Latest progress row for this user, or a fresh document."""
    rows = await _list_items(email, ITEM_PROGRESS, limit=1)
    if rows:
        row = rows[0]
        doc = row["content"] if isinstance(row["content"], dict) else {}
        doc.setdefault("levels", {})
        doc.setdefault("xp", 0)
        doc.setdefault("total_correct", 0)
        doc.setdefault("total_answered", 0)
        doc["_row_id"] = row.get("id")
        return doc
    return _empty_progress(email)


async def _save_progress(email: str, doc: Dict[str, Any]) -> str:
    """Update in place when we can, otherwise create the user's first row."""
    row_id = doc.pop("_row_id", None)
    doc["updated_at"] = _now()
    meta = {"xp": doc.get("xp", 0), "levels_passed": len([l for l, v in doc.get("levels", {}).items()
                                                          if v.get("status") == "passed"])}
    if row_id:
        ok = await _update_item(row_id, email, doc, meta)
        if ok:
            doc["_row_id"] = row_id
            return row_id
    new_id = await _save_item(email, ITEM_PROGRESS, f"Bible Challenge progress — {email}", doc, meta)
    if new_id:
        doc["_row_id"] = new_id
    return new_id or ""


def _level_state(doc: Dict[str, Any], level: int) -> Dict[str, Any]:
    return (doc.get("levels") or {}).get(str(level), {})


def _is_unlocked(doc: Dict[str, Any], level: int) -> bool:
    if level <= 1:
        return True
    prev = _level_state(doc, level - 1)
    return prev.get("status") == "passed"


def _stars(score: int, total: int) -> int:
    if total <= 0:
        return 0
    pct = score / total
    if pct >= 1.0:
        return 3
    if pct >= 0.9:
        return 2
    if pct >= PASS_PERCENT / 100:
        return 1
    return 0


def _campaign_view(doc: Dict[str, Any], email: str) -> Dict[str, Any]:
    levels = []
    passed_count = 0
    for lv in LEVELS:
        state = _level_state(doc, lv["level"])
        passed = state.get("status") == "passed"
        if passed:
            passed_count += 1
        levels.append({
            **lv,
            "status": "passed" if passed else ("in_progress" if state.get("attempts") else "not_started"),
            "unlocked": _is_unlocked(doc, lv["level"]),
            "best_score": state.get("best_score", 0),
            "best_percent": state.get("best_percent", 0),
            "stars": state.get("stars", 0),
            "attempts": state.get("attempts", 0),
            "passed_at": state.get("passed_at"),
        })
    return {
        "levels": levels,
        "questions_per_level": QUESTIONS_PER_LEVEL,
        "pass_percent": PASS_PERCENT,
        "max_level": MAX_LEVEL,
        "signed_in": bool(email),
        "display_name": doc.get("display_name", ""),
        "xp": doc.get("xp", 0),
        "total_correct": doc.get("total_correct", 0),
        "total_answered": doc.get("total_answered", 0),
        "levels_passed": passed_count,
        "levels_total": MAX_LEVEL,
        "completed": passed_count >= MAX_LEVEL,
    }


# ── Question generation ──────────────────────────────────────────────────────
_FALLBACK_PATH = os.path.join(os.path.dirname(__file__), "..", "bible_game_fallback_questions.json")


def _fallback_questions(level: int, count: int) -> List[Dict[str, Any]]:
    """Curated KJV bank, rotated so levels do not all get the same slice."""
    try:
        with open(_FALLBACK_PATH, "r", encoding="utf-8") as fh:
            bank = json.load(fh)
    except Exception:
        return []
    if not isinstance(bank, list) or not bank:
        return []
    offset = ((level - 1) * count) % len(bank)
    rotated = bank[offset:] + bank[:offset]
    picked = rotated[:count]
    out = []
    for i, q in enumerate(picked, start=1):
        if not isinstance(q, dict) or not q.get("question"):
            continue
        options = q.get("options") or []
        out.append({
            "id": i,
            "type": q.get("type", "multiple_choice"),
            "question": q["question"],
            "options": options,
            "correct_answer": q.get("correct_answer", ""),
            "explanation": q.get("explanation", ""),
            "scripture_reference": q.get("scripture_reference", ""),
        })
    return out


def _parse_questions(raw: str) -> List[Dict[str, Any]]:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned)
    except Exception:
        start, end = cleaned.find("["), cleaned.rfind("]")
        parsed = []
        if start != -1 and end != -1:
            try:
                parsed = json.loads(cleaned[start:end + 1])
            except Exception:
                parsed = []
    if isinstance(parsed, dict):
        parsed = parsed.get("questions", [])
    return parsed if isinstance(parsed, list) else []


async def _generate_questions(level_def: Dict[str, Any], language: str) -> tuple[List[Dict[str, Any]], bool]:
    """AI first, curated bank second. Returns (questions, used_fallback)."""
    lang_note = "Write every question, option and explanation in Spanish." if str(language).lower().startswith("es") else "Write everything in English."
    prompt = f"""Generate exactly {QUESTIONS_PER_LEVEL} Bible quiz questions for level {level_def['level']} of a discipleship game: "{level_def['title']}".

Scope for this level: {level_def['subject']}

Rules:
- Stay strictly inside this level's scope; do not drift into later books or themes.
- Difficulty should suit a Bible-reading adult: solid recall plus understanding, not trivia about genealogies.
- Mix multiple_choice, true_false and scripture_reference questions.
- Every fact must be accurate and consistent with the King James Version.
- {lang_note}

Return ONLY a JSON array, no prose and no code fences. Each item:
{{
  "type": "multiple_choice" | "true_false" | "scripture_reference",
  "question": "question text",
  "options": ["a","b","c","d"],   // ["True","False"] for true_false
  "correct_answer": "must exactly match one of the options",
  "explanation": "one or two sentences explaining why",
  "scripture_reference": "Book Chapter:Verse"
}}"""
    try:
        raw = chat_complete(
            "You are a Bible scholar writing accurate, KJV-consistent quiz questions for a church discipleship game.",
            prompt,
            max_tokens=2600,
            temperature=0.7,
        )
        parsed = _parse_questions(raw)
        questions: List[Dict[str, Any]] = []
        for i, q in enumerate(parsed, start=1):
            if not isinstance(q, dict) or not q.get("question"):
                continue
            opts = [str(o) for o in (q.get("options") or []) if str(o).strip()]
            if not opts:
                continue
            correct = str(q.get("correct_answer", "")).strip()
            if correct not in opts:
                # keep only questions we can grade unambiguously
                continue
            questions.append({
                "id": i,
                "type": q.get("type", "multiple_choice"),
                "question": q["question"],
                "options": opts,
                "correct_answer": correct,
                "explanation": q.get("explanation", ""),
                "scripture_reference": q.get("scripture_reference", ""),
            })
        if len(questions) >= QUESTIONS_PER_LEVEL:
            return questions[:QUESTIONS_PER_LEVEL], False
        if questions:
            filler = _fallback_questions(level_def["level"], QUESTIONS_PER_LEVEL)
            seen = {q["question"] for q in questions}
            for q in filler:
                if len(questions) >= QUESTIONS_PER_LEVEL:
                    break
                if q["question"] not in seen:
                    q["id"] = len(questions) + 1
                    questions.append(q)
            if questions:
                return questions, True
    except Exception as e:
        print(f"[games] AI generation failed for level {level_def['level']}: {e}")

    return _fallback_questions(level_def["level"], QUESTIONS_PER_LEVEL), True


def _public_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip answers before the questions leave the server."""
    return [{
        "id": q["id"],
        "type": q.get("type", "multiple_choice"),
        "question": q["question"],
        "options": q.get("options", []),
        "scripture_reference": q.get("scripture_reference", ""),
    } for q in questions]


# ── Grading ──────────────────────────────────────────────────────────────────
def _norm(value: str) -> str:
    return " ".join(str(value or "").lower().strip().split())


def _grade(questions: List[Dict[str, Any]], answers: Dict[str, str]) -> tuple[int, List[Dict[str, Any]]]:
    correct = 0
    detail = []
    for q in questions:
        given = answers.get(str(q["id"]), "")
        is_right = _norm(given) == _norm(q.get("correct_answer", ""))
        if is_right:
            correct += 1
        detail.append({
            "id": q["id"],
            "correct": is_right,
            "given": given,
            "correct_answer": q.get("correct_answer", ""),
            "explanation": q.get("explanation", ""),
            "scripture_reference": q.get("scripture_reference", ""),
        })
    return correct, detail


async def _issue_certificate(email: str, doc: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """Idempotent: one certificate per user, reissued only if the stored one is gone."""
    existing = await _list_items(email, ITEM_CERT, limit=1)
    if existing:
        cert = existing[0].get("content") or {}
        if cert.get("code"):
            return cert
    code = "PAC-" + secrets.token_hex(4).upper()
    levels = doc.get("levels") or {}
    avg = 0
    if levels:
        avg = round(sum(v.get("best_percent", 0) for v in levels.values()) / len(levels))
    cert = {
        "code": code,
        "name": name or doc.get("display_name") or email.split("@")[0],
        "email": email,
        "levels_completed": len([v for v in levels.values() if v.get("status") == "passed"]),
        "levels_total": MAX_LEVEL,
        "average_percent": avg,
        "xp": doc.get("xp", 0),
        "issued_at": _now(),
        "program": "Bible Challenge",
    }
    await _save_item(email, ITEM_CERT, f"Bible Challenge certificate {code}", cert, {"code": code})
    return cert


# ── Request models ───────────────────────────────────────────────────────────
class StartLevelRequest(BaseModel):
    level: int
    language: Optional[str] = "en"
    regenerate: Optional[bool] = False


class SubmitLevelRequest(BaseModel):
    level: int
    quiz_id: Optional[str] = None
    answers: Dict[str, str] = {}
    display_name: Optional[str] = ""


# ── Routes ───────────────────────────────────────────────────────────────────
@router.get("/campaign")
async def campaign(request: Request):
    """Level map plus this user's saved progress. Readable without signing in."""
    email = _email(request)
    doc = await _load_progress_row(email) if email else _empty_progress()
    view = _campaign_view(doc, email)
    certs = await _list_items(email, ITEM_CERT, limit=1) if email else []
    view["certificate"] = (certs[0].get("content") if certs else None)
    return {"success": True, **view}


@router.post("/level/start")
async def start_level(req: StartLevelRequest, request: Request):
    """Serve a level's questions (answers withheld) and cache them for replay."""
    email = _email(request)
    level_def = _level_def(req.level)
    doc = await _load_progress_row(email) if email else _empty_progress()

    if email and not _is_unlocked(doc, req.level):
        raise HTTPException(status_code=403, detail="Finish the previous level to unlock this one.")

    quiz_id, questions, used_fallback = None, [], True
    if email and not req.regenerate:
        cached = await _list_items(email, ITEM_QUIZ, limit=50)
        for row in cached:
            content = row.get("content") or {}
            if content.get("level") == req.level and content.get("language", "en") == (req.language or "en"):
                stored = content.get("questions") or []
                if len(stored) >= QUESTIONS_PER_LEVEL:
                    quiz_id, questions = row.get("id"), stored[:QUESTIONS_PER_LEVEL]
                    used_fallback = bool(content.get("used_fallback"))
                    break

    if not questions:
        questions, used_fallback = await _generate_questions(level_def, req.language or "en")
        if not questions:
            raise HTTPException(status_code=502, detail="Could not prepare questions for this level. Please try again.")
        if email:
            quiz_id = await _save_item(
                email, ITEM_QUIZ, f"Bible Challenge level {req.level} — {level_def['title']}",
                {"level": req.level, "language": req.language or "en",
                 "questions": questions, "used_fallback": used_fallback},
                {"level": req.level, "count": len(questions)},
            )

    return {
        "success": True,
        "level": req.level,
        "title": level_def["title"],
        "quiz_id": quiz_id,
        "count": len(questions),
        "questions": _public_questions(questions),
        "used_fallback": used_fallback,
        "saved": bool(quiz_id),
    }


@router.post("/level/submit")
async def submit_level(req: SubmitLevelRequest, request: Request):
    """Grade server-side, record the attempt, unlock the next level, maybe wrap up."""
    email = _email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Sign in to save your progress.")
    level_def = _level_def(req.level)
    doc = await _load_progress_row(email)

    if not _is_unlocked(doc, req.level):
        raise HTTPException(status_code=403, detail="Finish the previous level to unlock this one.")

    questions: List[Dict[str, Any]] = []
    if req.quiz_id:
        rows = await _list_items(email, ITEM_QUIZ, limit=50)
        for row in rows:
            if row.get("id") == req.quiz_id:
                questions = ((row.get("content") or {}).get("questions") or [])
                break
    if not questions:
        # accept a level's most recent cached set so a lost quiz_id is not fatal
        rows = await _list_items(email, ITEM_QUIZ, limit=50)
        for row in rows:
            content = row.get("content") or {}
            if content.get("level") == req.level:
                questions = content.get("questions") or []
                break
    if not questions:
        raise HTTPException(status_code=404, detail="That quiz is no longer available. Start the level again.")

    score, detail = _grade(questions, req.answers or {})
    total = len(questions)
    percent = round(score / total * 100) if total else 0
    passed = percent >= PASS_PERCENT
    stars = _stars(score, total)

    state = _level_state(doc, req.level)
    attempts = int(state.get("attempts", 0)) + 1
    best_score = max(int(state.get("best_score", 0)), score)
    best_percent = max(int(state.get("best_percent", 0)), percent)
    entry = {
        "status": "passed" if passed or state.get("status") == "passed" else "in_progress",
        "best_score": best_score,
        "best_percent": best_percent,
        "best_stars": max(int(state.get("best_stars", 0)), stars),
        "stars": max(int(state.get("stars", 0)), stars),
        "attempts": attempts,
        "last_score": score,
        "last_percent": percent,
        "passed_at": state.get("passed_at") or (_now() if passed else None),
    }
    doc.setdefault("levels", {})[str(req.level)] = entry

    xp_gained = score * 10 + (level_def["level"] * 5 if passed and state.get("status") != "passed" else 0)
    doc["xp"] = int(doc.get("xp", 0)) + xp_gained
    doc["total_correct"] = int(doc.get("total_correct", 0)) + score
    doc["total_answered"] = int(doc.get("total_answered", 0)) + total
    if req.display_name:
        doc["display_name"] = req.display_name.strip()[:60]
    doc["user_id"] = email

    await _save_progress(email, doc)

    passed_levels = len([v for v in doc["levels"].values() if v.get("status") == "passed"])
    certificate = None
    if passed_levels >= MAX_LEVEL:
        certificate = await _issue_certificate(email, doc, req.display_name or "")

    view = _campaign_view(doc, email)
    view["certificate"] = certificate
    return {
        "success": True,
        "level": req.level,
        "title": level_def["title"],
        "score": score,
        "total": total,
        "percent": percent,
        "passed": passed,
        "stars": stars,
        "xp_gained": xp_gained,
        "detail": detail,
        "progress": view,
        "levels_passed": passed_levels,
        "certificate": certificate,
    }


@router.get("/progress")
async def progress(request: Request):
    email = _email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Sign in to see your saved progress.")
    doc = await _load_progress_row(email)
    view = _campaign_view(doc, email)
    certs = await _list_items(email, ITEM_CERT, limit=1)
    view["certificate"] = (certs[0].get("content") if certs else None)
    return {"success": True, **view}


@router.post("/reset")
async def reset_progress(request: Request):
    email = _email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Sign in first.")
    doc = _empty_progress(email)
    doc["user_id"] = email
    await _save_progress(email, doc)
    return {"success": True, "progress": _campaign_view(doc, email)}


@router.get("/certificate/{code}")
async def verify_certificate(code: str):
    """Public verification — anyone holding a code can confirm it is genuine."""
    clean = (code or "").strip().upper()
    if not clean.startswith("PAC-"):
        raise HTTPException(status_code=400, detail="Certificate codes look like PAC-XXXXXXXX.")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=503, detail="Certificate lookup is unavailable right now.")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers=_headers(),
                params={"item_type": f"eq.{ITEM_CERT}",
                        "metadata->>code": f"eq.{clean}",
                        "limit": "1"},
            )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Certificate lookup failed: {e}")
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="No certificate matches that code.")
    row = r.json()[0]
    content = row.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            content = {}
    cert = {k: v for k, v in (content or {}).items() if k != "email"}
    return {"success": True, "valid": True, "certificate": cert}


@router.get("/leaderboard")
async def leaderboard(limit: int = 20):
    """Real standings from saved progress — no placeholder names."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"success": True, "leaders": [], "available": False}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers=_headers(),
                params={"item_type": f"eq.{ITEM_PROGRESS}", "limit": "500"},
            )
    except Exception:
        return {"success": True, "leaders": [], "available": False}
    if r.status_code != 200:
        return {"success": True, "leaders": [], "available": False}

    rows = []
    for row in r.json() or []:
        content = row.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                continue
        if not isinstance(content, dict):
            continue
        levels = content.get("levels") or {}
        passed = len([v for v in levels.values() if v.get("status") == "passed"])
        if not content.get("xp") and not passed:
            continue
        rows.append({
            "name": content.get("display_name") or "Friend",
            "xp": int(content.get("xp", 0)),
            "levels_passed": passed,
        })
    rows.sort(key=lambda x: (x["levels_passed"], x["xp"]), reverse=True)
    return {"success": True, "available": True, "leaders": rows[:max(1, min(limit, 50))]}
