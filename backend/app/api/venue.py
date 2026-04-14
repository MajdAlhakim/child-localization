"""
backend/app/api/venue.py

Legacy single-floor endpoints — kept for backward compatibility with the AP tool
and parent app that were built before multi-floor support.

All operations are routed to the "active" floor plan, determined by:
  1. X-Floor-Plan-Id header (if the caller knows a specific floor plan)
  2. Most recently created floor plan in the DB
  3. Auto-created default "Default Venue / Floor 1" if the DB is empty

The radio map computation still uses in-memory storage (fast, always recomputable).
"""

import math
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.db import get_db
from backend.app.models import AccessPoint, FloorPlan, GridPoint, Venue

router = APIRouter()

_UPLOAD_DIR = Path("/srv/backend/uploads")
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Shared task / radio-map store (in-memory, shared with venues.py via import-time dict)
_task_store: dict[str, dict] = {}
_radio_maps: dict[str, list[dict]] = {}


# ── Auth ─────────────────────────────────────────────────────────────────────

def _check_key(x_api_key: str | None) -> None:
    expected = os.environ.get("GATEWAY_API_KEY", "")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or missing X-API-Key")


# ── Active floor plan resolution ──────────────────────────────────────────────

async def _active_fp(
    db: AsyncSession,
    fp_id_header: str | None = None,
) -> FloorPlan:
    """
    Return the floor plan for legacy endpoints.
    Creates a default Venue + FloorPlan the very first time if the DB is empty.
    """
    if fp_id_header:
        try:
            fp = await db.get(FloorPlan, uuid.UUID(fp_id_header))
            if fp:
                return fp
        except (ValueError, Exception):
            pass

    # Most recently created floor plan
    result = await db.execute(
        select(FloorPlan).order_by(FloorPlan.created_at.desc()).limit(1)
    )
    fp = result.scalar_one_or_none()
    if fp:
        return fp

    # Nothing exists → bootstrap default venue + floor plan
    venue = Venue(name="Default Venue", description="Auto-created on first use")
    db.add(venue)
    await db.flush()
    fp = FloorPlan(venue_id=venue.id, name="Floor 1", floor_number=1)
    db.add(fp)
    await db.commit()
    await db.refresh(fp)
    return fp


# ── Pydantic models ───────────────────────────────────────────────────────────

class AccessPointIn(BaseModel):
    bssid: str
    ssid: str = ""
    rssi_ref: float = -40.0
    path_loss_n: float = 2.7
    x: float = 0.0
    y: float = 0.0
    ceiling_height: float = 3.0
    group_id: str | None = None


class GridPointIn(BaseModel):
    x: float
    y: float


class GridPointsRequest(BaseModel):
    scale_px_per_m: float = 10.0
    grid_spacing_m: float = 0.5
    points: list[GridPointIn]


# ── AP endpoints ──────────────────────────────────────────────────────────────

@router.get("/api/v1/venue/aps")
async def get_aps(
    x_api_key: str | None = Header(default=None),
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _check_key(x_api_key)
    fp = await _active_fp(db, x_floor_plan_id)
    result = await db.execute(
        select(AccessPoint).where(AccessPoint.floor_plan_id == fp.id)
    )
    aps = result.scalars().all()
    return {
        "access_points": [
            {
                "bssid":          ap.bssid,
                "ssid":           ap.ssid,
                "rssi_ref":       ap.rssi_ref,
                "path_loss_n":    ap.path_loss_n,
                "x":              ap.x,
                "y":              ap.y,
                "ceiling_height": ap.ceiling_height,
                "group_id":       str(ap.group_id) if ap.group_id else None,
            }
            for ap in aps
        ]
    }


@router.post("/api/v1/venue/ap", status_code=status.HTTP_200_OK)
async def post_ap(
    ap_in: AccessPointIn,
    x_api_key: str | None = Header(default=None),
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    _check_key(x_api_key)
    fp = await _active_fp(db, x_floor_plan_id)
    gid = uuid.UUID(ap_in.group_id) if ap_in.group_id else None

    result = await db.execute(
        select(AccessPoint).where(
            AccessPoint.floor_plan_id == fp.id,
            AccessPoint.bssid == ap_in.bssid,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.ssid           = ap_in.ssid
        existing.rssi_ref       = ap_in.rssi_ref
        existing.path_loss_n    = ap_in.path_loss_n
        existing.x              = ap_in.x
        existing.y              = ap_in.y
        existing.ceiling_height = ap_in.ceiling_height
        if gid:
            existing.group_id = gid
    else:
        db.add(AccessPoint(
            floor_plan_id  = fp.id,
            group_id       = gid,
            bssid          = ap_in.bssid,
            ssid           = ap_in.ssid,
            rssi_ref       = ap_in.rssi_ref,
            path_loss_n    = ap_in.path_loss_n,
            x              = ap_in.x,
            y              = ap_in.y,
            ceiling_height = ap_in.ceiling_height,
        ))
    await db.commit()
    return {"status": "ok"}


@router.delete("/api/v1/venue/aps", status_code=status.HTTP_200_OK)
async def delete_all_aps(
    x_api_key: str | None = Header(default=None),
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    _check_key(x_api_key)
    fp = await _active_fp(db, x_floor_plan_id)
    await db.execute(delete(AccessPoint).where(AccessPoint.floor_plan_id == fp.id))
    await db.commit()
    return {"status": "ok"}


# ── Floor plan endpoints ──────────────────────────────────────────────────────

@router.post("/api/v1/venue/floor-plan", status_code=status.HTTP_200_OK)
async def upload_floor_plan(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    _check_key(x_api_key)
    content_type = file.content_type or ""
    if content_type not in ("image/jpeg", "image/png", "image/jpg", "image/svg+xml"):
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or SVG accepted")

    fp = await _active_fp(db, x_floor_plan_id)
    img_dir = _UPLOAD_DIR / str(fp.id)
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "image"
    data = await file.read()
    img_path.write_bytes(data)
    fp.image_path = str(img_path)
    await db.commit()
    return {"status": "ok", "size": str(len(data))}


@router.get("/api/v1/venue/floor-plan")
async def get_floor_plan(
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    fp = await _active_fp(db, x_floor_plan_id)
    if not fp.image_path or not Path(fp.image_path).exists():
        raise HTTPException(status_code=404, detail="No floor plan uploaded yet")
    data = Path(fp.image_path).read_bytes()
    if data[:4] == b"\x89PNG":
        media_type = "image/png"
    elif b"<svg" in data[:256]:
        media_type = "image/svg+xml"
    else:
        media_type = "image/jpeg"
    return FileResponse(fp.image_path, media_type=media_type)


# ── Grid endpoints ────────────────────────────────────────────────────────────

@router.post("/api/v1/venue/grid-points", status_code=status.HTTP_200_OK)
async def post_grid_points(
    body: GridPointsRequest,
    x_api_key: str | None = Header(default=None),
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _check_key(x_api_key)
    fp = await _active_fp(db, x_floor_plan_id)
    await db.execute(delete(GridPoint).where(GridPoint.floor_plan_id == fp.id))
    fp.scale_px_per_m = body.scale_px_per_m
    fp.grid_spacing_m = body.grid_spacing_m
    for pt in body.points:
        db.add(GridPoint(floor_plan_id=fp.id, x=pt.x, y=pt.y))
    await db.commit()
    return {"status": "ok", "count": len(body.points)}


@router.get("/api/v1/venue/grid-points")
async def get_grid_points(
    x_api_key: str | None = Header(default=None),
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _check_key(x_api_key)
    fp = await _active_fp(db, x_floor_plan_id)
    result = await db.execute(
        select(GridPoint).where(GridPoint.floor_plan_id == fp.id)
    )
    pts = result.scalars().all()
    if not pts:
        raise HTTPException(status_code=404, detail="No grid stored yet")
    return {
        "scale_px_per_m": fp.scale_px_per_m,
        "grid_spacing_m": fp.grid_spacing_m,
        "points": [{"x": p.x, "y": p.y} for p in pts],
    }


# ── Radio Map ─────────────────────────────────────────────────────────────────

def _compute_bg(task_id: str, fpid_str: str, points: list, aps: list) -> None:
    total   = max(len(points) * len(aps), 1)
    entries = []
    done    = 0
    for pt in points:
        for ap in aps:
            dx = pt["x"] - ap["x"]
            dy = pt["y"] - ap["y"]
            floor_dist = math.sqrt(dx * dx + dy * dy)
            slant      = math.sqrt(floor_dist ** 2 + ap.get("ceiling_height", 3.0) ** 2)
            slant      = max(slant, 0.1)
            rssi_est   = ap["rssi_ref"] - 10.0 * ap["path_loss_n"] * math.log10(slant)
            entries.append({
                "bssid":    ap["bssid"],
                "x_m":      round(pt["x"], 3),
                "y_m":      round(pt["y"], 3),
                "rssi_est": round(rssi_est, 2),
                "dist_m":   round(slant, 3),
            })
            done += 1
            if done % 500 == 0:
                _task_store[task_id]["progress"] = int(done / total * 100)
    _radio_maps[fpid_str] = entries
    _task_store[task_id]  = {"status": "done", "progress": 100}


@router.post("/api/v1/venue/radio-map/compute", status_code=status.HTTP_200_OK)
async def compute_radio_map(
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(default=None),
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    _check_key(x_api_key)
    fp = await _active_fp(db, x_floor_plan_id)
    fp_id = fp.id  # capture id before any session expiry

    # selectinload + populate_existing=True forces SQLAlchemy to run the
    # secondary SELECTs for grid_points and access_points even when the
    # FloorPlan object is already cached in the session identity map.
    # Without populate_existing the cached object is returned without
    # relationships, and accessing them triggers lazy-load which raises
    # MissingGreenlet under asyncpg.
    result = await db.execute(
        select(FloorPlan)
        .options(
            selectinload(FloorPlan.grid_points),
            selectinload(FloorPlan.access_points),
        )
        .where(FloorPlan.id == fp_id)
        .execution_options(populate_existing=True)
    )
    fp_full = result.scalar_one_or_none()
    if not fp_full:
        raise HTTPException(status_code=404, detail="Floor plan not found")
    if not fp_full.grid_points:
        raise HTTPException(status_code=422, detail="No grid stored. Save the grid first.")
    if not fp_full.access_points:
        raise HTTPException(status_code=422, detail="No APs stored. Place APs first.")

    points  = [{"x": p.x, "y": p.y} for p in fp_full.grid_points]
    aps     = [{"bssid": a.bssid, "x": a.x, "y": a.y,
                "rssi_ref": a.rssi_ref, "path_loss_n": a.path_loss_n,
                "ceiling_height": a.ceiling_height} for a in fp_full.access_points]

    task_id = str(uuid.uuid4())
    _task_store[task_id] = {"status": "computing", "progress": 0}
    background_tasks.add_task(_compute_bg, task_id, str(fp.id), points, aps)
    return {"status": "computing", "task_id": task_id}


@router.get("/api/v1/venue/radio-map/status/{task_id}")
async def radio_map_status(task_id: str) -> dict[str, Any]:
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/api/v1/venue/radio-map")
async def get_radio_map(
    x_floor_plan_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    fp = await _active_fp(db, x_floor_plan_id)
    data = _radio_maps.get(str(fp.id))
    if not data:
        raise HTTPException(status_code=404, detail="Radio map not computed yet")
    return {"radio_map": data}
