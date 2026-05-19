"""
main.py — Railway entry point for TerrellOS FastAPI backend.
Imports the FastAPI `app` object from app.py.
Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
"""
from app import app  # noqa: F401

__all__ = ["app"]
