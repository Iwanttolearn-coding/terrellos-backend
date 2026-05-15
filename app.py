from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    prompt: Optional[str] = ""
    message: Optional[str] = ""
    messages: Optional[List[Dict[str, Any]]] = []

@app.get("/")
async def root():
    return {
        "status": "TerrellOS backend live",
        "environment": "production",
        "success": True
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "backend": "online",
        "environment": "production",
        "success": True
    }

@app.get("/ping")
async def ping():
    return {
        "message": "pong",
        "success": True
    }

@app.post("/chat")
async def chat(req: ChatRequest):
    user_input = req.prompt or req.message

    if not user_input and req.messages:
        last_message = req.messages[-1]
        user_input = last_message.get("content", "")

    if not user_input:
        user_input = "No prompt received"

    return {
        "reply": f"TerrellOS AI received: {user_input}",
        "status": "success",
        "success": True
    }
