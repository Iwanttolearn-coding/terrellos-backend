
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def root():
    return {
        "status": "TerrellOS backend live"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }

@app.post("/chat")
async def chat(req: ChatRequest):

    user_message = req.message

    return {
        "reply": f"TerrellOS AI received: {user_message}",
        "status": "success"
    }
