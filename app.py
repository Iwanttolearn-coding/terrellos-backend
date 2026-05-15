from fastapi import FastAPI

app = FastAPI()

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
