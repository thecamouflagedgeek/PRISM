from fastapi import FastAPI
from route.routes import router
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI(title="PRISM Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

@app.get("/")
def home():
    return {"message": "PRISM API is live"}