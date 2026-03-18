import uvicorn
from fastapi import FastAPI 

app=FastAPI()

@app.get("/")
def root():
    return {"message":"PRISM Backend"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)