from fastapi import FastAPI
from api.routes import router
app=FastAPI(title="PRISM Backend")

app.include_router(router)

