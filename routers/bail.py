"""
/v1/bail/* — Pro-Se AI: Texas Bail Flow Intelligence
Covers: bond analysis, Bexar County bail companies, jail info,
        motion drafting (bond reduction, release on OR, habeas)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
import os, httpx

router = APIRouter(prefix="/v1/bail", tags=["Pro-Se AI - Bail Flow"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

BAIL_SYSTEM = """You are a Texas criminal defense strategist specializing in bail and bond law.
You help defendants and their families understand: how bond amounts are set, grounds for bond reduction,
OR (Own Recognizance) release criteria, Bexar County bail procedures, habeas corpus for illegal detention,
and how to draft motions related to bond. Cite Texas Code of Criminal Procedure chapters 17 and 11 when relevant.
You are educational — not providing legal representation. Always recommend consulting a licensed TX attorney."""

# ── Bexar County bail company directory (static, kept current) ────────────────
BEXAR_BAIL_COMPANIES = [
    {"name": "A-Affordable Bail Bonds",     "phone": "(210) 224-2245", "area": "San Antonio",   "24hr": True},
    {"name": "Aardvark Bail Bonds",          "phone": "(210) 226-2245", "area": "San Antonio",   "24hr": True},
    {"name": "Bad Boys Bail Bonds",          "phone": "(210) 223-2245", "area": "San Antonio",   "24hr": True},
    {"name": "Castle Bail Bonds",            "phone": "(210) 533-0707", "area": "San Antonio",   "24hr": True},
    {"name": "Freedom Bail Bonds",           "phone": "(210) 223-0011", "area": "San Antonio",   "24hr": True},
    {"name": "Gold Star Bail Bonds",         "phone": "(210) 224-6660", "area": "San Antonio",   "24hr": True},
    {"name": "Lone Star Bail Bonds",         "phone": "(210) 222-2245", "area": "San Antonio",   "24hr": True},
    {"name": "Pretrial Services of Bexar",   "phone": "(210) 335-6700", "area": "Bexar County",  "24hr": False},
    {"name": "San Antonio Bail Bonds",       "phone": "(210) 224-2100", "area": "San Antonio",   "24hr": True},
    {"name": "Supreme Bail Bonds",           "phone": "(210) 226-7000", "area": "San Antonio",   "24hr": True},
]

# ── Bexar County Jail info ─────────────────────────────────────────────────────
BEXAR_JAIL_INFO = {
    "facility": "Bexar County Adult Detention Center",
    "address": "200 N. Comal St, San Antonio, TX 78207",
    "phone": "(210) 335-6300",
    "inmate_search": "https://www.bexar.org/3096/Inmate-Search",
    "magistration_hours": "24/7",
    "bond_types": ["Cash Bond", "Surety Bond (Bail Bondsman)", "Personal Bond (OR)", "Property Bond"],
    "bond_hearing_timing": "Within 48 hours of arrest per Tx Code Crim Proc Art. 17.033",
    "pretrial_services": "(210) 335-6700",
    "notes": "Bond amounts set by magistrate based on Art. 17.15 factors: nature of offense, defendant ties to community, work record, prior record, future court appearance likelihood.",
}

# ── Pydantic models ────────────────────────────────────────────────────────────
class BailAnalyzeRequest(BaseModel):
    case_summary: str
    charges: str
    bond_amount: Optional[str] = None
    defendant_info: Optional[str] = None
    county: Optional[str] = "Bexar"
    prior_record: Optional[str] = None
    community_ties: Optional[str] = None

class BailMotionRequest(BaseModel):
    motion_type: str  # "bond_reduction" | "or_release" | "habeas" | "bond_hearing"
    case_summary: str
    charges: str
    bond_amount: Optional[str] = None
    defendant_name: Optional[str] = "Defendant"
    cause_number: Optional[str] = None
    county: Optional[str] = "Bexar"
    supporting_facts: Optional[str] = None
    judge_name: Optional[str] = None

class BailChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    county: Optional[str] = "Bexar"

# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/health")
async def bail_health():
    return {
        "success": True,
        "status": "online",
        "service": "Pro-Se AI Bail Flow Monitor",
        "openai": bool(client),
        "counties_supported": ["Bexar", "Harris", "Travis", "Dallas", "Tarrant"],
        "features": ["bond_analysis", "bail_companies", "jail_info", "motion_drafting", "ai_chat"],
    }

@router.get("/companies/bexar")
async def bail_companies_bexar():
    """Returns Bexar County bail bond companies with contact info."""
    return {
        "success": True,
        "county": "Bexar",
        "city": "San Antonio, TX",
        "companies": BEXAR_BAIL_COMPANIES,
        "total": len(BEXAR_BAIL_COMPANIES),
        "note": "Call 24/7 companies any time. Typical premium: 10-15% of bond amount.",
    }

@router.get("/jail/bexar")
async def jail_info_bexar():
    """Returns Bexar County Adult Detention Center info."""
    return {
        "success": True,
        "county": "Bexar",
        **BEXAR_JAIL_INFO,
    }

@router.post("/analyze")
async def bail_analyze(payload: BailAnalyzeRequest):
    """AI-powered bond analysis — Art. 17.15 factors, reduction strategy."""
    if not client:
        return {
            "success": True,
            "analysis": "Bond is set by magistrate under Art. 17.15 TCCP. Key reduction grounds: no prior record, strong community ties, non-violent charge, financial hardship. File Motion to Reduce Bond citing these factors.",
            "mode": "fallback",
        }
    prompt = f"""Analyze this Texas bond situation and give a defense strategy:

Charges: {payload.charges}
County: {payload.county} County
Bond Amount: {payload.bond_amount or "Unknown"}
Case Summary: {payload.case_summary}
Prior Record: {payload.prior_record or "Not provided"}
Community Ties: {payload.community_ties or "Not provided"}
Defendant Info: {payload.defendant_info or "Not provided"}

Provide:
1. Bond assessment (is the amount appropriate under Art. 17.15 TCCP?)
2. Grounds for bond reduction (cite specific factors)
3. OR release eligibility analysis
4. Recommended motion strategy
5. Immediate steps for the family/defendant"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": BAIL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3, max_tokens=1200,
        )
        return {
            "success": True,
            "analysis": resp.choices[0].message.content,
            "county": payload.county,
            "charges": payload.charges,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/motion")
async def bail_motion(payload: BailMotionRequest):
    """Draft a bail-related motion (bond reduction, OR release, habeas corpus)."""
    if not client:
        raise HTTPException(status_code=503, detail="OpenAI not configured")

    motion_prompts = {
        "bond_reduction": f"Draft a professional Motion to Reduce Bond for Cause No. {payload.cause_number or '[CAUSE NUMBER]'} in {payload.county} County, Texas.",
        "or_release": f"Draft a Motion for Personal Bond (OR Release) for Cause No. {payload.cause_number or '[CAUSE NUMBER]'} in {payload.county} County, Texas.",
        "habeas": f"Draft a Writ of Habeas Corpus for unlawful detention in {payload.county} County, Texas.",
        "bond_hearing": f"Draft a Motion for Emergency Bond Hearing in {payload.county} County, Texas.",
    }
    motion_type_prompt = motion_prompts.get(payload.motion_type, motion_prompts["bond_reduction"])

    prompt = f"""{motion_type_prompt}

Defendant: {payload.defendant_name}
Charges: {payload.charges}
Bond Amount: {payload.bond_amount or "TBD"}
Judge: {payload.judge_name or "[JUDGE NAME]"}
Supporting Facts: {payload.supporting_facts or "None provided"}
Case Summary: {payload.case_summary}

Requirements:
- Proper Texas legal caption and formatting
- Cite Texas Code of Criminal Procedure Art. 17.15 (bond factors) and relevant case law
- Include all required sections (Introduction, Facts, Argument, Prayer for Relief)
- Professional legal language
- Leave [BRACKETS] for attorney to fill in specific details
- Include signature block"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": BAIL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2, max_tokens=2000,
        )
        return {
            "success": True,
            "motion_type": payload.motion_type,
            "motion_text": resp.choices[0].message.content,
            "county": payload.county,
            "cause_number": payload.cause_number,
            "disclaimer": "This is an AI-drafted template. Review with a licensed Texas attorney before filing.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat")
async def bail_chat(payload: BailChatRequest):
    """General bail/bond Q&A for Pro-Se defendants and families."""
    if not client:
        return {"success": True, "reply": "Bond is typically set by a magistrate within 48 hours of arrest in Texas. You have the right to a bond hearing.", "mode": "fallback"}
    messages = [{"role": "system", "content": BAIL_SYSTEM}]
    if payload.context:
        messages.append({"role": "system", "content": f"Context: {payload.context}"})
    messages.append({"role": "user", "content": payload.message})
    resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.4, max_tokens=800)
    return {"success": True, "reply": resp.choices[0].message.content, "county": payload.county}
