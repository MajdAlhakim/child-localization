# TRAKN — Project Context for Claude

Read this file before doing anything. It contains the complete project context so you don't need to re-read source files to understand the system.

---

## What This Project Is

**TRAKN** — indoor child localization system for Qatar University Building H07, C Corridor.
A two-board IoT tag worn by a child streams IMU + Wi-Fi RSSI data to a GCP cloud server over HTTPS. The server runs Pedestrian Dead Reckoning (PDR) and pushes live position updates via WebSocket to a parent's Android app.

**Senior Design Project — QU, 4 members, active April 2026.**

---

## Stack at a Glance

| Component | Tech | Location |
|---|---|---|
| Tag (main board) | XIAO ESP32-C5, FreeRTOS, Arduino | `firmware/esp32c5/trakn_tag/` |
| Tag (scanner board) | Beetle ESP32-C6, Arduino | `firmware/beetle_c6_scanner/` |
| Backend | Python 3.11, FastAPI, PostgreSQL 16, SQLAlchemy 2.0 async | `backend/` |
| Web Mapping Tool | React 18 + Vite + Tailwind + Konva.js + Zustand | `app/web-react/` (builds to `app/web/`) |
| Android AP Tool | Kotlin + Jetpack Compose + WifiRttManager + Retrofit 2 | `tools/trakn-ap-tool/` |
| Android Parent App | Kotlin + Jetpack Compose + Retrofit 2 | `tools/trakn-parent-app/` |
| Server infra | GCP e2-micro, Nginx → FastAPI → PostgreSQL, Docker Compose | `docker-compose.yml`, `nginx/nginx.conf` |

**Flutter, React Native, and old vanilla-JS mapping tool have been removed.**

---

## Hardware

### Two-board tag architecture
Single-radio contention (TLS + scan simultaneously) was the root problem. Solved by two dedicated boards.

| Board | Role | Radio use |
|---|---|---|
| XIAO ESP32-C5 | IMU sampling (100Hz) + HTTP POST (200ms) | TCP/TLS only — never scans |
| Beetle ESP32-C6 (DFR1117) | Passive Wi-Fi scan every 10s | Scan only — never connects |

**UART link:** Beetle GPIO16 (TX) → ESP32-C5 GPIO12 (RX), 115200 baud, `Serial1`, one-way.

### IMU — MPU6050
- I²C: SDA=GPIO23, SCL=GPIO24 on XIAO ESP32-C5
- Rate: 100Hz via `vTaskDelayUntil`
- **LOCKED constants (never change):**
  - `ax_SI = raw × 0.0011978149 m/s²`
  - `gz_SI = raw × 0.0002663309 rad/s`
- Register config: PWR_MGMT_1=0x00, GYRO_CONFIG=0x08, ACCEL_CONFIG=0x08, CONFIG=0x04

### Network
- ESP32-C5 MAC: `24:42:E3:15:E5:72` (registered on QU-User, MAC-authenticated, no password)
- Home dev: SSID=`Alhakim`, PASS=`sham@2014`
- QU: SSID=`QU-User`, PASS=`""`
- Server: `https://35.238.189.188/api/v1/gateway/packet`, port 443 only (QU firewall)
- TLS: self-signed cert, `client.setInsecure()`

---

## Backend

### Key files
- `backend/app/main.py` — FastAPI app, CORS, lifespan (creates DB tables on startup)
- `backend/app/models.py` — SQLAlchemy ORM: `Venue`, `FloorPlan`, `AccessPoint`, `GridPoint`
- `backend/app/api/gateway.py` — `POST /api/v1/gateway/packet`, PDR pipeline, WebSocket broadcast
- `backend/app/api/venue.py` — legacy single-floor endpoints (backward compat)
- `backend/app/api/venues.py` — multi-floor venue CRUD
- `backend/app/api/tags.py` — tag list, rename, QR code
- `backend/app/api/websocket.py` — `WSS /ws/position/{tag_id}`
- `backend/app/fusion/pdr.py` — PDR engine (in-memory, per-device)
- `backend/app/fusion/tag_registry.py` — MAC → TRAKN-XXXX auto-assignment (in-memory)
- `backend/app/core/broadcaster.py` — WebSocket broadcaster singleton

### Auth
- Device → server: `X-API-Key: 580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990`
- JWT/parent auth: **not implemented yet** (TASK-15)

### DB schema (actual, not PRD fantasy)
```
Venue         (id, name, description, created_at)
FloorPlan     (id, venue_id→Venue, name, floor_number, scale_px_per_m, grid_spacing_m, image_path, created_at)
AccessPoint   (id, floor_plan_id→FloorPlan, group_id, bssid, ssid, rssi_ref, path_loss_n, x, y, ceiling_height)
GridPoint     (id, floor_plan_id→FloorPlan, x, y)
```
**Not in DB:** users, device_links, devices (TagRegistry is in-memory), radio_map (in-memory), positions.

### Radio map
Computed in-memory (background task), keyed by floor_plan UUID. Lost on server restart.

### Tag IDs
Auto-assigned `TRAKN-XXXX` (4 random uppercase alphanumeric), in-memory only. Mapped from MAC address. Lost on server restart.

---

## PDR Engine (`backend/app/fusion/pdr.py`)

All verified in SDP1 (88 steps, 64m loop, 3.75% error). **Do not change locked constants without re-verification.**

### EMA filter
```
FC = 3.2 Hz
α = 1 − exp(−2π × FC × dt)
```

### Gyro bias calibration
```
bias_gz = mean(gz_samples[:200])   # first 200 samples = 2s at 100Hz
```

### Gyro dead zone
```
GYRO_DEAD_ZONE = 0.02 rad/s  — treat as zero below this to suppress noise drift
```

### Step detection (all 5 must be true, rolling 400ms buffer of EMA-filtered a_mag)
```
INVARIANT: MIN_STEP_DT_MS (500) > STEP_BUFFER_MS (400) — ensures the old step
           peak expires from the buffer before the cooldown ends.

Buffer contains EMA-filtered a_mag_filt values (not raw a_mag) to suppress
high-frequency noise spikes that caused false detections.

(1) dt_since_last_step > 500ms               [MIN_STEP_DT_MS=500]
(2) a_max > median(buf) + 2.0 × std(buf)     [STD_FACTOR=2.0]
(3) a_max − a_min > 0.9 × std(buf)           [SWING_FACTOR=0.9]
(4) std(buf) > 0.5 m/s²                       [MIN_STD=0.5]
(5) |mean(buf) − 9.8| > 0.1 m/s²             [MIN_MEAN_DELTA=0.1]
```

Bias calibration no longer causes an early return — step detection runs from
sample 0 (heading uses bias_gz=0 for the first ~2 s, acceptable). Broadcasts
are still gated on bias_calibrated=True in gateway.py.

### Weinberg stride (LOCKED)
```
L = 0.47 × (a_max − a_min)^0.25
L = clamp(L, 0.25m, 1.40m)
```

---

## Web Mapping Tool

- **Source:** `app/web-react/` (React 18 + Vite + Tailwind + Konva.js + Zustand)
- **Build output:** `app/web/` — served by nginx at `https://trakn.duckdns.org/tool/`
- **Vite config:** `base: '/tool/'`, `outDir: '../web'`, dev proxy on `/api`, `/ws`, `/health`
- **API client:** relative paths, no hardcoded server URL
- **Build command:** `cd app/web-react && npm install && npm run build`
- **Dev:** `npm run dev` → `http://localhost:5173/tool/`

6-step workflow: Floor Plan → Zones (walkable polygon) → Grid (0.5m) → APs → Radio Map → Export

---

## Deployment

```
Nginx (443) → FastAPI (8000 internal) → PostgreSQL 16
```

- Docker Compose: `docker compose up -d --build`
- Web tool must be built before deploy: `cd app/web-react && npm run build`
- nginx serves `app/web/` at `/tool/` (volume mount in docker-compose)
- Backend internal port 8000 never exposed publicly

### Deploy workflow
```bash
cd ~/child-localization && git pull
cd app/web-react && npm install && npm run build
cd ../..
docker compose up -d --build backend
docker logs -f child-localization-backend-1 --tail 20
```

---

## Implementation Status

| Task | Status |
|---|---|
| Project structure + Docker | ✅ Done |
| Gateway endpoint + packet logging | ✅ Done |
| PDR engine (in-memory) | ✅ Done |
| WebSocket broadcaster | ✅ Done |
| Venue/FloorPlan/AP/Grid DB + API | ✅ Done |
| Web Mapping Tool (React) | ✅ Done |
| Android AP Localization Tool (Kotlin) | ✅ Done |
| Android Parent App (Kotlin) | ✅ Done (partial — no auth, tracking screen WIP) |
| RSSI Kalman filter + log-distance | 🔲 TASK-04 |
| Weighted trilateration + scoring | 🔲 TASK-05 |
| EKF sensor fusion | 🔲 TASK-06 |
| Auth (JWT login, device link) | 🔲 TASK-15 |
| Position persistence to DB | 🔲 TASK-16 |
| Tag registry persistence | 🔲 TASK-17 |
| QR scanner in parent app | 🔲 TASK-18 |
| Radio map DB persistence | 🔲 TASK-19 |
| Integration test — full pipeline walk | 🔲 TASK-13 |
| Walk accuracy benchmark | 🔲 TASK-14 |

**Current server output:** PDR-only. Every WebSocket message has `source="pdr_only"`, `mode="imu_only"`, `confidence=0.0`. EKF not yet wired.

---

## Open Questions

| ID | Question | Impact |
|---|---|---|
| OQ-01 | AP physical coordinates in H07-C — manual survey required | High |
| OQ-02 | Path loss exponent n for H07-C — needs on-site measurement | Medium |

---

## What NOT to Do

- Never use `xTaskCreatePinnedToCore()` on ESP32-C5 — it is single-core
- Never change the IMU conversion constants without re-running the 88-step SDP1 benchmark
- Never expose port 8000 publicly — all traffic must go through nginx on 443
- Do not add a `radio_map` DB table without first checking the in-memory approach isn't sufficient
- The `tools/web-mapping/` (vanilla JS), `app/lib/` (Flutter), `tools/trakn-ap-tool-rn/`, and `tools/trakn-parent-app-rn/` (React Native) have all been removed — do not re-add them
