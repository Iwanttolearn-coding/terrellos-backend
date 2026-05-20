"""
/v1/uploads/* — File upload, vault storage
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/v1/uploads", tags=["Uploads"])

UPLOADS: Dict[str, Dict[str, Any]] = {}

@router.post("/file")
async def upload_file(file: UploadFile = File(...), user_id: Optional[str] = "user",
                      app_id: Optional[str] = "terrellos"):
    content = await file.read()
    uid = str(uuid.uuid4())
    UPLOADS[uid] = {
        "id": uid, "filename": file.filename, "content_type": file.content_type,
        "size": len(content), "user_id": user_id, "app_id": app_id,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"success": True, "upload_id": uid, "filename": file.filename,
            "size": len(content), "content_type": file.content_type}

@router.get("/list/{user_id}")
async def list_uploads(user_id: str, app_id: Optional[str] = None):
    items = [u for u in UPLOADS.values() if u["user_id"] == user_id]
    if app_id: items = [u for u in items if u.get("app_id") == app_id]
    return {"success": True, "uploads": items, "total": len(items)}
