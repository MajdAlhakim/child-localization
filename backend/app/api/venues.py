"""
backend/app/api/venues.py

Multi-floor venue + floor-plan management API.

Venues
  GET    /api/v1/venues                              list all venues (with floor plans + AP counts)
  POST   /api/v1/venues                              create venue
  GET    /api/v1/venues/{vid}                        get venue detail
  DELETE /api/v1/venues/{vid}                        delete venue (cascades)

Floor Plans
  GET    /api/v1/venues/{vid}/floor-plans            list floor plans for a venue
  POST   /api/v1/venues/{vid}/floor-plans            create floor plan + upload image (multipart)
  GET    /api/v1/floor-plans/{fpid}                  get floor plan detail
  DELETE /api/v1/floor-plans/{fpid}                  delete floor plan (cascades)
  GET    /api/v1/floor-plans/{fpid}/image            serve floor plan image

Access Points (floor-plan scoped)
  GET    /api/v1/floor-plans/{fpid}/aps              list APs
  POST   /api/v1/floor-plans/{fpid}/aps              upsert one AP (or a subnet group)
  DELETE /api/v1/floor-plans/{fpid}/aps/{bssid}      delete one AP

Grid (floor-plan scoped)
  GET    /api/v1/floor-plans/{fpid}/grid             get grid
  POST   /api/v1/floor-plans/{fpid}/grid             save/replace grid

Radio Map (floor-plan scoped, in-memory computation)
  POST   /api/v1/floor-plans/{fpid}/radio-map/compute
  GET    /api/v1/floor-plans/{fpid}/radio-map/status/{tid}
  GET    /api/v1/floor-plans/{fpid}/radio-map
"""

import math
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.db import get_db
from backend.app.models import AccessPoint, FloorPlan, GridPoint, Venue

router = APIRouter()

_UPLOAD_DIR = Path("/srv/backend/uploads")
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# In-memory radio-map task store (keyed by task_id)
_task_store: dict[str, dict] = {}
_radio_maps: dict[str, list[dict]] = {}   # floor_plan_id → entries


# ── Auth ─────────────────────────────────────────────────────────────────────

def _check_key(x_api_key: str | None) -> None:
    expected = os.environ.get("GATEWAY_API_KEY", "")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or missing X-API-Key")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class VenueCreate(BaseModel):
    name: str
    description: str = ""

class APUpsert(BaseModel):
    bssid: str
    ssid: str = ""
    rssi_ref: float = -40.0
    path_loss_n: float = 2.7
    x: float = 0.0
    y: float = 0.0
    ceiling_height: float = 3.0
    group_id: str | None = None   # UUID string; links subnet BSSIDs

class APGroupUpsert(BaseModel):
    """Submit multiple BSSIDs from the same physical AP at once."""
    access_points: list[APUpsert]

class GridPointSchema(BaseModel):
    x: float
    y: float

class GridSave(BaseModel):
    scale_px_per_m: float = 10.0
    grid_spacing_m: float = 0.5
    points: list[GridPointSchema]


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _fp_dict(fp: FloorPlan, ap_count: int | None = None) -> dict:
    return {
        "id":             str(fp.id),
        "venue_id":       str(fp.venue_id),
        "name":           fp.name,
        "floor_number":   fp.floor_number,
        "scale_px_per_m": fp.scale_px_per_m,
        "grid_spacing_m": fp.grid_spacing_m,
        "has_image":      fp.image_path is not None,
        "created_at":     fp.created_at.isoformat(),
        "ap_count":       ap_count if ap_count is not None else len(fp.access_points),
    }

def _ap_dict(ap: AccessPoint) -> dict:
    return {
        "id":             str(ap.id),
        "bssid":          ap.bssid,
        "ssid":           ap.ssid,
        "rssi_ref":       ap.rssi_ref,
        "path_loss_n":    ap.path_loss_n,
        "x":              ap.x,
        "y":              ap.y,
        "ceiling_height": ap.ceiling_height,
        "group_id":       str(ap.group_id) if ap.group_id else None,
    }


# ── Venue endpoints ───────────────────────────────────────────────────────────

@router.get("/api/v1/venues")
async def list_venues(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(Venue).options(selectinload(Venue.floor_plans)
                              .selectinload(FloorPlan.access_points))
        .order_by(Venue.created_at)
    )
    venues = result.unique().scalars().all()
    return {
        "venues": [
            {
                "id":          str(v.id),
                "name":        v.name,
                "description": v.description,
                "created_at":  v.created_at.isoformat(),
                "floor_plans": [_fp_dict(fp) for fp in v.floor_plans],
            }
            for v in venues
        ]
    }


@router.post("/api/v1/venues", status_code=status.HTTP_201_CREATED)
async def create_venue(
    body: VenueCreate,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    venue = Venue(name=body.name, description=body.description)
    db.add(venue)
    await db.commit()
    await db.refresh(venue)
    return {"id": str(venue.id), "name": venue.name}


@router.get("/api/v1/venues/{vid}")
async def get_venue(vid: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    venue = await db.get(Venue, vid, options=[
        selectinload(Venue.floor_plans).selectinload(FloorPlan.access_points)
    ])
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return {
        "id":          str(venue.id),
        "name":        venue.name,
        "description": venue.description,
        "floor_plans": [_fp_dict(fp) for fp in venue.floor_plans],
    }


@router.delete("/api/v1/venues/{vid}", status_code=status.HTTP_200_OK)
async def delete_venue(
    vid: uuid.UUID,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    venue = await db.get(Venue, vid)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    await db.delete(venue)
    await db.commit()
    return {"status": "deleted"}


# ── Floor Plan endpoints ──────────────────────────────────────────────────────

@router.get("/api/v1/venues/{vid}/floor-plans")
async def list_floor_plans(vid: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    venue = await db.get(Venue, vid, options=[
        selectinload(Venue.floor_plans).selectinload(FloorPlan.access_points)
    ])
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return {"floor_plans": [_fp_dict(fp) for fp in venue.floor_plans]}


@router.post("/api/v1/venues/{vid}/floor-plans", status_code=status.HTTP_201_CREATED)
async def create_floor_plan(
    vid: uuid.UUID,
    name: str = Form(default="Floor 1"),
    floor_number: int = Form(default=1),
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    venue = await db.get(Venue, vid)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    content_type = file.content_type or ""
    if content_type not in ("image/jpeg", "image/png", "image/jpg", "image/svg+xml"):
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or SVG accepted")

    fp = FloorPlan(venue_id=vid, name=name, floor_number=floor_number)
    db.add(fp)
    await db.flush()   # get fp.id before writing file

    img_dir = _UPLOAD_DIR / str(fp.id)
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "image"
    img_path.write_bytes(await file.read())
    fp.image_path = str(img_path)

    await db.commit()
    await db.refresh(fp)
    return _fp_dict(fp, ap_count=0)


@router.get("/api/v1/floor-plans/{fpid}")
async def get_floor_plan(fpid: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    fp = await db.get(FloorPlan, fpid, options=[selectinload(FloorPlan.access_points)])
    if not fp:
        raise HTTPException(status_code=404, detail="Floor plan not found")
    return _fp_dict(fp)


@router.delete("/api/v1/floor-plans/{fpid}", status_code=status.HTTP_200_OK)
async def delete_floor_plan(
    fpid: uuid.UUID,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    fp = await db.get(FloorPlan, fpid)
    if not fp:
        raise HTTPException(status_code=404, detail="Floor plan not found")
    await db.delete(fp)
    await db.commit()
    return {"status": "deleted"}


@router.post("/api/v1/floor-plans/{fpid}/image", status_code=status.HTTP_200_OK)
async def upload_floor_plan_image(
    fpid: uuid.UUID,
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    fp = await db.get(FloorPlan, fpid)
    if not fp:
        raise HTTPException(status_code=404, detail="Floor plan not found")
    content_type = file.content_type or ""
    if content_type not in ("image/jpeg", "image/png", "image/jpg", "image/svg+xml"):
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or SVG accepted")
    img_dir = _UPLOAD_DIR / str(fpid)
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "image"
    data = await file.read()
    img_path.write_bytes(data)
    fp.image_path = str(img_path)
    await db.commit()
    return {"status": "ok", "size": len(data)}


@router.get("/api/v1/floor-plans/{fpid}/image")
async def get_floor_plan_image(fpid: uuid.UUID, db: AsyncSession = Depends(get_db)) -> FileResponse:
    fp = await db.get(FloorPlan, fpid)
    if not fp or not fp.image_path or not Path(fp.image_path).exists():
        raise HTTPException(status_code=404, detail="No image for this floor plan")
    data = Path(fp.image_path).read_bytes()
    if data[:4] == b"\x89PNG":
        media_type = "image/png"
    elif b"<svg" in data[:256]:
        media_type = "image/svg+xml"
    else:
        media_type = "image/jpeg"
    return FileResponse(fp.image_path, media_type=media_type)


# ── AP endpoints (floor-plan scoped) ─────────────────────────────────────────

@router.get("/api/v1/floor-plans/{fpid}/aps")
async def get_aps(
    fpid: uuid.UUID,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    result = await db.execute(
        select(AccessPoint).where(AccessPoint.floor_plan_id == fpid)
    )
    aps = result.scalars().all()
    return {"access_points": [_ap_dict(ap) for ap in aps]}


@router.post("/api/v1/floor-plans/{fpid}/aps", status_code=status.HTTP_200_OK)
async def upsert_aps(
    fpid: uuid.UUID,
    body: APGroupUpsert,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Upsert one or more APs for a floor plan.
    All APs in one request that share the same physical position should have the same group_id.
    """
    _check_key(x_api_key)
    fp = await db.get(FloorPlan, fpid)
    if not fp:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    for item in body.access_points:
        gid = uuid.UUID(item.group_id) if item.group_id else None
        result = await db.execute(
            select(AccessPoint).where(
                AccessPoint.floor_plan_id == fpid,
                AccessPoint.bssid == item.bssid,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.ssid           = item.ssid
            existing.rssi_ref       = item.rssi_ref
            existing.path_loss_n    = item.path_loss_n
            existing.x              = item.x
            existing.y              = item.y
            existing.ceiling_height = item.ceiling_height
            if gid:
                existing.group_id = gid
        else:
            db.add(AccessPoint(
                floor_plan_id  = fpid,
                group_id       = gid,
                bssid          = item.bssid,
                ssid           = item.ssid,
                rssi_ref       = item.rssi_ref,
                path_loss_n    = item.path_loss_n,
                x              = item.x,
                y              = item.y,
                ceiling_height = item.ceiling_height,
            ))

    await db.commit()
    return {"status": "ok", "count": len(body.access_points)}


@router.delete("/api/v1/floor-plans/{fpid}/aps/{bssid:path}", status_code=status.HTTP_200_OK)
async def delete_ap(
    fpid: uuid.UUID,
    bssid: str,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    await db.execute(
        delete(AccessPoint).where(
            AccessPoint.floor_plan_id == fpid,
            AccessPoint.bssid == bssid,
        )
    )
    await db.commit()
    return {"status": "ok"}


# ── Grid endpoints (floor-plan scoped) ───────────────────────────────────────

@router.get("/api/v1/floor-plans/{fpid}/grid")
async def get_grid(
    fpid: uuid.UUID,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    fp = await db.get(FloorPlan, fpid, options=[selectinload(FloorPlan.grid_points)])
    if not fp:
        raise HTTPException(status_code=404, detail="Floor plan not found")
    if not fp.grid_points:
        raise HTTPException(status_code=404, detail="No grid saved yet")
    return {
        "scale_px_per_m": fp.scale_px_per_m,
        "grid_spacing_m": fp.grid_spacing_m,
        "points": [{"x": p.x, "y": p.y} for p in fp.grid_points],
    }


@router.post("/api/v1/floor-plans/{fpid}/grid", status_code=status.HTTP_200_OK)
async def save_grid(
    fpid: uuid.UUID,
    body: GridSave,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    fp = await db.get(FloorPlan, fpid)
    if not fp:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    # Delete existing grid and replace
    await db.execute(delete(GridPoint).where(GridPoint.floor_plan_id == fpid))
    fp.scale_px_per_m = body.scale_px_per_m
    fp.grid_spacing_m = body.grid_spacing_m
    for pt in body.points:
        db.add(GridPoint(floor_plan_id=fpid, x=pt.x, y=pt.y))

    await db.commit()
    return {"status": "ok", "count": len(body.points)}


# ── Radio Map (in-memory, floor-plan scoped) ──────────────────────────────────

def _compute_radio_map_bg(task_id: str, fpid_str: str, points: list, aps: list) -> None:
    total = len(points) * len(aps)
    entries: list[dict] = []
    done = 0
    for pt in points:
        for ap in aps:
            dx = pt["x"] - ap["x"]
            dy = pt["y"] - ap["y"]
            floor_dist = math.sqrt(dx * dx + dy * dy)
            slant_dist = math.sqrt(floor_dist ** 2 + ap.get("ceiling_height", 3.0) ** 2)
            slant_dist = max(slant_dist, 0.1)
            rssi_est   = ap["rssi_ref"] - 10.0 * ap["path_loss_n"] * math.log10(slant_dist)
            entries.append({
                "bssid":    ap["bssid"],
                "x_m":      round(pt["x"], 3),
                "y_m":      round(pt["y"], 3),
                "rssi_est": round(rssi_est, 2),
                "dist_m":   round(slant_dist, 3),
            })
            done += 1
            if done % 500 == 0:
                _task_store[task_id]["progress"] = int(done / total * 100)

    _radio_maps[fpid_str] = entries
    _task_store[task_id] = {"status": "done", "progress": 100}


@router.post("/api/v1/floor-plans/{fpid}/radio-map/compute", status_code=status.HTTP_200_OK)
async def compute_radio_map(
    fpid: uuid.UUID,
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_key(x_api_key)
    fp = await db.get(FloorPlan, fpid, options=[
        selectinload(FloorPlan.grid_points),
        selectinload(FloorPlan.access_points),
    ])
    if not fp:
        raise HTTPException(status_code=404, detail="Floor plan not found")
    if not fp.grid_points:
        raise HTTPException(status_code=422, detail="No grid saved. Save grid first.")
    if not fp.access_points:
        raise HTTPException(status_code=422, detail="No APs saved. Place APs first.")

    points = [{"x": p.x, "y": p.y} for p in fp.grid_points]
    aps    = [_ap_dict(a) for a in fp.access_points]

    task_id = str(uuid.uuid4())
    _task_store[task_id] = {"status": "computing", "progress": 0}
    background_tasks.add_task(_compute_radio_map_bg, task_id, str(fpid), points, aps)
    return {"status": "computing", "task_id": task_id}


@router.get("/api/v1/floor-plans/{fpid}/radio-map/status/{task_id}")
async def radio_map_status(fpid: uuid.UUID, task_id: str) -> dict:
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/api/v1/floor-plans/{fpid}/radio-map")
async def get_radio_map(fpid: uuid.UUID) -> dict:  # fpid used as key
    data = _radio_maps.get(str(fpid))
    if not data:
        raise HTTPException(status_code=404, detail="Radio map not computed yet")
    return {"radio_map": data}
