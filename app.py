from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os

app = FastAPI(title="TerrellOS Backend")

# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# MODELS
# =========================

class ChatMessage(BaseModel):
    role: Optional[str] = "user"
    content: Optional[str] = ""

class ChatRequest(BaseModel):
    message: Optional[str] = None
    prompt: Optional[str] = None
    messages: Optional[List[ChatMessage]] = []

# =========================
# ROOT
# =========================

@app.get("/")
async def root():
    return {
        "status": "TerrellOS backend live",
        "environment": "production",
        "version": "4.0.0-prod"
    }

# =========================
# HEALTH
# =========================

@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }

# =========================
# CHAT ENDPOINT
# =========================

@app.post("/chat")
async def chat(req: ChatRequest):

    user_message = ""

    # PRIORITY 1
    if req.message:
        user_message = req.message

    # PRIORITY 2
    elif req.prompt:
        user_message = req.prompt

    # PRIORITY 3
    elif req.messages and len(req.messages) > 0:
        user_message = req.messages[-1].content

    else:
        user_message = "empty request"

    return {
        "success": True,
        "response": f"TerrellOS AI received: {user_message}",
        "message": user_message,
        "environment": "production",
        "version": "4.0.0-prod"
    }

# =========================
# STARTUP
# =========================

@app.on_event("startup")
async def startup_event():
    print("🔥 TerrellOS backend starting...")
