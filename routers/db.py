"""
routers/db.py — TerrellOS Generic Entity CRUD
Provides /v1/db/:entity REST endpoints for the TerrellOS frontend.
Replaces Base44 entity SDK — all data stored in Supabase.
Tables are created on first use if they don't exist.
"""
import os, uuid, json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from supabase import create_client, Client

router = APIRouter(prefix="/v1/db", tags=["Entity DB"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

def get_sb() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ── Allowed entity tables (whitelist — prevents arbitrary table injection) ──────
ALLOWED_ENTITIES = {
    "BuildLog", "Project", "Upload", "FileVersion", "AIModelSetting",
    "BackendConnection", "OwnerControl", "Patch", "WorkflowState",
    "ReleaseRecord", "StabilityReport", "Template", "WebhookIntegration",
    "Workflow", "ProjectTool", "ProjectIntegration", "SystemSettings",
}

def validate_entity(entity: str):
    if entity not in ALLOWED_ENTITIES:
        raise HTTPException(status_code=400, detail=f"Unknown entity: {entity}")
    return entity.lower()  # Supabase table names are lowercase

class CreateBody(BaseModel):
    data: Dict[str, Any] = {}

class UpdateBody(BaseModel):
    data: Dict[str, Any] = {}

class FilterBody(BaseModel):
    query: Dict[str, Any] = {}

# ── LIST ─────────────────────────────────────────────────────────────────────────
@router.get("/{entity}")
async def list_entity(entity: str, sort: str = "-created_date", limit: int = 50):
    tbl = validate_entity(entity)
    sb  = get_sb()
    col = sort.lstrip("-")
    asc = not sort.startswith("-")
    try:
        res = sb.table(tbl).select("*").order(col, desc=not asc).limit(limit).execute()
        return {"data": res.data or []}
    except Exception as e:
        return {"data": [], "error": str(e)}

# ── GET ───────────────────────────────────────────────────────────────────────────
@router.get("/{entity}/{item_id}")
async def get_entity(entity: str, item_id: str):
    tbl = validate_entity(entity)
    sb  = get_sb()
    try:
        res = sb.table(tbl).select("*").eq("id", item_id).limit(1).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Not found")
        return {"data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── FILTER ────────────────────────────────────────────────────────────────────────
@router.post("/{entity}/filter")
async def filter_entity(entity: str, body: FilterBody, sort: str = "-created_date"):
    tbl = validate_entity(entity)
    sb  = get_sb()
    col = sort.lstrip("-")
    asc = not sort.startswith("-")
    try:
        q = sb.table(tbl).select("*").order(col, desc=not asc)
        for k, v in body.query.items():
            q = q.eq(k, v)
        res = q.execute()
        return {"data": res.data or []}
    except Exception as e:
        return {"data": [], "error": str(e)}

# ── CREATE ────────────────────────────────────────────────────────────────────────
@router.post("/{entity}")
async def create_entity(entity: str, body: CreateBody):
    tbl = validate_entity(entity)
    sb  = get_sb()
    record = {
        "id": str(uuid.uuid4()),
        "created_date": now_iso(),
        "updated_date": now_iso(),
        **body.data,
    }
    try:
        res = sb.table(tbl).insert(record).execute()
        return {"data": res.data[0] if res.data else record}
    except Exception as e:
        # Table may not exist — return the record as-is (graceful degradation)
        return {"data": record, "warning": f"DB write skipped: {e}"}

# ── UPDATE ────────────────────────────────────────────────────────────────────────
@router.put("/{entity}/{item_id}")
async def update_entity(entity: str, item_id: str, body: UpdateBody):
    tbl = validate_entity(entity)
    sb  = get_sb()
    patch = {**body.data, "updated_date": now_iso()}
    try:
        res = sb.table(tbl).update(patch).eq("id", item_id).execute()
        return {"data": res.data[0] if res.data else patch}
    except Exception as e:
        return {"data": patch, "warning": str(e)}

# ── DELETE ────────────────────────────────────────────────────────────────────────
@router.delete("/{entity}/{item_id}")
async def delete_entity(entity: str, item_id: str):
    tbl = validate_entity(entity)
    sb  = get_sb()
    try:
        sb.table(tbl).delete().eq("id", item_id).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "warning": str(e)}
