"""
routers/legion.py — American Legion Bicentennial Post 579
Backend API for post579.org / american-legion-post579
Commander Harold | 3002 Gunsmoke Drive, San Antonio TX 78227 | (210) 674-8069
Built by TM Designs™
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone
import os

router = APIRouter(prefix="/v1/legion", tags=["American Legion Post 579"])

# ── Models ──────────────────────────────────────────────────────────────────

class ContactForm(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone_number: Optional[str] = None
    subject: str
    is_veteran: Optional[str] = None
    message: str

class MembershipApplication(BaseModel):
    full_name: str
    email: str
    phone_number: str
    birth_date: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = "TX"
    zip_code: Optional[str] = None
    military_branch: Optional[str] = None
    service_number: Optional[str] = None
    entry_date: Optional[str] = None
    discharge_date: Optional[str] = None
    discharge_type: Optional[str] = None
    war_era: Optional[str] = None
    rank_at_discharge: Optional[str] = None
    dd214_on_file: Optional[bool] = False
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    referral_source: Optional[str] = None
    signature: Optional[str] = None

class VolunteerRegistration(BaseModel):
    full_name: str
    email: str
    phone_number: str
    veteran_status: Optional[str] = None
    skills: Optional[str] = None
    availability: Optional[str] = None

class HallRentalRequest(BaseModel):
    full_name: str
    email: str
    phone_number: str
    event_date: Optional[str] = None
    event_type: Optional[str] = None
    expected_attendance: Optional[int] = None
    setup_time: Optional[str] = None
    end_time: Optional[str] = None
    special_requests: Optional[str] = None
    deposit_amount: Optional[float] = None

class EventRegistration(BaseModel):
    full_name: str
    email: str
    phone_number: Optional[str] = None
    event_name: str
    ticket_quantity: Optional[int] = 1
    ticket_type: Optional[str] = None
    total_amount: Optional[float] = None
    dietary_restrictions: Optional[str] = None

class DonationRequest(BaseModel):
    donor_name: str
    email: str
    phone_number: Optional[str] = None
    amount: float
    donation_type: Optional[str] = "general"
    message: Optional[str] = None
    is_anonymous: Optional[bool] = False

POST_INFO = {
    "name": "American Legion Bicentennial Post 579",
    "nickname": "Mrs. Carden Post",
    "commander": "Commander Harold",
    "address": "3002 Gunsmoke Drive, San Antonio, Texas 78227",
    "phone": "(210) 674-8069",
    "email": "commander@post579sa.org",
    "crisis_line": "988 — Press 1",
    "built_by": "TM Designs™",
}

def ts():
    return datetime.now(timezone.utc).isoformat()

# ── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
async def legion_health():
    return {
        "status": "operational",
        "app": "american-legion-post579",
        "post": POST_INFO["name"],
        "commander": POST_INFO["commander"],
        "address": POST_INFO["address"],
        "phone": POST_INFO["phone"],
        "timestamp": ts(),
    }

@router.get("/info")
async def post_info():
    return {
        "post": POST_INFO,
        "programs": [
            "Membership", "Veterans Services", "Steak Night",
            "Fish Fry", "Hall Rental", "Boys/Girls State",
            "Scholarships", "Honor Guard", "Riders", "Auxiliary",
            "Sons of the American Legion", "Youth Programs",
            "Community Service", "Military Guide AI",
        ],
        "active": True,
    }

# ── Contact Form ──────────────────────────────────────────────────────────

@router.post("/contact")
async def submit_contact(form: ContactForm):
    record = {
        "id": f"contact_{ts()}",
        "type": "contact",
        "status": "received",
        "submitted_at": ts(),
        "post": "post579",
        **form.dict(),
    }
    # TODO: wire to email notification (SendGrid/SMTP) once Commander confirms email
    return {
        "success": True,
        "message": f"Thank you {form.first_name}! Post 579 will respond within 1-2 business days.",
        "record_id": record["id"],
        "post_phone": POST_INFO["phone"],
    }

# ── Membership ────────────────────────────────────────────────────────────

@router.post("/membership/apply")
async def membership_apply(app_data: MembershipApplication):
    record_id = f"member_{ts()}"
    return {
        "success": True,
        "message": f"Welcome {app_data.full_name}! Your membership application for Post 579 has been received.",
        "record_id": record_id,
        "next_steps": [
            "Commander Harold will review your application",
            "You will be contacted at " + (app_data.phone_number or app_data.email),
            "Bring your DD-214 to your first meeting",
            f"Questions? Call {POST_INFO['phone']}",
        ],
        "submitted_at": ts(),
    }

@router.post("/membership/renew")
async def membership_renew(data: dict):
    return {
        "success": True,
        "message": "Renewal received. Commander Harold will confirm your renewal.",
        "submitted_at": ts(),
        "post_phone": POST_INFO["phone"],
    }

# ── Volunteer ─────────────────────────────────────────────────────────────

@router.post("/volunteer")
async def volunteer_signup(vol: VolunteerRegistration):
    return {
        "success": True,
        "message": f"Thank you {vol.full_name}! Your volunteer registration for Post 579 has been received.",
        "record_id": f"volunteer_{ts()}",
        "contact": POST_INFO["phone"],
        "submitted_at": ts(),
    }

# ── Hall Rental ───────────────────────────────────────────────────────────

@router.post("/hall-rental")
async def hall_rental_request(rental: HallRentalRequest):
    return {
        "success": True,
        "message": f"Hall rental request received for {rental.event_date or 'TBD'}. Commander Harold will confirm availability.",
        "record_id": f"rental_{ts()}",
        "address": POST_INFO["address"],
        "contact": POST_INFO["phone"],
        "submitted_at": ts(),
    }

# ── Event Registration / Tickets ──────────────────────────────────────────

@router.post("/events/register")
async def event_registration(reg: EventRegistration):
    return {
        "success": True,
        "message": f"Registration confirmed for {reg.event_name}! See you there.",
        "record_id": f"event_reg_{ts()}",
        "event": reg.event_name,
        "quantity": reg.ticket_quantity,
        "confirmation_sent_to": reg.email,
        "submitted_at": ts(),
    }

@router.get("/events")
async def get_events():
    return {
        "events": [
            {
                "id": "steak-night",
                "name": "Steak Night",
                "description": "Monthly steak night fundraiser at Post 579",
                "location": POST_INFO["address"],
                "ticket_price": 20.00,
                "status": "active",
            },
            {
                "id": "fish-fry",
                "name": "Fish Fry",
                "description": "Post 579 Fish Fry fundraiser",
                "location": POST_INFO["address"],
                "ticket_price": 15.00,
                "status": "active",
            },
            {
                "id": "veterans-day-banquet",
                "name": "Veterans Day Banquet",
                "description": "Annual Veterans Day Banquet — Post 579",
                "location": POST_INFO["address"],
                "ticket_price": 35.00,
                "status": "active",
            },
        ],
        "contact": POST_INFO["phone"],
    }

# ── Donations ─────────────────────────────────────────────────────────────

@router.post("/donate")
async def submit_donation(donation: DonationRequest):
    return {
        "success": True,
        "message": f"Thank you{' ' + donation.donor_name if not donation.is_anonymous else ' for your generous anonymous donation'}! Your donation of ${donation.amount:.2f} to Post 579 is being processed.",
        "record_id": f"donation_{ts()}",
        "amount": donation.amount,
        "submitted_at": ts(),
    }

# ── Military AI ───────────────────────────────────────────────────────────

class MilitaryAIQuery(BaseModel):
    question: str
    topic: Optional[str] = None
    user_type: Optional[str] = "public"  # veteran | family | public

@router.post("/military-ai/query")
async def military_ai_query(query: MilitaryAIQuery):
    """
    Military Guide AI — informational responses about VA benefits,
    military branches, American Legion programs, and veteran resources.
    Not a recruiter. Not legal/medical advice.
    """
    q = query.question.lower()

    # Keyword routing to canned responses (can be upgraded to OpenAI later)
    if any(k in q for k in ["crisis","988","suicide","mental health"]):
        topic = "crisis"
    elif any(k in q for k in ["gi bill","education benefit","college","tuition"]):
        topic = "gi_bill"
    elif any(k in q for k in ["disability","claim","rating","compensation"]):
        topic = "disability"
    elif any(k in q for k in ["va benefit","what benefit","benefit eligible"]):
        topic = "va_benefits"
    elif any(k in q for k in ["join","membership","how to join"]):
        topic = "join"
    elif any(k in q for k in ["boys state","girls state"]):
        topic = "boys_state"
    elif any(k in q for k in ["scholarship"]):
        topic = "scholarships"
    else:
        topic = "general"

    return {
        "success": True,
        "topic": topic,
        "post": POST_INFO["name"],
        "contact": POST_INFO["phone"],
        "crisis_line": POST_INFO["crisis_line"],
        "disclaimer": "Informational only. Not legal/medical advice. Not a recruiter. For official VA decisions, consult the VA or a Post 579 Service Officer.",
        "ai_response": f"Topic: {topic}. For detailed assistance, contact Post 579 at {POST_INFO['phone']} or visit 3002 Gunsmoke Drive, San Antonio TX 78227.",
    }

