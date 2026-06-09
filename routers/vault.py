"""
routers/vault.py — Universal Vault Save/List/Delete
Used by: Pastor AI, Kindred, TerrellOS, HEE, Pro-Se AI
Saves any generated content (sermons, bible studies, discipleship tracks,
poems, legal docs, etc.) to Supabase saved_items table.
"""
import os, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from services.db import get_supabase

router = APIRouter(prefix="/v1/vault", tags=["vault"])

# ── Models ──────────────────────────────────────────────────────────────────
class VaultSaveRequest(BaseModel):
    user_email: str
    type: str                      # sermon | bible_study | discipleship | poem | legal | memo
    title: str
    content: Any                   # any JSON-serializable structure
    app_id: Optional[str] = "terrellos"
    tags: Optional[list] = []
    notes: Optional[str] = ""
    metadata: Optional[dict] = {}

class VaultDeleteRequest(BaseModel):
    user_email: str
    item_id: str

# ── Health ───────────────────────────────────────────────────────────────────
@router.get("/health")
async def vault_health():
    return {"success": True, "status": "online", "service": "Universal Vault",
            "supabase": bool(os.getenv("SUPABASE_URL"))}

# ── Save ─────────────────────────────────────────────────────────────────────
@router.post("/save")
async def vault_save(req: VaultSaveRequest):
    try:
        sb = get_supabase()
        record = {
            "id":         str(uuid.uuid4()),
            "user_email": req.user_email.lower().strip(),
            "type":       req.type,
            "title":      req.title,
            "content":    req.content if isinstance(req.content, dict) else {"data": req.content},
            "app_id":     req.app_id,
            "tags":       req.tags or [],
            "notes":      req.notes or "",
            "metadata":   req.metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        result = sb.table("saved_items").insert(record).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Vault save failed — no data returned")
        return {"success": True, "item_id": record["id"], "title": req.title, "type": req.type}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vault save error: {str(e)}")

# ── List ─────────────────────────────────────────────────────────────────────
@router.get("/list")
async def vault_list(user_email: str, app_id: Optional[str] = None,
                     type: Optional[str] = None, limit: int = 50, offset: int = 0):
    try:
        sb = get_supabase()
        q = sb.table("saved_items").select("*").eq("user_email", user_email.lower().strip())
        if app_id:  q = q.eq("app_id", app_id)
        if type:    q = q.eq("type", type)
        result = q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return {"success": True, "items": result.data or [], "total": len(result.data or [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vault list error: {str(e)}")

# ── Get single ───────────────────────────────────────────────────────────────
@router.get("/item/{item_id}")
async def vault_get(item_id: str, user_email: str):
    try:
        sb = get_supabase()
        result = sb.table("saved_items").select("*").eq("id", item_id).eq(
            "user_email", user_email.lower().strip()).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"success": True, "item": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Delete ───────────────────────────────────────────────────────────────────
@router.delete("/delete")
async def vault_delete(req: VaultDeleteRequest):
    try:
        sb = get_supabase()
        result = sb.table("saved_items").delete().eq("id", req.item_id).eq(
            "user_email", req.user_email.lower().strip()).execute()
        return {"success": True, "deleted": req.item_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vault delete error: {str(e)}")

# ── Count ─────────────────────────────────────────────────────────────────────
@router.get("/count")
async def vault_count(user_email: str, app_id: Optional[str] = None):
    try:
        sb = get_supabase()
        q = sb.table("saved_items").select("id", count="exact").eq(
            "user_email", user_email.lower().strip())
        if app_id: q = q.eq("app_id", app_id)
        result = q.execute()
        return {"success": True, "count": result.count or 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
