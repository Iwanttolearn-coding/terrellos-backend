from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
import os

app = FastAPI(title="TerrellOS Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

class ChatMessage(BaseModel):
    role: Optional[str] = "user"
    content: Optional[str] = ""

class ChatRequest(BaseModel):
    message: Optional[str] = None
    prompt: Optional[str] = None
    messages: Optional[List[ChatMessage]] = []

@app.get("/")
async def root():
    return {"status": "TerrellOS backend live", "environment": "production"}

@app.get("/health")
async def health():
    return {"status": "healthy", "backend": "online"}

@app.post("/chat")
async def chat(req: ChatRequest):
    user_message = req.message or req.prompt

    if not user_message and req.messages:
        user_message = req.messages[-1].content

    if not user_message:
        user_message = "Hello"

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are TerrellOS AI Builder, a production coding and app-building assistant."
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    )

    return {
        "success": True,
        "reply": res.choices[0].message.content,
        "status": "success"
    }
