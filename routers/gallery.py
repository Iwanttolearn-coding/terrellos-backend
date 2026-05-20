"""
/v1/gallery/* — Creator Vault: persistent gallery, folders, collections
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/v1/gallery", tags=["Creator Vault"])

# In-memory store (replace with Supabase/PostgreSQL for persistence)
GALLERY: Dict[str, Dict[str, Any]] = {}
FOLDERS: Dict[str, Dict[str, Any]] = {}
PROMPTS: Dict[str, List[Dict]] = {}  # user_id -> prompt history

VAULT_CATEGORIES = [
    "ai_generations",
    "tattoo_concepts",
    "tattoo_outlines",
    "vector_files",
    "dtf_designs",
    "transparent_pngs",
    "mockups",
    "upload_history",
    "saved_prompts",
    "favorite_styles",
    "collections",
]

class GallerySaveRequest(BaseModel):
    user_id: str
    app_id: Optional[str] = "all-around-customs"
    title: Optional[str] = "Untitled"
    prompt: Optional[str] = None
    image_url: str
    type: Optional[str] = "ai_generation"     # tattoo_concept | tattoo_stencil | vector | dtf | png | mockup
    tags: Optional[List[str]] = []
    folder_id: Optional[str] = None
    style: Optional[str] = None
    source: Optional[str] = "ai_generated"    # ai_generated | uploaded | edited

class GalleryUpdateRequest(BaseModel):
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    folder_id: Optional[str] = None
    is_favorite: Optional[bool] = None

class FolderCreateRequest(BaseModel):
    user_id: str
    name: str
    color: Optional[str] = "#7c3aed"
    icon: Optional[str] = "folder"
    app_id: Optional[str] = "all-around-customs"

class PromptSaveRequest(BaseModel):
    user_id: str
    prompt: str
    type: Optional[str] = "tattoo"
    style: Optional[str] = None
    is_favorite: Optional[bool] = False

@router.post("/save")
async def save_item(payload: GallerySaveRequest):
    """Save a generated image or uploaded file to the Creator Vault."""
    item_id = str(uuid.uuid4())
    item = {
        "id": item_id,
        "user_id": payload.user_id,
        "app_id": payload.app_id,
        "title": payload.title,
        "prompt": payload.prompt,
        "image_url": payload.image_url,
        "type": payload.type,
        "tags": payload.tags or [],
        "folder_id": payload.folder_id,
        "style": payload.style,
        "source": payload.source,
        "is_favorite": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    GALLERY[item_id] = item
    
    # Auto-save prompt to history if provided
    if payload.prompt and payload.user_id:
        if payload.user_id not in PROMPTS:
            PROMPTS[payload.user_id] = []
        PROMPTS[payload.user_id].insert(0, {
            "prompt": payload.prompt, "type": payload.type,
            "style": payload.style, "used_at": datetime.now(timezone.utc).isoformat()
        })
        PROMPTS[payload.user_id] = PROMPTS[payload.user_id][:50]  # Keep last 50
    
    return {"success": True, "item_id": item_id, "item": item}

@router.get("/load/{user_id}")
async def load_gallery(
    user_id: str,
    type: Optional[str] = None,
    folder_id: Optional[str] = None,
    favorites_only: Optional[bool] = False,
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    app_id: Optional[str] = None,
):
    """Load user gallery with optional filters."""
    items = [i for i in GALLERY.values() if i["user_id"] == user_id]
    if type: items = [i for i in items if i["type"] == type]
    if folder_id: items = [i for i in items if i.get("folder_id") == folder_id]
    if favorites_only: items = [i for i in items if i.get("is_favorite")]
    if app_id: items = [i for i in items if i.get("app_id") == app_id]
    
    items = sorted(items, key=lambda x: x["created_at"], reverse=True)
    total = len(items)
    paginated = items[offset:offset + limit]
    
    # Group by type for summary
    type_counts = {}
    for i in items:
        t = i.get("type", "other")
        type_counts[t] = type_counts.get(t, 0) + 1
    
    return {
        "success": True,
        "items": paginated,
        "total": total,
        "returned": len(paginated),
        "offset": offset,
        "has_more": (offset + limit) < total,
        "type_summary": type_counts,
    }

@router.get("/item/{item_id}")
async def get_item(item_id: str):
    item = GALLERY.get(item_id)
    if not item: raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True, "item": item}

@router.patch("/item/{item_id}")
async def update_item(item_id: str, payload: GalleryUpdateRequest):
    item = GALLERY.get(item_id)
    if not item: raise HTTPException(status_code=404, detail="Item not found")
    if payload.title is not None: item["title"] = payload.title
    if payload.tags is not None: item["tags"] = payload.tags
    if payload.folder_id is not None: item["folder_id"] = payload.folder_id
    if payload.is_favorite is not None: item["is_favorite"] = payload.is_favorite
    item["updated_at"] = datetime.now(timezone.utc).isoformat()
    return {"success": True, "item": item}

@router.delete("/item/{item_id}")
async def delete_item(item_id: str):
    if item_id not in GALLERY: raise HTTPException(status_code=404, detail="Item not found")
    del GALLERY[item_id]
    return {"success": True, "deleted": item_id}

@router.post("/folders")
async def create_folder(payload: FolderCreateRequest):
    folder_id = str(uuid.uuid4())
    folder = {
        "id": folder_id, "user_id": payload.user_id,
        "name": payload.name, "color": payload.color,
        "icon": payload.icon, "app_id": payload.app_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    FOLDERS[folder_id] = folder
    return {"success": True, "folder_id": folder_id, "folder": folder}

@router.get("/folders/{user_id}")
async def get_folders(user_id: str):
    folders = [f for f in FOLDERS.values() if f["user_id"] == user_id]
    # Add item counts
    for folder in folders:
        folder["item_count"] = len([i for i in GALLERY.values()
                                    if i.get("folder_id") == folder["id"]])
    return {"success": True, "folders": folders, "total": len(folders)}

@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str):
    if folder_id not in FOLDERS: raise HTTPException(status_code=404, detail="Folder not found")
    # Unassign items from deleted folder
    for item in GALLERY.values():
        if item.get("folder_id") == folder_id:
            item["folder_id"] = None
    del FOLDERS[folder_id]
    return {"success": True, "deleted": folder_id}

@router.post("/prompts/save")
async def save_prompt(payload: PromptSaveRequest):
    if payload.user_id not in PROMPTS: PROMPTS[payload.user_id] = []
    entry = {
        "id": str(uuid.uuid4()), "prompt": payload.prompt,
        "type": payload.type, "style": payload.style,
        "is_favorite": payload.is_favorite,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    PROMPTS[payload.user_id].insert(0, entry)
    return {"success": True, "prompt_id": entry["id"]}

@router.get("/prompts/{user_id}")
async def get_prompts(user_id: str, favorites_only: bool = False, limit: int = 30):
    prompts = PROMPTS.get(user_id, [])
    if favorites_only: prompts = [p for p in prompts if p.get("is_favorite")]
    return {"success": True, "prompts": prompts[:limit], "total": len(prompts)}

@router.get("/stats/{user_id}")
async def gallery_stats(user_id: str):
    items = [i for i in GALLERY.values() if i["user_id"] == user_id]
    type_counts = {}
    for i in items:
        t = i.get("type", "other")
        type_counts[t] = type_counts.get(t, 0) + 1
    return {
        "success": True,
        "total_items": len(items),
        "total_folders": len([f for f in FOLDERS.values() if f["user_id"] == user_id]),
        "total_prompts": len(PROMPTS.get(user_id, [])),
        "favorites": len([i for i in items if i.get("is_favorite")]),
        "by_type": type_counts,
        "vault_categories": VAULT_CATEGORIES,
    }

@router.get("/categories")
async def get_categories():
    return {"success": True, "categories": VAULT_CATEGORIES}
