from fastapi import FastAPI
from backend.app.api.gateway import router as gateway_router

app = FastAPI(title="TRAKN Backend", version="1.0.0")

app.include_router(gateway_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
