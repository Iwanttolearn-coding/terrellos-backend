#!/usr/bin/env python3
"""
prestart.py — Import validation before Uvicorn starts.
Catches missing deps and syntax errors early.
"""
import sys, os

print("[prestart] Validating Python environment...")

checks = [
    ("fastapi",   "FastAPI"),
    ("pydantic",  "BaseModel"),
    ("openai",    "OpenAI"),
    ("httpx",     "AsyncClient"),
    ("starlette.middleware.cors", "CORSMiddleware"),
]

ok = True
for module, cls in checks:
    try:
        mod = __import__(module, fromlist=[cls])
        getattr(mod, cls)
        print(f"  ✅ {module}.{cls}")
    except Exception as e:
        print(f"  ❌ {module}.{cls} — {e}")
        ok = False

print("[prestart] Validating routers...")
routers = [
    "core","memory","voice","pastor","echo","design",
    "founder","admin","uploads","tattoo","gallery",
    "auth","system","paypal","payments","voice_interview",
    "db","fn",
]
for r in routers:
    try:
        __import__(f"routers.{r}", fromlist=["router"])
        print(f"  ✅ routers.{r}")
    except Exception as e:
        print(f"  ❌ routers.{r} — {e}", file=sys.stderr)
        ok = False

if not ok:
    print("[prestart] ❌ Startup aborted — fix errors above", file=sys.stderr)
    sys.exit(1)

print("[prestart] ✅ All checks passed — starting Uvicorn on 0.0.0.0:8080")
