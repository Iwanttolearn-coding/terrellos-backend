from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("API_KEY")

app = FastAPI(title="TerrellOS Python Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def check_key(x_api_key: str):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "TerrellOS backend is running"
    }

@app.get("/api/status")
def status(x_api_key: str = Header(None)):
    check_key(x_api_key)
    return {
        "python": "online",
        "backend": "connected",
        "mode": "production"
    }
