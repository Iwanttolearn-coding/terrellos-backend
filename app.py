from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "success": True
    }

@app.get("/ping")
async def ping():
    return {
        "message": "pong"
    }
