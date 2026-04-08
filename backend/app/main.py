from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.gateway import router as gateway_router
from backend.app.api.venue import router as venue_router

app = FastAPI(title="TRAKN Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gateway_router)
app.include_router(venue_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
