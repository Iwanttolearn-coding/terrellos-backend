"""
routers/vault.py — Universal Vault Save/List/Delete
Used by: Pastor AI, Kindred, TerrellOS, HEE, Pro-Se AI
Saves generated content (sermons, bible studies, discipleship tracks,
poems, legal docs, etc.) to Supabase saved_items table.
Uses httpx + direct Supabase REST — no supabase-py dependency.
"""
import os, uuid, httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any, List

router = APIRouter(prefix="/v1/vault", tags=["vault"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
TABLE = "saved_items"

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def _now():
    return datetime.now(timezone.utc).isoformat()

# ── Models ──────────────────────────────────────────────────────────────────
class VaultSaveRequest(BaseModel):
    user_email: str
    type: str
    title: str
    content: Any
    app_id: Optional[str] = "pastor-ai-connect"
    tags: Optional[List[str]] = []
    notes: Optional[str] = ""
    metadata: Optional[dict] = {}

class VaultDeleteRequest(BaseModel):
    user_email: str
    item_id: str

# ── Health ───────────────────────────────────────────────────────────────────
@router.get("/health")
async def vault_health():
    return {
        "success": True,
        "status": "online",
        "service": "Universal Vault",
        "supabase": bool(SUPABASE_URL and SUPABASE_KEY),
    }

# ── Save ─────────────────────────────────────────────────────────────────────
@router.post("/save")
async def vault_save(req: VaultSaveRequest):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    record = {
        "id":         str(uuid.uuid4()),
        "user_email": req.user_email.lower().strip(),
        "type":       req.type,
        "title":      req.title,
        "content":    req.content if isinstance(req.content, dict) else {"data": req.content},
        "app_id":     req.app_id or "pastor-ai-connect",
        "tags":       req.tags or [],
        "notes":      req.notes or "",
        "metadata":   req.metadata or {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            json=record,
        )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"Vault save failed: {r.text[:200]}")
    data = r.json()
    saved = data[0] if isinstance(data, list) and data else record
    return {"success": True, "item_id": saved.get("id", record["id"]),
            "title": req.title, "type": req.type}

# ── List ─────────────────────────────────────────────────────────────────────
@router.get("/list")
async def vault_list(
    user_email: str,
    app_id: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    params = {
        "user_email": f"eq.{user_email.lower().strip()}",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if app_id: params["app_id"] = f"eq.{app_id}"
    if type:   params["type"]   = f"eq.{type}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers={**_headers(), "Prefer": "count=exact"},
            params=params,
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Vault list failed: {r.text[:200]}")
    items = r.json() or []
    return {"success": True, "items": items, "total": len(items)}

# ── Get single ───────────────────────────────────────────────────────────────
@router.get("/item/{item_id}")
async def vault_get(item_id: str, user_email: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"id": f"eq.{item_id}", "user_email": f"eq.{user_email.lower().strip()}"},
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True, "item": r.json()[0]}

# ── Delete ───────────────────────────────────────────────────────────────────
@router.delete("/delete")
async def vault_delete(req: VaultDeleteRequest):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.delete(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"id": f"eq.{req.item_id}",
                    "user_email": f"eq.{req.user_email.lower().strip()}"},
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail=f"Delete failed: {r.text[:200]}")
    return {"success": True, "deleted": req.item_id}

# ── Count ─────────────────────────────────────────────────────────────────────
@router.get("/count")
async def vault_count(user_email: str, app_id: Optional[str] = None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    params = {"user_email": f"eq.{user_email.lower().strip()}"}
    if app_id: params["app_id"] = f"eq.{app_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers={**_headers(), "Prefer": "count=exact"},
            params={**params, "limit": "0"},
        )
    count = int(r.headers.get("content-range", "0/0").split("/")[-1] or 0)
    return {"success": True, "count": count}


# ── Migrate (one-shot table creation) ────────────────────────────────────────
@router.post("/migrate")
async def vault_migrate(secret: str = ""):
    """One-shot: create saved_items table. Call once from admin only."""
    import os
    expected = os.getenv("ADMIN_SECRET", "terrellos-admin-2026")
    if secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # Use Supabase's pg meta API (available on all projects)
    create_sql = (
        "CREATE TABLE IF NOT EXISTS public.saved_items ("
        "id text PRIMARY KEY DEFAULT gen_random_uuid()::text,"
        "user_email text NOT NULL,"
        "type text NOT NULL,"
        "title text NOT NULL,"
        "content jsonb NOT NULL DEFAULT '{}',"
        "app_id text NOT NULL DEFAULT 'pastor-ai-connect',"
        "tags jsonb NOT NULL DEFAULT '[]',"
        "notes text NOT NULL DEFAULT '',"
        "metadata jsonb NOT NULL DEFAULT '{}',"
        "created_at timestamptz NOT NULL DEFAULT now(),"
        "updated_at timestamptz NOT NULL DEFAULT now()"
        ");"
        "CREATE INDEX IF NOT EXISTS idx_saved_items_user ON public.saved_items(user_email);"
        "CREATE INDEX IF NOT EXISTS idx_saved_items_app  ON public.saved_items(app_id);"
        "CREATE INDEX IF NOT EXISTS idx_saved_items_type ON public.saved_items(type);"
    )

    # Try Supabase pg meta API
    supabase_ref = SUPABASE_URL.replace("https://","").replace(".supabase.co","")
    headers_mgmt = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    results = {}

    # Method 1: pg meta
    async with httpx.AsyncClient(timeout=20) as client:
        r1 = await client.post(
            f"https://{supabase_ref}.supabase.co/pg/query",
            headers=headers_mgmt,
            json={"query": create_sql}
        )
        results["pg_query"] = r1.status_code

    # Method 2: rpc exec_sql if exists
    async with httpx.AsyncClient(timeout=20) as client:
        r2 = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
            headers={**headers_mgmt, "Prefer": "return=representation"},
            json={"sql": create_sql}
        )
        results["rpc_exec_sql"] = r2.status_code

    # Method 3: verify table exists now
    async with httpx.AsyncClient(timeout=10) as client:
        r3 = await client.get(
            f"{SUPABASE_URL}/rest/v1/saved_items?limit=1",
            headers=headers_mgmt
        )
        results["table_probe"] = r3.status_code
        table_exists = r3.status_code == 200

    return {
        "success": table_exists,
        "table_exists": table_exists,
        "methods_tried": results,
        "message": "saved_items table is ready" if table_exists else "Table creation attempted — check Supabase dashboard"
    }
