from fastapi import FastAPI
from route.routes import router
app=FastAPI(title="PRISM Backend")

app.include_router(router)

