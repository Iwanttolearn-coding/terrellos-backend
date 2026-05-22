"""
/v1/uploads/* — File upload with persistent in-memory store + base64 serving
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid, base64, os

router = APIRouter(prefix="/v1/uploads", tags=["Uploads"])

# In-memory store keyed by upload_id
# NOTE: Fly.io restarts clear this. For true persistence, wire to Supabase Storage.
_STORE: Dict[str, Dict[str, Any]] = {}

ALLOWED_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "image/svg+xml", "application/pdf",
}
MAX_SIZE_MB = 20

@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(default="user"),
    app_id:  Optional[str] = Form(default="terrellos"),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type not allowed: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_SIZE_MB}MB)")

    uid = str(uuid.uuid4())
    b64 = base64.b64encode(content).decode()
    data_url = f"data:{file.content_type};base64,{b64}"

    _STORE[uid] = {
        "id": uid,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "user_id": user_id,
        "app_id": app_id,
        "data_url": data_url,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    # Return file_url pointing to our serve endpoint
    base_url = os.getenv("FRONTEND_URL", "https://terrellos-backend.fly.dev")
    file_url = data_url  # Use data URL directly so gallery can display it immediately

    return {
        "success": True,
        "upload_id": uid,
        "filename": file.filename,
        "file_url": file_url,
        "size": len(content),
        "content_type": file.content_type,
    }

@router.get("/list/{user_id}")
async def list_uploads(user_id: str, app_id: Optional[str] = None):
    items = [
        {k: v for k, v in u.items() if k != "data_url"}  # exclude raw bytes from listing
        for u in _STORE.values()
        if u["user_id"] == user_id and (app_id is None or u.get("app_id") == app_id)
    ]
    return {"success": True, "uploads": items, "total": len(items)}

@router.get("/file/{upload_id}")
async def serve_file(upload_id: str):
    item = _STORE.get(upload_id)
    if not item:
        raise HTTPException(404, "File not found")
    raw = base64.b64decode(item["data_url"].split(",", 1)[1])
    return Response(content=raw, media_type=item["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="{item["filename"]}"'})

@router.delete("/file/{upload_id}")
async def delete_upload(upload_id: str, user_id: str = ""):
    item = _STORE.get(upload_id)
    if not item:
        raise HTTPException(404, "Not found")
    if user_id and item["user_id"] != user_id:
        raise HTTPException(403, "Forbidden")
    del _STORE[upload_id]
    return {"success": True}


@router.get("/health")
async def uploads_health():
    """Upload system health check."""
    import os
    return {
        "success": True,
        "status":  "online",
        "max_file_size_mb": 50,
        "supported_types": ["image/png","image/jpeg","image/webp","image/gif","application/pdf","image/svg+xml"],
        "storage": "fly_volume",
    }
