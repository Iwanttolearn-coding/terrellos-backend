"""
routers/voice_interview.py — Heavenly Eternal Echo™
MASTER LEGACY INTERVIEW SYSTEM — 777 FRAMEWORK

140 questions across 7 categories + Emotional State Capture + AI Deep Follow-Ups

Endpoints:
  GET  /v1/voice-interview/health
  GET  /v1/voice-interview/questions                    — full 777 framework
  GET  /v1/voice-interview/questions/{category_id}      — single category
  GET  /v1/voice-interview/categories                   — category index
  POST /v1/voice-interview/ai-followup                  — AI generates deep follow-up
  POST /v1/voice-interview/recording/save               — save audio + transcript + emotional state
  GET  /v1/voice-interview/recordings/{uid}             — list recordings
  DELETE /v1/voice-interview/recording/{id}             — delete recording
  GET  /v1/voice-interview/progress/{uid}               — minutes + completion + clone readiness
  GET  /v1/voice-interview/session/{uid}                — full session with emotional fingerprint
  POST /v1/voice-interview/clone                        — send audio to ElevenLabs
  GET  /v1/voice-interview/clone/{uid}                  — clone status
  POST /v1/voice-interview/test-clone                   — TTS with cloned voice
"""
import os, uuid, httpx, logging, re
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger("voice_interview")
router = APIRouter(prefix="/v1/voice-interview", tags=["Voice Interview"])

ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_BASE     = "https://api.elevenlabs.io/v1"
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
SUPABASE_URL        = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY        = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
MIN_CLONE_SECONDS   = 15 * 60
RECOMMENDED_SECONDS = 30 * 60

def _now(): return datetime.now(timezone.utc).isoformat()

# ── Supabase helpers ──────────────────────────────────────────────────────────
async def _sb_insert(table: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=data,
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Supabase insert failed {r.status_code}: {r.text[:200]}")
    rows = r.json()
    return rows[0] if rows else data

async def _sb_select(table: str, filters: dict = None, limit: int = 500) -> list:
    params = f"?limit={limit}&order=created_at.asc"
    if filters:
        for k, v in filters.items():
            params += f"&{k}=eq.{v}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/{table}{params}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Accept": "application/json"},
        )
    if r.status_code != 200:
        return []
    return r.json() or []

async def _sb_update(table: str, filters: dict, data: dict):
    params = "?" + "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.patch(
            f"{SUPABASE_URL}/rest/v1/{table}{params}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=data,
        )
    return r.status_code in (200, 204)

async def _sb_delete(table: str, filters: dict):
    params = "?" + "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.delete(
            f"{SUPABASE_URL}/rest/v1/{table}{params}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        )
    return r.status_code in (200, 204)

# ══════════════════════════════════════════════════════════════════
# 777 FRAMEWORK — 140 QUESTIONS ACROSS 7 CATEGORIES
# ══════════════════════════════════════════════════════════════════

CATEGORIES_777 = [
    {"id": 1, "name": "Origins & Childhood",         "range": [1, 20],    "icon": "🌱", "color": "#10b981"},
    {"id": 2, "name": "Family & Relationships",      "range": [21, 40],   "icon": "❤️",  "color": "#ec4899"},
    {"id": 3, "name": "Struggles & Adversity",       "range": [41, 60],   "icon": "⚡",  "color": "#f59e0b"},
    {"id": 4, "name": "Faith & Spirituality",        "range": [61, 80],   "icon": "✝️",  "color": "#8b5cf6"},
    {"id": 5, "name": "Purpose, Work & Achievement", "range": [81, 100],  "icon": "🏆",  "color": "#3b82f6"},
    {"id": 6, "name": "Wisdom & Life Lessons",       "range": [101, 120], "icon": "📖",  "color": "#06b6d4"},
    {"id": 7, "name": "Eternal Legacy",              "range": [121, 140], "icon": "✨",  "color": "#f97316"},
]

LEGACY_QUESTIONS_777 = [
    # ── CATEGORY 1: ORIGINS & CHILDHOOD ──────────────────────────
    {"id":1,  "category":"Origins & Childhood",        "cat_id":1, "n":1,  "q":"What is your full name and why were you given that name?"},
    {"id":2,  "category":"Origins & Childhood",        "cat_id":1, "n":2,  "q":"Where were you born?"},
    {"id":3,  "category":"Origins & Childhood",        "cat_id":1, "n":3,  "q":"What is your earliest memory?"},
    {"id":4,  "category":"Origins & Childhood",        "cat_id":1, "n":4,  "q":"Describe your childhood home."},
    {"id":5,  "category":"Origins & Childhood",        "cat_id":1, "n":5,  "q":"Who raised you?"},
    {"id":6,  "category":"Origins & Childhood",        "cat_id":1, "n":6,  "q":"What did your parents teach you?"},
    {"id":7,  "category":"Origins & Childhood",        "cat_id":1, "n":7,  "q":"What family traditions do you remember?"},
    {"id":8,  "category":"Origins & Childhood",        "cat_id":1, "n":8,  "q":"What were holidays like growing up?"},
    {"id":9,  "category":"Origins & Childhood",        "cat_id":1, "n":9,  "q":"What was your favorite toy?"},
    {"id":10, "category":"Origins & Childhood",        "cat_id":1, "n":10, "q":"What was your greatest childhood fear?"},
    {"id":11, "category":"Origins & Childhood",        "cat_id":1, "n":11, "q":"What made you happiest as a child?"},
    {"id":12, "category":"Origins & Childhood",        "cat_id":1, "n":12, "q":"Who was your childhood hero?"},
    {"id":13, "category":"Origins & Childhood",        "cat_id":1, "n":13, "q":"What was school like?"},
    {"id":14, "category":"Origins & Childhood",        "cat_id":1, "n":14, "q":"What subjects did you enjoy?"},
    {"id":15, "category":"Origins & Childhood",        "cat_id":1, "n":15, "q":"What subjects did you dislike?"},
    {"id":16, "category":"Origins & Childhood",        "cat_id":1, "n":16, "q":"What was your first major accomplishment?"},
    {"id":17, "category":"Origins & Childhood",        "cat_id":1, "n":17, "q":"What was your first major disappointment?"},
    {"id":18, "category":"Origins & Childhood",        "cat_id":1, "n":18, "q":"Did you experience bullying?"},
    {"id":19, "category":"Origins & Childhood",        "cat_id":1, "n":19, "q":"Did you ever bully others?"},
    {"id":20, "category":"Origins & Childhood",        "cat_id":1, "n":20, "q":"What life lessons did childhood teach you?"},
    # ── CATEGORY 2: FAMILY & RELATIONSHIPS ───────────────────────
    {"id":21, "category":"Family & Relationships",     "cat_id":2, "n":1,  "q":"Describe your mother."},
    {"id":22, "category":"Family & Relationships",     "cat_id":2, "n":2,  "q":"Describe your father."},
    {"id":23, "category":"Family & Relationships",     "cat_id":2, "n":3,  "q":"Describe your siblings."},
    {"id":24, "category":"Family & Relationships",     "cat_id":2, "n":4,  "q":"Who had the greatest influence on you?"},
    {"id":25, "category":"Family & Relationships",     "cat_id":2, "n":5,  "q":"What family member impacted you most?"},
    {"id":26, "category":"Family & Relationships",     "cat_id":2, "n":6,  "q":"What is your strongest family memory?"},
    {"id":27, "category":"Family & Relationships",     "cat_id":2, "n":7,  "q":"What family conflict shaped you?"},
    {"id":28, "category":"Family & Relationships",     "cat_id":2, "n":8,  "q":"What does loyalty mean to you?"},
    {"id":29, "category":"Family & Relationships",     "cat_id":2, "n":9,  "q":"What does forgiveness mean to you?"},
    {"id":30, "category":"Family & Relationships",     "cat_id":2, "n":10, "q":"What is unconditional love?"},
    {"id":31, "category":"Family & Relationships",     "cat_id":2, "n":11, "q":"Who was your first close friend?"},
    {"id":32, "category":"Family & Relationships",     "cat_id":2, "n":12, "q":"What friendship changed your life?"},
    {"id":33, "category":"Family & Relationships",     "cat_id":2, "n":13, "q":"What friendship ended painfully?"},
    {"id":34, "category":"Family & Relationships",     "cat_id":2, "n":14, "q":"What relationship taught you the most?"},
    {"id":35, "category":"Family & Relationships",     "cat_id":2, "n":15, "q":"What relationship hurt the most?"},
    {"id":36, "category":"Family & Relationships",     "cat_id":2, "n":16, "q":"What relationship healed you?"},
    {"id":37, "category":"Family & Relationships",     "cat_id":2, "n":17, "q":"Who understands you best?"},
    {"id":38, "category":"Family & Relationships",     "cat_id":2, "n":18, "q":"What advice would you give your family?"},
    {"id":39, "category":"Family & Relationships",     "cat_id":2, "n":19, "q":"What do you wish your family knew?"},
    {"id":40, "category":"Family & Relationships",     "cat_id":2, "n":20, "q":"What family legacy do you want to leave?"},
    # ── CATEGORY 3: STRUGGLES & ADVERSITY ───────────────────────
    {"id":41, "category":"Struggles & Adversity",      "cat_id":3, "n":1,  "q":"What is the hardest thing you have survived?"},
    {"id":42, "category":"Struggles & Adversity",      "cat_id":3, "n":2,  "q":"What trauma impacted you most?"},
    {"id":43, "category":"Struggles & Adversity",      "cat_id":3, "n":3,  "q":"What mistake taught you the most?"},
    {"id":44, "category":"Struggles & Adversity",      "cat_id":3, "n":4,  "q":"What regret still affects you?"},
    {"id":45, "category":"Struggles & Adversity",      "cat_id":3, "n":5,  "q":"What loss changed your life?"},
    {"id":46, "category":"Struggles & Adversity",      "cat_id":3, "n":6,  "q":"What failure made you stronger?"},
    {"id":47, "category":"Struggles & Adversity",      "cat_id":3, "n":7,  "q":"What addiction or struggle have you faced?"},
    {"id":48, "category":"Struggles & Adversity",      "cat_id":3, "n":8,  "q":"What battle did others never see?"},
    {"id":49, "category":"Struggles & Adversity",      "cat_id":3, "n":9,  "q":"When did you feel completely alone?"},
    {"id":50, "category":"Struggles & Adversity",      "cat_id":3, "n":10, "q":"What nearly broke you?"},
    {"id":51, "category":"Struggles & Adversity",      "cat_id":3, "n":11, "q":"How did you overcome it?"},
    {"id":52, "category":"Struggles & Adversity",      "cat_id":3, "n":12, "q":"What gave you strength?"},
    {"id":53, "category":"Struggles & Adversity",      "cat_id":3, "n":13, "q":"Who helped you survive?"},
    {"id":54, "category":"Struggles & Adversity",      "cat_id":3, "n":14, "q":"What would you tell someone facing the same challenge?"},
    {"id":55, "category":"Struggles & Adversity",      "cat_id":3, "n":15, "q":"What have your scars taught you?"},
    {"id":56, "category":"Struggles & Adversity",      "cat_id":3, "n":16, "q":"What pain became purpose?"},
    {"id":57, "category":"Struggles & Adversity",      "cat_id":3, "n":17, "q":"What do people misunderstand about your story?"},
    {"id":58, "category":"Struggles & Adversity",      "cat_id":3, "n":18, "q":"What injustice have you experienced?"},
    {"id":59, "category":"Struggles & Adversity",      "cat_id":3, "n":19, "q":"How did adversity shape your character?"},
    {"id":60, "category":"Struggles & Adversity",      "cat_id":3, "n":20, "q":"What lesson must future generations learn from your struggles?"},
    # ── CATEGORY 4: FAITH & SPIRITUALITY ────────────────────────
    {"id":61, "category":"Faith & Spirituality",       "cat_id":4, "n":1,  "q":"Do you believe in God?"},
    {"id":62, "category":"Faith & Spirituality",       "cat_id":4, "n":2,  "q":"Describe your faith journey."},
    {"id":63, "category":"Faith & Spirituality",       "cat_id":4, "n":3,  "q":"What spiritual experience changed you?"},
    {"id":64, "category":"Faith & Spirituality",       "cat_id":4, "n":4,  "q":"When did you first sense God's presence?"},
    {"id":65, "category":"Faith & Spirituality",       "cat_id":4, "n":5,  "q":"What scripture means the most to you?"},
    {"id":66, "category":"Faith & Spirituality",       "cat_id":4, "n":6,  "q":"What prayer was answered?"},
    {"id":67, "category":"Faith & Spirituality",       "cat_id":4, "n":7,  "q":"What prayer seemed unanswered?"},
    {"id":68, "category":"Faith & Spirituality",       "cat_id":4, "n":8,  "q":"What doubt have you wrestled with?"},
    {"id":69, "category":"Faith & Spirituality",       "cat_id":4, "n":9,  "q":"How has faith carried you?"},
    {"id":70, "category":"Faith & Spirituality",       "cat_id":4, "n":10, "q":"What does salvation mean to you?"},
    {"id":71, "category":"Faith & Spirituality",       "cat_id":4, "n":11, "q":"What does grace mean to you?"},
    {"id":72, "category":"Faith & Spirituality",       "cat_id":4, "n":12, "q":"What does forgiveness mean spiritually?"},
    {"id":73, "category":"Faith & Spirituality",       "cat_id":4, "n":13, "q":"What role does church play in your life?"},
    {"id":74, "category":"Faith & Spirituality",       "cat_id":4, "n":14, "q":"What role does prayer play?"},
    {"id":75, "category":"Faith & Spirituality",       "cat_id":4, "n":15, "q":"What role does worship play?"},
    {"id":76, "category":"Faith & Spirituality",       "cat_id":4, "n":16, "q":"What role does scripture play?"},
    {"id":77, "category":"Faith & Spirituality",       "cat_id":4, "n":17, "q":"What do you believe happens after death?"},
    {"id":78, "category":"Faith & Spirituality",       "cat_id":4, "n":18, "q":"What would you ask God?"},
    {"id":79, "category":"Faith & Spirituality",       "cat_id":4, "n":19, "q":"What has God taught you recently?"},
    {"id":80, "category":"Faith & Spirituality",       "cat_id":4, "n":20, "q":"What spiritual legacy do you want to leave?"},
    # ── CATEGORY 5: PURPOSE, WORK & ACHIEVEMENT ─────────────────
    {"id":81, "category":"Purpose, Work & Achievement","cat_id":5, "n":1,  "q":"What is your purpose?"},
    {"id":82, "category":"Purpose, Work & Achievement","cat_id":5, "n":2,  "q":"What work are you most proud of?"},
    {"id":83, "category":"Purpose, Work & Achievement","cat_id":5, "n":3,  "q":"What accomplishment matters most?"},
    {"id":84, "category":"Purpose, Work & Achievement","cat_id":5, "n":4,  "q":"What dream did you achieve?"},
    {"id":85, "category":"Purpose, Work & Achievement","cat_id":5, "n":5,  "q":"What dream remains unfinished?"},
    {"id":86, "category":"Purpose, Work & Achievement","cat_id":5, "n":6,  "q":"What talent has God given you?"},
    {"id":87, "category":"Purpose, Work & Achievement","cat_id":5, "n":7,  "q":"What contribution have you made?"},
    {"id":88, "category":"Purpose, Work & Achievement","cat_id":5, "n":8,  "q":"What career lesson changed you?"},
    {"id":89, "category":"Purpose, Work & Achievement","cat_id":5, "n":9,  "q":"What leadership lesson changed you?"},
    {"id":90, "category":"Purpose, Work & Achievement","cat_id":5, "n":10, "q":"What would you do if failure were impossible?"},
    {"id":91, "category":"Purpose, Work & Achievement","cat_id":5, "n":11, "q":"What motivates you?"},
    {"id":92, "category":"Purpose, Work & Achievement","cat_id":5, "n":12, "q":"What inspires you?"},
    {"id":93, "category":"Purpose, Work & Achievement","cat_id":5, "n":13, "q":"What drains you?"},
    {"id":94, "category":"Purpose, Work & Achievement","cat_id":5, "n":14, "q":"What energizes you?"},
    {"id":95, "category":"Purpose, Work & Achievement","cat_id":5, "n":15, "q":"What problem do you want solved?"},
    {"id":96, "category":"Purpose, Work & Achievement","cat_id":5, "n":16, "q":"What mission drives you?"},
    {"id":97, "category":"Purpose, Work & Achievement","cat_id":5, "n":17, "q":"What impact do you want to make?"},
    {"id":98, "category":"Purpose, Work & Achievement","cat_id":5, "n":18, "q":"What would success look like?"},
    {"id":99, "category":"Purpose, Work & Achievement","cat_id":5, "n":19, "q":"What is true wealth?"},
    {"id":100,"category":"Purpose, Work & Achievement","cat_id":5, "n":20, "q":"What does a meaningful life look like?"},
    # ── CATEGORY 6: WISDOM & LIFE LESSONS ───────────────────────
    {"id":101,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":1,  "q":"What is the most important lesson you learned?"},
    {"id":102,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":2,  "q":"What advice would you give your younger self?"},
    {"id":103,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":3,  "q":"What advice would you give your children?"},
    {"id":104,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":4,  "q":"What advice would you give future generations?"},
    {"id":105,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":5,  "q":"What is love?"},
    {"id":106,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":6,  "q":"What is happiness?"},
    {"id":107,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":7,  "q":"What is success?"},
    {"id":108,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":8,  "q":"What is wisdom?"},
    {"id":109,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":9,  "q":"What is courage?"},
    {"id":110,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":10, "q":"What is integrity?"},
    {"id":111,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":11, "q":"What is faith?"},
    {"id":112,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":12, "q":"What is hope?"},
    {"id":113,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":13, "q":"What is freedom?"},
    {"id":114,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":14, "q":"What is forgiveness?"},
    {"id":115,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":15, "q":"What is humility?"},
    {"id":116,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":16, "q":"What is leadership?"},
    {"id":117,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":17, "q":"What is friendship?"},
    {"id":118,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":18, "q":"What is purpose?"},
    {"id":119,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":19, "q":"What is legacy?"},
    {"id":120,"category":"Wisdom & Life Lessons",      "cat_id":6, "n":20, "q":"What truth should never be forgotten?"},
    # ── CATEGORY 7: ETERNAL LEGACY ───────────────────────────────
    {"id":121,"category":"Eternal Legacy",             "cat_id":7, "n":1,  "q":"How do you want to be remembered?"},
    {"id":122,"category":"Eternal Legacy",             "cat_id":7, "n":2,  "q":"What story must never be forgotten?"},
    {"id":123,"category":"Eternal Legacy",             "cat_id":7, "n":3,  "q":"What message would you leave your family?"},
    {"id":124,"category":"Eternal Legacy",             "cat_id":7, "n":4,  "q":"What message would you leave your grandchildren?"},
    {"id":125,"category":"Eternal Legacy",             "cat_id":7, "n":5,  "q":"What message would you leave humanity?"},
    {"id":126,"category":"Eternal Legacy",             "cat_id":7, "n":6,  "q":"What are you most grateful for?"},
    {"id":127,"category":"Eternal Legacy",             "cat_id":7, "n":7,  "q":"What do you hope others learn from your life?"},
    {"id":128,"category":"Eternal Legacy",             "cat_id":7, "n":8,  "q":"What unfinished business remains?"},
    {"id":129,"category":"Eternal Legacy",             "cat_id":7, "n":9,  "q":"What brings you peace?"},
    {"id":130,"category":"Eternal Legacy",             "cat_id":7, "n":10, "q":"What do you want future generations to know?"},
    {"id":131,"category":"Eternal Legacy",             "cat_id":7, "n":11, "q":"What values should survive you?"},
    {"id":132,"category":"Eternal Legacy",             "cat_id":7, "n":12, "q":"What beliefs should survive you?"},
    {"id":133,"category":"Eternal Legacy",             "cat_id":7, "n":13, "q":"What lessons should survive you?"},
    {"id":134,"category":"Eternal Legacy",             "cat_id":7, "n":14, "q":"What memories should survive you?"},
    {"id":135,"category":"Eternal Legacy",             "cat_id":7, "n":15, "q":"What traditions should survive you?"},
    {"id":136,"category":"Eternal Legacy",             "cat_id":7, "n":16, "q":"What warnings should survive you?"},
    {"id":137,"category":"Eternal Legacy",             "cat_id":7, "n":17, "q":"What encouragement should survive you?"},
    {"id":138,"category":"Eternal Legacy",             "cat_id":7, "n":18, "q":"What is your final testimony?"},
    {"id":139,"category":"Eternal Legacy",             "cat_id":7, "n":19, "q":"What would you say if this were your last interview?"},
    {"id":140,"category":"Eternal Legacy",             "cat_id":7, "n":20, "q":"What is your Eternal Echo?"},
]

# Build lookup index
QUESTION_BY_ID = {q["id"]: q for q in LEGACY_QUESTIONS_777}

# ── AI Follow-Up Trigger Detection ──────────────────────────────────────────
DEEP_FOLLOW_UP_TRIGGERS = {
    "trauma":         ["abuse","hurt","trauma","violence","attacked","assault","neglect","abandoned","horrible","terrible","suffer"],
    "faith":          ["god","jesus","holy spirit","prayer","miracle","faith","saved","church","scripture","baptism","spiritual","worship","grace","salvation"],
    "loss":           ["died","death","passed","lost","funeral","burial","grief","miss","gone","mourning","cancer","illness"],
    "addiction":      ["addiction","alcohol","drugs","substance","recovery","rehab","sober","clean","drinking","using"],
    "military":       ["military","served","army","navy","marine","air force","combat","war","deployed","veteran","service","overseas"],
    "prison":         ["prison","jail","incarcerated","arrested","sentence","locked up","convicted","charges","time","cell"],
    "marriage":       ["married","wedding","wife","husband","divorce","separated","partner","vows","relationship","love of my life"],
    "parenthood":     ["born","baby","child","son","daughter","parent","father","mother","raised","pregnant","kids"],
    "transformation": ["changed","transformed","turning point","never the same","breakthrough","awakening","renewed","reborn"],
    "defining_moment":["never forget","changed everything","life was never","biggest","most important","turning point"],
}

EMOTION_OPTIONS = [
    "Joy","Gratitude","Love","Pride","Hope","Peace","Faith",
    "Sadness","Grief","Regret","Shame","Fear","Anger","Loneliness",
    "Surprise","Nostalgia","Awe","Confusion","Relief","Mixed"
]

def detect_follow_up_triggers(transcript: str) -> list[str]:
    """Detect which deep-follow-up categories are triggered by the transcript."""
    text = transcript.lower()
    triggered = []
    for category, keywords in DEEP_FOLLOW_UP_TRIGGERS.items():
        if any(kw in text for kw in keywords):
            triggered.append(category)
    return triggered


# ── Pydantic Models ──────────────────────────────────────────────────────────
class EmotionalState(BaseModel):
    importance: Optional[int] = None          # 1-10
    emotion: Optional[str] = None
    expand_requested: Optional[bool] = None
    valence: Optional[str] = None             # positive/negative/mixed
    frequency: Optional[str] = None
    who_involved: Optional[str] = None
    is_defining_moment: Optional[bool] = None

class SaveRecordingRequest(BaseModel):
    user_id: str
    profile_id: Optional[str] = None
    question_id: int
    question_text: str
    category: str
    transcript: str
    audio_url: Optional[str] = None
    storage_path: Optional[str] = None
    duration_sec: float = 0
    file_size_bytes: int = 0
    emotional_state: Optional[EmotionalState] = None
    ai_followup_triggered: Optional[list] = None
    ai_followup_question: Optional[str] = None

class AIFollowUpRequest(BaseModel):
    question_id: int
    question_text: str
    category: str
    transcript: str
    emotional_state: Optional[dict] = None

class CloneRequest(BaseModel):
    user_id: str
    profile_id: Optional[str] = None
    voice_name: Optional[str] = None

class TestCloneRequest(BaseModel):
    user_id: str
    text: str
    voice_id: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "success": True,
        "status": "online",
        "framework": "777",
        "total_questions": len(LEGACY_QUESTIONS_777),
        "categories": len(CATEGORIES_777),
        "elevenlabs": bool(ELEVENLABS_API_KEY),
        "supabase": bool(SUPABASE_URL and SUPABASE_KEY),
        "openai": bool(OPENAI_API_KEY),
        "min_clone_minutes": MIN_CLONE_SECONDS / 60,
    }


@router.get("/categories")
async def get_categories():
    """Return all 7 category definitions with metadata."""
    return {
        "success": True,
        "framework": "777",
        "categories": CATEGORIES_777,
        "total_questions": 140,
    }


@router.get("/questions")
async def get_all_questions():
    """Return all 140 questions with category metadata and emotional state capture prompts."""
    return {
        "success": True,
        "framework": "777",
        "total": len(LEGACY_QUESTIONS_777),
        "categories": CATEGORIES_777,
        "questions": [
            {
                "id": q["id"],
                "category": q["category"],
                "category_id": q["cat_id"],
                "number_in_category": q["n"],
                "question": q["q"],
            }
            for q in LEGACY_QUESTIONS_777
        ],
        "emotional_state_capture": [
            {"id": "importance",   "question": "How important is this memory to you?",        "type": "scale_1_10"},
            {"id": "emotion",      "question": "What emotion do you associate with it?",       "type": "emotion_select", "options": EMOTION_OPTIONS},
            {"id": "expand",       "question": "Would you like to expand on this memory?",     "type": "yes_no"},
            {"id": "valence",      "question": "Is this memory positive, negative, or mixed?", "type": "choice", "options": ["Positive","Negative","Mixed"]},
            {"id": "frequency",    "question": "How often do you think about this memory?",    "type": "choice", "options": ["Daily","Weekly","Monthly","Rarely","First time"]},
            {"id": "who_involved", "question": "Who else was involved in this memory?",        "type": "text_short"},
            {"id": "defining",     "question": "Is this a defining moment of your life?",      "type": "yes_no"},
        ],
    }


@router.get("/questions/{category_id}")
async def get_questions_by_category(category_id: int):
    """Return questions for a specific category (1-7)."""
    if category_id < 1 or category_id > 7:
        raise HTTPException(400, "Category ID must be 1-7")
    cat = next((c for c in CATEGORIES_777 if c["id"] == category_id), None)
    questions = [q for q in LEGACY_QUESTIONS_777 if q["cat_id"] == category_id]
    return {
        "success": True,
        "category": cat,
        "questions": [{"id": q["id"], "number": q["n"], "question": q["q"]} for q in questions],
        "count": len(questions),
    }


@router.post("/ai-followup")
async def generate_ai_followup(req: AIFollowUpRequest):
    """
    AI-driven deep follow-up question generation.
    Detects emotional triggers in the transcript and generates a personalized
    follow-up that digs deeper into the specific story the person shared.
    """
    if not OPENAI_API_KEY:
        return {"success": False, "error": "OpenAI not configured"}

    # Detect triggers
    triggers = detect_follow_up_triggers(req.transcript)
    emotion = req.emotional_state.get("emotion", "") if req.emotional_state else ""
    importance = req.emotional_state.get("importance", 5) if req.emotional_state else 5
    is_defining = req.emotional_state.get("is_defining_moment", False) if req.emotional_state else False

    # Build prompt
    system_prompt = """You are the Heavenly Eternal Echo™ AI Legacy Interviewer.
Your purpose is to help people capture their deepest, most meaningful life stories.
You generate ONE powerful follow-up question that digs deeper into what they just shared.

Rules:
- Ask about ONE specific detail, emotion, or person they mentioned
- Be warm, gentle, and reverential — this is sacred storytelling
- If they mentioned trauma, grief, faith, or transformation — go deeper
- Never ask multiple questions at once
- Make the question feel personal to EXACTLY what they said
- Keep it under 25 words
- Do NOT start with "Can you" — start with What, Who, How, Tell me, Describe, or Walk me through"""

    user_prompt = f"""Original question: {req.question_text}
Category: {req.category}
What they said: "{req.transcript[:500]}"
Emotion detected: {emotion}
Importance (1-10): {importance}
Defining moment: {is_defining}
Trigger patterns detected: {', '.join(triggers) if triggers else 'none'}

Generate one deep follow-up question:"""

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 80,
                    "temperature": 0.8,
                },
            )
        if r.status_code == 200:
            followup = r.json()["choices"][0]["message"]["content"].strip().strip('"')
            return {
                "success": True,
                "followup_question": followup,
                "triggers_detected": triggers,
                "should_follow_up": bool(triggers or int(importance or 0) >= 7 or is_defining),
            }
        return {"success": False, "error": f"OpenAI {r.status_code}"}
    except Exception as e:
        logger.error("AI followup error: %s", e)
        return {"success": False, "error": str(e)}


@router.post("/recording/save")
async def save_recording(req: SaveRecordingRequest):
    """Save a completed interview answer with full emotional state capture."""
    try:
        record_id = str(uuid.uuid4())

        # Auto-detect follow-up triggers if not provided
        triggers = req.ai_followup_triggered or detect_follow_up_triggers(req.transcript)

        row = {
            "id": record_id,
            "user_id": req.user_id,
            "profile_id": req.profile_id,
            "question_index": req.question_id,
            "question_text": req.question_text,
            "category": req.category,
            "transcript": req.transcript,
            "audio_url": req.audio_url,
            "storage_path": req.storage_path,
            "duration_sec": req.duration_sec,
            "file_size_bytes": req.file_size_bytes,
            "upload_success": True,
            "created_at": _now(),
        }

        # Store emotional state as JSON in notes column (no schema change needed)
        if req.emotional_state:
            es = req.emotional_state.dict(exclude_none=True)
            es["triggers_detected"] = triggers
            if req.ai_followup_question:
                es["ai_followup_question"] = req.ai_followup_question

        saved = await _sb_insert("hee_recordings", row)

        return {
            "success": True,
            "id": record_id,
            "question_id": req.question_id,
            "category": req.category,
            "transcript_length": len(req.transcript),
            "duration_sec": req.duration_sec,
            "triggers_detected": triggers,
            "should_follow_up": bool(
                triggers or
                (req.emotional_state and req.emotional_state.importance and req.emotional_state.importance >= 7) or
                (req.emotional_state and req.emotional_state.is_defining_moment)
            ),
        }
    except Exception as e:
        logger.error("save_recording error: %s", e)
        raise HTTPException(500, str(e))


@router.post("/recording/save-audio")
async def save_recording_with_audio(
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    question_id: int = Form(...),
    question_text: str = Form(...),
    category: str = Form(...),
    transcript: str = Form(""),
    duration_sec: float = Form(0),
    audio: UploadFile = File(None),
):
    """Save audio file + transcript for a recording."""
    try:
        record_id = str(uuid.uuid4())
        audio_url = None
        storage_path = None
        file_size = 0

        if audio:
            audio_bytes = await audio.read()
            file_size = len(audio_bytes)
            ext = audio.filename.split(".")[-1] if "." in (audio.filename or "") else "webm"
            storage_path = f"hee/{user_id}/{record_id}.{ext}"

            # Upload to Supabase Storage
            try:
                async with httpx.AsyncClient(timeout=60) as c:
                    r = await c.post(
                        f"{SUPABASE_URL}/storage/v1/object/hee-audio/{storage_path}",
                        headers={
                            "apikey": SUPABASE_KEY,
                            "Authorization": f"Bearer {SUPABASE_KEY}",
                            "Content-Type": audio.content_type or "audio/webm",
                            "x-upsert": "true",
                        },
                        content=audio_bytes,
                    )
                if r.status_code in (200, 201):
                    audio_url = f"{SUPABASE_URL}/storage/v1/object/public/hee-audio/{storage_path}"
            except Exception as upload_err:
                logger.warning("Audio upload failed: %s", upload_err)

        triggers = detect_follow_up_triggers(transcript)
        row = {
            "id": record_id,
            "user_id": user_id,
            "question_index": question_id,
            "question_text": question_text,
            "category": category,
            "transcript": transcript,
            "audio_url": audio_url,
            "storage_path": storage_path,
            "duration_sec": duration_sec,
            "file_size_bytes": file_size,
            "upload_success": audio_url is not None,
            "created_at": _now(),
        }

        await _sb_insert("hee_recordings", row)

        return {
            "success": True,
            "id": record_id,
            "audio_url": audio_url,
            "duration_sec": duration_sec,
            "triggers_detected": triggers,
        }
    except Exception as e:
        logger.error("save_recording_with_audio error: %s", e)
        raise HTTPException(500, str(e))


@router.get("/recordings/{user_id}")
async def get_recordings(user_id: str):
    """Get all recordings for a user, grouped by category."""
    rows = await _sb_select("hee_recordings", {"user_id": user_id}, limit=500)

    # Group by category
    by_category = {}
    for row in rows:
        cat = row.get("category", "Unknown")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(row)

    # Build answered question IDs
    answered_ids = [r["question_index"] for r in rows if r.get("question_index")]
    total_duration = sum(r.get("duration_sec", 0) for r in rows)

    return {
        "success": True,
        "total": len(rows),
        "total_questions": 140,
        "answered_count": len(set(answered_ids)),
        "completion_pct": round(len(set(answered_ids)) / 140 * 100, 1),
        "total_duration_sec": total_duration,
        "total_duration_min": round(total_duration / 60, 1),
        "recordings": rows,
        "by_category": by_category,
        "answered_question_ids": list(set(answered_ids)),
    }


@router.get("/progress/{user_id}")
async def get_progress(user_id: str):
    """Get progress, clone readiness, and emotional fingerprint summary."""
    rows = await _sb_select("hee_recordings", {"user_id": user_id}, limit=500)
    total_sec = sum(r.get("duration_sec", 0) for r in rows)
    answered = list(set(r["question_index"] for r in rows if r.get("question_index")))

    # Category breakdown
    cat_progress = {}
    for cat in CATEGORIES_777:
        cat_answers = [r for r in rows if r.get("category") == cat["name"]]
        cat_progress[cat["name"]] = {
            "answered": len(cat_answers),
            "total": 20,
            "pct": round(len(cat_answers) / 20 * 100, 1),
            "icon": cat["icon"],
            "color": cat["color"],
        }

    clone_status = await _sb_select("hee_voice_clones", {"user_id": user_id}, limit=1)

    return {
        "success": True,
        "total_recordings": len(rows),
        "answered_questions": len(answered),
        "total_questions": 140,
        "completion_pct": round(len(answered) / 140 * 100, 1),
        "total_duration_sec": total_sec,
        "total_duration_min": round(total_sec / 60, 1),
        "clone_ready": total_sec >= MIN_CLONE_SECONDS,
        "clone_recommended": total_sec >= RECOMMENDED_SECONDS,
        "min_clone_seconds": MIN_CLONE_SECONDS,
        "recommended_clone_seconds": RECOMMENDED_SECONDS,
        "clone_status": clone_status[0] if clone_status else None,
        "category_progress": cat_progress,
    }


@router.delete("/recording/{record_id}")
async def delete_recording(record_id: str):
    ok = await _sb_delete("hee_recordings", {"id": record_id})
    return {"success": ok}


@router.post("/clone")
async def create_voice_clone(req: CloneRequest):
    """Send all recordings to ElevenLabs to create a voice clone."""
    if not ELEVENLABS_API_KEY:
        raise HTTPException(503, "ElevenLabs not configured")

    recordings = await _sb_select("hee_recordings", {"user_id": req.user_id}, limit=500)
    if not recordings:
        raise HTTPException(400, "No recordings found for this user")

    total_sec = sum(r.get("duration_sec", 0) for r in recordings)
    if total_sec < MIN_CLONE_SECONDS:
        raise HTTPException(400, f"Need at least {MIN_CLONE_SECONDS/60:.0f} minutes of audio. Have {total_sec/60:.1f} minutes.")

    # Update clone status to processing
    existing = await _sb_select("hee_voice_clones", {"user_id": req.user_id}, limit=1)
    clone_id = existing[0]["id"] if existing else str(uuid.uuid4())

    clone_row = {
        "id": clone_id,
        "user_id": req.user_id,
        "profile_id": req.profile_id,
        "status": "processing",
        "recording_count": len(recordings),
        "total_seconds": total_sec,
        "updated_at": _now(),
    }

    if existing:
        await _sb_update("hee_voice_clones", {"user_id": req.user_id}, clone_row)
    else:
        clone_row["created_at"] = _now()
        await _sb_insert("hee_voice_clones", clone_row)

    # Collect audio files with URLs
    audio_urls = [r["audio_url"] for r in recordings if r.get("audio_url")]
    if not audio_urls:
        raise HTTPException(400, "No audio files found — recordings may be text-only")

    # Build ElevenLabs IVC voice from URLs
    try:
        voice_name = req.voice_name or f"Legacy Voice {req.user_id[:8]}"
        files = []
        async with httpx.AsyncClient(timeout=60) as c:
            for url in audio_urls[:25]:  # ElevenLabs max 25 samples
                try:
                    ar = await c.get(url, timeout=30)
                    if ar.status_code == 200:
                        fname = url.split("/")[-1]
                        files.append(("files", (fname, ar.content, "audio/webm")))
                except Exception:
                    continue

        if not files:
            raise HTTPException(400, "Could not download audio files for cloning")

        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{ELEVENLABS_BASE}/voices/add",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                data={"name": voice_name, "description": "Heavenly Eternal Echo™ Legacy Voice"},
                files=files,
            )

        if r.status_code in (200, 201):
            voice_data = r.json()
            voice_id = voice_data.get("voice_id", "")
            await _sb_update("hee_voice_clones", {"user_id": req.user_id}, {
                "status": "ready",
                "elevenlabs_voice_id": voice_id,
                "voice_name": voice_name,
                "updated_at": _now(),
            })
            return {"success": True, "voice_id": voice_id, "voice_name": voice_name, "status": "ready"}
        else:
            err = r.text[:200]
            await _sb_update("hee_voice_clones", {"user_id": req.user_id}, {
                "status": "failed", "last_error": err, "updated_at": _now()
            })
            raise HTTPException(500, f"ElevenLabs error: {err}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("clone error: %s", e)
        await _sb_update("hee_voice_clones", {"user_id": req.user_id}, {
            "status": "failed", "last_error": str(e), "updated_at": _now()
        })
        raise HTTPException(500, str(e))


@router.get("/clone/{user_id}")
async def get_clone_status(user_id: str):
    rows = await _sb_select("hee_voice_clones", {"user_id": user_id}, limit=1)
    if not rows:
        return {"success": True, "status": "not_started", "voice_id": None}
    return {"success": True, **rows[0]}


@router.post("/test-clone")
async def test_clone_voice(req: TestCloneRequest):
    """Generate TTS audio using the user's cloned voice."""
    if not ELEVENLABS_API_KEY:
        raise HTTPException(503, "ElevenLabs not configured")

    voice_id = req.voice_id
    if not voice_id:
        rows = await _sb_select("hee_voice_clones", {"user_id": req.user_id}, limit=1)
        if not rows or not rows[0].get("elevenlabs_voice_id"):
            raise HTTPException(404, "No voice clone found for this user")
        voice_id = rows[0]["elevenlabs_voice_id"]

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                json={"text": req.text, "model_id": "eleven_monolingual_v1",
                      "voice_settings": {"stability": 0.75, "similarity_boost": 0.85}},
            )
        if r.status_code == 200:
            import base64
            return {"success": True, "audio_base64": base64.b64encode(r.content).decode(), "voice_id": voice_id}
        raise HTTPException(500, f"ElevenLabs TTS error: {r.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/admin/debug")
async def admin_debug():
    """Founder debug panel — system status."""
    recordings_count = 0
    clones_count = 0
    try:
        recs = await _sb_select("hee_recordings", limit=1)
        clones = await _sb_select("hee_voice_clones", limit=1)
        recordings_count = "ok"
        clones_count = "ok"
    except Exception as e:
        recordings_count = str(e)

    return {
        "success": True,
        "framework": "777",
        "total_questions": len(LEGACY_QUESTIONS_777),
        "categories": len(CATEGORIES_777),
        "supabase_tables": {"hee_recordings": recordings_count, "hee_voice_clones": clones_count},
        "elevenlabs": bool(ELEVENLABS_API_KEY),
        "openai": bool(OPENAI_API_KEY),
    }
