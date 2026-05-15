from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# CORS for Base44 frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request model
class ChatRequest(BaseModel):
    message: str

# Root route
@app.get("/")
async def root():
    return {
        "status": "TerrellOS backend live"
    }

# Health route
@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }

# AI chat route
@app.post("/chat")
async def chat(req: ChatRequest):

    user_message = req.message

    return {
        "reply": f"TerrellOS AI received: {user_message}",
        "status": "success"
    }

