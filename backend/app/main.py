from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db import engine
from backend.app.models import Base
from backend.app.api.gateway import router as gateway_router
from backend.app.api.venue import router as venue_router
from backend.app.api.venues import router as venues_router
from backend.app.api.tags import router as tags_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create all tables on startup (idempotent — safe to run on every boot)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="TRAKN Backend", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gateway_router)
app.include_router(venue_router)   # legacy single-floor endpoints
app.include_router(venues_router)  # new multi-floor endpoints
app.include_router(tags_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
