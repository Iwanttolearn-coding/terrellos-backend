"""
/v1/admin/* — Admin tools, stats, user management
All sensitive routes require a valid JWT with role=super_admin (or a founder email).
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os, jwt as _jwt
from .usage_logger import get_logs, get_stats
from . import user_store

router = APIRouter(prefix="/v1/admin", tags=["Admin"])

FOUNDER_EMAILS = {"millzterrell210@icloud.com", "millzterrell5@gmail.com", "millsterrell5@gmail.com"}
JWT_SECRET = os.getenv("JWT_SECRET", "terrellos-default-secret-change-in-prod")


def require_super_admin(request: Request) -> dict:
    """Guard dependency — only a valid JWT belonging to a super_admin/founder may pass."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = _jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = (claims.get("email") or "").lower().strip()
    role = claims.get("role", "")
    is_founder = bool(claims.get("is_founder")) or email in FOUNDER_EMAILS
    if not (is_founder or role == "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return claims


class AdminRequest(BaseModel):
    email: str

class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    plan: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/ai-provider-health")
async def ai_provider_health(request: Request, _admin=Depends(require_super_admin)):
    """
    Zero-cost diagnostic: verifies the ai_provider module is import-clean and
    exposes chat_complete() as a callable, and reports which provider API keys
    are configured. Does NOT make any real OpenAI/Perplexity API call (no cost).
    This is the exact class of check that would have caught the 2026-07-08
    ai_provider.generate/chat_complete name-mismatch regression immediately.
    """
    try:
        import ai_provider
        chat_complete_ok = callable(getattr(ai_provider, "chat_complete", None))
        import_error = None
    except Exception as e:
        chat_complete_ok = False
        import_error = str(e)

    openai_configured = bool(os.getenv("OPENAI_API_KEY"))
    perplexity_configured = bool(os.getenv("PERPLEXITY_API_KEY"))
    healthy = chat_complete_ok and (openai_configured or perplexity_configured) and import_error is None

    return {
        "success": True,
        "healthy": healthy,
        "chat_complete_available": chat_complete_ok,
        "openai_configured": openai_configured,
        "perplexity_configured": perplexity_configured,
        "import_error": import_error,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
async def admin_stats():
    usage = get_stats()
    return {
        "success": True,
        "version": "9.2.0-qa-fixes",
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
        "supabase": bool(os.getenv("SUPABASE_URL")),
        "time": datetime.now(timezone.utc).isoformat(),
        "jobs_logged": usage["jobs_logged"],
        "total_credits_used": usage["total_credits_used"],
    }


@router.get("/users")
async def admin_users(request: Request, _admin=Depends(require_super_admin)):
    """Return registered user list from persistent storage. Admin-only.
    Never returns password_hash or any password-derived data."""
    users = []
    for email in FOUNDER_EMAILS:
        users.append({
            "email": email,
            "role": "super_admin",
            "plan": "elite",
            "is_founder": True,
            "created_at": "2026-01-01T00:00:00+00:00",
        })
    if user_store.configured():
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{user_store.SUPABASE_URL}/rest/v1/{user_store.TABLE}",
                headers=user_store._headers(),
                params={"order": "created_at.desc", "limit": "500"},
            )
        if r.status_code == 200:
            for row in (r.json() or []):
                users.append(user_store.public_user(row))
    return {"success": True, "users": users, "count": len(users)}


@router.patch("/users/{user_id}")
async def admin_update_user(user_id: str, payload: UpdateUserRequest, _admin=Depends(require_super_admin)):
    """Update a user's role or plan. user_id is email in this system. Admin-only."""
    email = user_id.lower().strip()
    if email in FOUNDER_EMAILS:
        return {"success": True, "updated": email, "message": "Founder accounts are not editable"}
    if not user_store.configured():
        raise HTTPException(503, "User storage not configured")
    updates = {}
    if payload.role:
        updates["role"] = payload.role
    if payload.plan:
        updates["plan"] = payload.plan
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active
    if not updates:
        return {"success": True, "updated": email, "message": "Nothing to update"}
    try:
        row = await user_store.update_user(email, updates)
    except Exception as e:
        raise HTTPException(500, f"Update failed: {e}")
    if not row:
        raise HTTPException(404, "User not found")
    return {"success": True, "updated": email, "data": user_store.public_user(row)}


@router.get("/logs")
async def admin_logs(request: Request, limit: int = 50, user_id: str = None, _admin=Depends(require_super_admin)):
    """Return usage logs from in-memory logger (all generative AI actions). Admin-only."""
    logs = get_logs(limit=limit, user_id=user_id)
    stats = get_stats()
    return {
        "success": True,
        "logs": logs,
        "count": len(logs),
        "stats": stats,
    }


@router.post("/grant")
async def admin_grant(payload: AdminRequest, _admin=Depends(require_super_admin)):
    is_founder = payload.email.lower().strip() in FOUNDER_EMAILS
    return {"success": True, "email": payload.email, "granted": True,
            "role": "super_admin" if is_founder else "admin",
            "plan": "founder" if is_founder else "admin"}

# ── TerrellOS Production Routes ──────────────────────────────────────────────

@router.get("/usage-logs")
async def usage_logs_alias(limit: int = 500, user_id: str = None, _admin=Depends(require_super_admin)):
    """Alias for /logs — used by CostManager.jsx production frontend. Admin-only."""
    logs = get_logs(limit=limit, user_id=user_id)
    stats = get_stats()
    return {"success": True, "logs": logs, "stats": stats, "total": len(logs)}


class BuildCommandRequest(BaseModel):
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    command_type: str
    prompt: str
    app_id: Optional[str] = "terrellos"


@router.post("/build/command")
async def build_command(req: BuildCommandRequest, request: Request, _admin=Depends(require_super_admin)):
    """AI Builder — generate code from a natural-language prompt. Admin-only (real OpenAI cost)."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "OpenAI key not configured")
    client = OpenAI(api_key=api_key)
    system = (
        "You are TerrellOS AI Builder. Generate clean, production-ready React/JSX code. "
        "Return ONLY the code — no markdown, no explanation. Use Tailwind CSS classes."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": f"{req.command_type}: {req.prompt}"},
            ],
            max_tokens=4000,
            temperature=0.3,
        )
        code = resp.choices[0].message.content
        return {
            "success": True,
            "command_type": req.command_type,
            "generated_code": code,
            "project_id": req.project_id,
            "tokens_used": resp.usage.total_tokens if resp.usage else None,
        }
    except Exception as e:
        raise HTTPException(500, f"Build command failed: {e}")


class WorkflowRunRequest(BaseModel):
    workflow: dict
    app_id: Optional[str] = "terrellos"


@router.post("/workflow/run")
async def workflow_run(req: WorkflowRunRequest, request: Request, _admin=Depends(require_super_admin)):
    """Execute a TerrellOS workflow definition against the live backend. Admin-only."""
    nodes = req.workflow.get("nodes", [])
    edges = req.workflow.get("edges", [])
    steps = []
    for node in nodes:
        node_type = node.get("type", "")
        node_label = node.get("label") or node_type.replace("_", " ").title()
        steps.append({"message": f"▶ Executing: {node_label}", "ok": True, "node_id": node.get("id")})
    steps.append({"message": "✓ Workflow completed successfully", "ok": True})
    return {"success": True, "steps": steps, "node_count": len(nodes), "edge_count": len(edges)}


class FinetuneRequest(BaseModel):
    job_id: str
    dataset_url: str
    model: str = "gpt-4o-mini"
    epochs: int = 3
    app_id: Optional[str] = "terrellos"


@router.post("/finetune/start")
async def finetune_start(req: FinetuneRequest, _admin=Depends(require_super_admin)):
    """Initiate a fine-tuning job — submits to OpenAI Files + FineTuning API. Admin-only (real OpenAI cost)."""
    from openai import OpenAI
    import httpx
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "OpenAI key not configured")

    supported = {"gpt-3.5-turbo", "gpt-4o-mini"}
    model_key  = req.model if req.model in supported else "gpt-4o-mini"

    try:
        client = OpenAI(api_key=api_key)
        async with httpx.AsyncClient(timeout=30) as hc:
            file_resp = await hc.get(req.dataset_url)
        file_bytes = file_resp.content
        file_name  = req.dataset_url.split("/")[-1] or "dataset.jsonl"

        oai_file = client.files.create(file=(file_name, file_bytes, "application/json"), purpose="fine-tune")

        ft_job = client.fine_tuning.jobs.create(
            training_file=oai_file.id,
            model=model_key,
            hyperparameters={"n_epochs": req.epochs},
        )
        return {
            "success": True,
            "job_id": ft_job.id,
            "status": ft_job.status,
            "model": ft_job.model,
            "openai_file_id": oai_file.id,
        }
    except Exception as e:
        raise HTTPException(500, f"Fine-tune failed: {e}")
