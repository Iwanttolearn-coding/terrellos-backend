"""
routers/db.py — TerrellOS Generic Entity CRUD
Provides /v1/db/:entity REST endpoints for the TerrellOS frontend.
Uses Supabase REST API directly via httpx — no supabase-py dependency needed.
"""
import os, uuid, httpx
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1/db", tags=["Entity DB"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Whitelisted entity → Supabase table name map
ENTITY_TABLE = {
    "SavedItem":          "saved_items",
    "BuildLog":           "build_logs",
    "Project":            "projects",
    "Upload":             "uploads",
    "FileVersion":        "file_versions",
    "AIModelSetting":     "ai_model_settings",
    "BackendConnection":  "backend_connections",
    "OwnerControl":       "owner_controls",
    "Patch":              "patches",
    "WorkflowState":      "workflow_states",
    "ReleaseRecord":      "release_records",
    "StabilityReport":    "stability_reports",
    "Template":           "templates",
    "WebhookIntegration": "webhook_integrations",
    "Workflow":           "workflows",
    "ProjectTool":        "project_tools",
    "ProjectIntegration": "project_integrations",
    "SystemSettings":     "system_settings",
}

def sb_headers():
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def validate_entity(entity: str) -> str:
    if entity not in ENTITY_TABLE:
        raise HTTPException(status_code=400, detail=f"Unknown entity: {entity}")
    return ENTITY_TABLE[entity]

class WriteBody(BaseModel):
    data: Dict[str, Any] = {}

class FilterBody(BaseModel):
    query: Dict[str, Any] = {}

# ── LIST ──────────────────────────────────────────────────────────────────────────
@router.get("/{entity}")
async def list_entity(entity: str, sort: str = "-created_date", limit: int = 50):
    tbl = validate_entity(entity)
    col = sort.lstrip("-")
    asc = not sort.startswith("-")
    order_param = f"{col}.asc" if asc else f"{col}.desc"
    url = f"{SUPABASE_URL}/rest/v1/{tbl}?order={order_param}&limit={limit}&select=*"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=sb_headers())
    return {"data": r.json() if r.is_success else []}

# ── GET ───────────────────────────────────────────────────────────────────────────
@router.get("/{entity}/{item_id}")
async def get_entity(entity: str, item_id: str):
    tbl = validate_entity(entity)
    url = f"{SUPABASE_URL}/rest/v1/{tbl}?id=eq.{item_id}&select=*&limit=1"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=sb_headers())
    rows = r.json() if r.is_success else []
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return {"data": rows[0]}

# ── FILTER ────────────────────────────────────────────────────────────────────────
@router.post("/{entity}/filter")
async def filter_entity(entity: str, body: FilterBody, sort: str = "-created_date"):
    tbl = validate_entity(entity)
    col = sort.lstrip("-")
    asc = not sort.startswith("-")
    order_param = f"{col}.asc" if asc else f"{col}.desc"
    url = f"{SUPABASE_URL}/rest/v1/{tbl}?order={order_param}&select=*"
    for k, v in body.query.items():
        url += f"&{k}=eq.{v}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=sb_headers())
    return {"data": r.json() if r.is_success else []}

# ── CREATE ────────────────────────────────────────────────────────────────────────
@router.post("/{entity}")
async def create_entity(entity: str, body: WriteBody):
    tbl = validate_entity(entity)
    record = {"id": str(uuid.uuid4()), "created_date": now_iso(), "updated_date": now_iso(), **body.data}
    url = f"{SUPABASE_URL}/rest/v1/{tbl}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json=record, headers=sb_headers())
    rows = r.json() if r.is_success else None
    return {"data": (rows[0] if isinstance(rows, list) and rows else record)}

# ── UPDATE ────────────────────────────────────────────────────────────────────────
@router.put("/{entity}/{item_id}")
async def update_entity(entity: str, item_id: str, body: WriteBody):
    tbl = validate_entity(entity)
    patch = {**body.data, "updated_date": now_iso()}
    url = f"{SUPABASE_URL}/rest/v1/{tbl}?id=eq.{item_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.patch(url, json=patch, headers=sb_headers())
    rows = r.json() if r.is_success else None
    return {"data": rows[0] if isinstance(rows, list) and rows else patch}

# ── DELETE ────────────────────────────────────────────────────────────────────────
@router.delete("/{entity}/{item_id}")
async def delete_entity(entity: str, item_id: str):
    tbl = validate_entity(entity)
    url = f"{SUPABASE_URL}/rest/v1/{tbl}?id=eq.{item_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.delete(url, headers=sb_headers())
    return {"ok": r.is_success}
