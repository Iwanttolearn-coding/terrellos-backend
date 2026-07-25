"""
routers/mailer.py — minimal transactional email sender via Resend HTTP API.
No SDK dependency, just httpx (already a project dependency).
"""
import os, httpx

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("MAIL_FROM", "Pastor AI <onboarding@resend.dev>")


def configured() -> bool:
    return bool(RESEND_API_KEY)


async def send_email(to: str, subject: str, html: str) -> bool:
    """Fire-and-log email send. Returns True on success, False (never raises) on failure
    so a flaky mail provider never breaks an auth flow."""
    if not configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            )
        return r.status_code in (200, 201, 202)
    except Exception:
        return False
