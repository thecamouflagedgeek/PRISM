import os

from fastapi import FastAPI, HTTPException
from route.routes import router
from fastapi.middleware.cors import CORSMiddleware
from phase2.shadow_api.routes import router as experimental_shadow_router

app=FastAPI(title="PRISM Backend")
origins = [x.strip() for x in os.getenv("PRISM_CORS_ORIGINS", "").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(set(origins + [
        "http://localhost:5173", "http://localhost:5174",
        "http://127.0.0.1:5173", "http://127.0.0.1:5174",
    ])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(experimental_shadow_router)

@app.get("/health", tags=["Operations"])
def health():
    return {"status": "ok", "service": "prism-backend"}

@app.get("/ready", tags=["Operations"])
def ready():
    from phase4.demo_api import readiness
    is_ready, detail = readiness()
    if not is_ready:
        raise HTTPException(status_code=503, detail=detail)
    return {"status": "ready", **detail}

if os.getenv("ENABLE_PHASE4_DEMO", "false").strip().lower() in {"1", "true", "yes", "on"}:
    from phase4.demo_api import router as phase4_demo_router
    app.include_router(phase4_demo_router)

@app.get("/")
def home():
    return {"message": "PRISM API is live"}
