"""
routers/vault.py — Universal Vault Save/List/Delete (rewritten for new schema)
Used by: Pastor AI, Kindred, TerrellOS, HEE, Pro-Se AI
Saves generated content (sermons, bible studies, discipleship tracks,
poems, legal docs, etc.) to Supabase saved_items table.
Uses httpx + direct Supabase REST — no supabase-py dependency.

Schema (public.saved_items):
  id uuid, user_id text, item_type text, title text, content text,
  metadata jsonb, created_at, updated_at
"""
import os, json, httpx
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

def _serialize_content(content: Any) -> str:
    """content column is TEXT now — stringify dicts/lists, pass strings through."""
    if isinstance(content, str):
        return content
    return json.dumps(content)

def _deserialize_item(item: dict) -> dict:
    """Try to parse content back into JSON for API responses; fall back to raw string."""
    raw = item.get("content")
    if isinstance(raw, str):
        try:
            item["content"] = json.loads(raw)
        except (ValueError, TypeError):
            pass
    return item

# ── Models ──────────────────────────────────────────────────────────────────
class VaultSaveRequest(BaseModel):
    user_id: str
    item_type: str
    title: Optional[str] = None
    content: Any
    metadata: Optional[dict] = {}

class VaultDeleteRequest(BaseModel):
    user_id: str
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
        "user_id":    req.user_id.strip(),
        "item_type":  req.item_type,
        "title":      req.title,
        "content":    _serialize_content(req.content),
        "metadata":   req.metadata or {},
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
    return {"success": True, "item_id": saved.get("id"),
            "title": req.title, "item_type": req.item_type}

# ── List ─────────────────────────────────────────────────────────────────────
@router.get("/list")
async def vault_list(
    user_id: str,
    item_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    params = {
        "user_id": f"eq.{user_id.strip()}",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if item_type: params["item_type"] = f"eq.{item_type}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers={**_headers(), "Prefer": "count=exact"},
            params=params,
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Vault list failed: {r.text[:200]}")
    items = [_deserialize_item(i) for i in (r.json() or [])]
    return {"success": True, "items": items, "total": len(items)}

# ── Get single ───────────────────────────────────────────────────────────────
@router.get("/item/{item_id}")
async def vault_get(item_id: str, user_id: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"id": f"eq.{item_id}", "user_id": f"eq.{user_id.strip()}"},
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True, "item": _deserialize_item(r.json()[0])}

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
                    "user_id": f"eq.{req.user_id.strip()}"},
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail=f"Delete failed: {r.text[:200]}")
    return {"success": True, "deleted": req.item_id}

# ── Count ─────────────────────────────────────────────────────────────────────
@router.get("/count")
async def vault_count(user_id: str, item_type: Optional[str] = None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    params = {"user_id": f"eq.{user_id.strip()}"}
    if item_type: params["item_type"] = f"eq.{item_type}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers={**_headers(), "Prefer": "count=exact"},
            params={**params, "limit": "0"},
        )
    count = int(r.headers.get("content-range", "0/0").split("/")[-1] or 0)
    return {"success": True, "count": count}
