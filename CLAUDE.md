# TRAKN — Project Context for Claude

Read this file before doing anything. It contains the complete project context so you don't need to re-read source files to understand the system.

---

## What This Project Is

**TRAKN** — indoor child localization system for Qatar University Building H07, C Corridor.
A two-board IoT tag worn by a child streams IMU + Wi-Fi RSSI data to a GCP cloud server over HTTPS. The server runs Pedestrian Dead Reckoning (PDR) + RSSI-based positioning and pushes live position updates via WebSocket to a parent's Android app.

**Senior Design Project — QU, 4 members, completed April 2026.**

---

## Stack at a Glance

| Component | Tech | Location |
|---|---|---|
| Tag (main board) | Beetle ESP32-C6, FreeRTOS, Arduino | `firmware/beetle_c6_main/new_trakn_tag/` |
| Tag (scanner board) | Beetle ESP32-C6, Arduino | `firmware/beetle_c6_scanner/` |
| Backend | Python 3.11, FastAPI, PostgreSQL 16, SQLAlchemy 2.0 async | `backend/` |
| Web Mapping Tool | React 18 + Vite + Tailwind + Konva.js + Zustand | `app/web-react/` (builds to `app/web/`) |
| Android AP Tool | Kotlin + Jetpack Compose + Retrofit 2 | `tools/trakn-ap-tool/` |
| Android Parent App | Kotlin + Jetpack Compose + Retrofit 2 | `tools/trakn-parent-app/` |
| Server infra | GCP e2-micro, Nginx → FastAPI → PostgreSQL, Docker Compose | `docker-compose.yml`, `nginx/nginx.conf` |

**Active firmware: `firmware/beetle_c6_main/new_trakn_tag/new_trakn_tag.ino` — this is what runs on the tag.**
`firmware/beetle_c6_tag/beetle_c6_tag.ino` is an older prototype; do not flash it.

**Flutter, React Native, and old vanilla-JS mapping tool have been removed.**

---

## Hardware

### Two-board tag architecture
Single-radio contention (TLS + scan simultaneously) was the root problem. Solved by two dedicated boards.

| Board | Role | Radio use |
|---|---|---|
| Beetle ESP32-C6 (main tag) | IMU sampling (100Hz) + barometer + HTTP POST (1000ms) | TCP/TLS only — never scans |
| Beetle ESP32-C6 (scanner) | Passive Wi-Fi scan every 5s | Scan only — never connects |

**UART link:** scanner Beetle GPIO16 (TX) → tag Beetle GPIO17 (RX), 115200 baud, `Serial1`, one-way.

### IMU — MPU6050
- I²C shared bus: SDA=GPIO19, SCL=GPIO20 on Beetle ESP32-C6 tag
- Rate: 100Hz via `vTaskDelayUntil`
- Protected by `i2c_mutex` shared with baro_task
- **LOCKED constants (never change):**
  - `ax_SI = raw × 0.0011978149 m/s²`
  - `gz_SI = raw × 0.0002663309 rad/s`
- Register config: PWR_MGMT_1=0x00, GYRO_CONFIG=0x08, ACCEL_CONFIG=0x08, CONFIG=0x04

### Barometer — BMP180
- I²C addr 0x77, shared bus with MPU6050 (GPIO19/20), protected by `i2c_mutex`
- Measures floor via altitude delta from Ground Floor baseline (sampled at boot)
- Floor thresholds: <−2.0m → Basement(−1), −2.0–2.5m → Ground(0), 2.5–5.5m → Floor 1(1), >5.5m → Floor 2(2)
- `BARO_CONFIRM_THRESHOLD = 10` consecutive readings (~10s) before committing floor change
- `FLOOR_HEIGHT_M = 3.5`
- Reports `floor` field in every POST packet

### Network
- Tag MAC: `9C:9E:6E:77:17:50` (registered on QU-User, MAC-authenticated, no password)
- Home dev: SSID=`Alhakim`, PASS=`sham@2014`
- QU: SSID=`QU User`, PASS=`""`
- Server: `https://35.238.189.188/api/v1/gateway/packet`, port 443 only (QU firewall)
- TLS: self-signed cert, `client.setInsecure()`
- POST interval: 1000ms; actual rate ~2.5s due to TLS handshake cost per request (`http.setReuse(false)`)

### WiFi reconnection (fixed April 2026)
`connect_to_best_ap()` now calls `WiFi.disconnect(false)` before every `WiFi.begin()`. The old status guard (`WL_IDLE || WL_DISCONNECTED || WL_CONNECTED` only) caused the function to return early when WiFi entered `WL_CONNECT_FAILED` or `WL_NO_SSID_AVAIL`, producing 60–90 s blackouts (verified in logs: 83s gap = ~27 wasted 3s retry iterations).

---

## Backend

### Key files
- `backend/app/main.py` — FastAPI app, CORS, lifespan (creates DB tables on startup)
- `backend/app/models.py` — SQLAlchemy ORM: `Venue`, `FloorPlan`, `AccessPoint`, `GridPoint`
- `backend/app/api/gateway.py` — `POST /api/v1/gateway/packet`, PDR + RSSI pipeline, WebSocket broadcast
- `backend/app/api/venue.py` — legacy single-floor endpoints (backward compat)
- `backend/app/api/venues.py` — multi-floor venue CRUD
- `backend/app/api/tags.py` — tag list, rename, QR code
- `backend/app/api/websocket.py` — `WSS /ws/position/{tag_id}`
- `backend/app/fusion/pdr.py` — PDR engine (in-memory, per-device)
- `backend/app/fusion/rssi_localizer.py` — RSSI Kalman + log-distance + weighted centroid positioning
- `backend/app/fusion/device_state.py` — per-device state dataclass (PDREngine + IMU buffer + Kalman states)
- `backend/app/fusion/tag_registry.py` — MAC → TRAKN-XXXX auto-assignment (in-memory)
- `backend/app/core/broadcaster.py` — WebSocket broadcaster singleton

### Auth
- Device → server: `X-API-Key: 580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990`
- JWT/parent auth: **not implemented** (TASK-15)

### Environment variables
- `BEETLE_RSSI_OFFSET_DB = 4.0` — compensates for Beetle PCB antenna being ~4 dBm weaker than a phone antenna. Applied to all RSSI values before passing to rssi_localizer. Set in `docker-compose.yml`.

### DB schema (actual)
```
Venue         (id, name, description, created_at)
FloorPlan     (id, venue_id→Venue, name, floor_number, scale_px_per_m, grid_spacing_m, image_path, created_at)
AccessPoint   (id, floor_plan_id→FloorPlan, group_id, bssid, ssid, rssi_ref, path_loss_n, x, y, ceiling_height)
GridPoint     (id, floor_plan_id→FloorPlan, x, y)
```
**Not in DB:** users, device_links, devices (TagRegistry is in-memory), radio_map (in-memory), positions.

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

### Step detection (all 5 must be true, rolling 200ms buffer of EMA-filtered a_mag)
```
INVARIANT: MIN_STEP_DT_MS (300) > STEP_BUFFER_MS (200) — ensures the old step
           peak expires from the buffer before the cooldown ends.

(1) dt_since_last_step > 300ms               [MIN_STEP_DT_MS=300]
(2) a_max > median(buf) + 0.8 × std(buf)     [STD_FACTOR=0.8]
(3) a_max − a_min > 0.7 × std(buf)           [SWING_FACTOR=0.7]
(4) std(buf) > 0.3 m/s²                       [MIN_STD=0.3]
(5) |mean(buf) − 9.8| > 0.1 m/s²             [MIN_MEAN_DELTA=0.1]
```

### Weinberg stride (LOCKED)
```
L = 0.47 × (a_max − a_min)^0.25
L = clamp(L, 0.25m, 1.40m)
```

---

## RSSI Localizer (`backend/app/fusion/rssi_localizer.py`)

Parallel implementation to `LocalizationEngine.kt` (parent app). Both use identical constants.

### Calibrated 2.4 GHz constants (H07-C corridor, verified on-site)
```python
_RSSI_REF_DBM = -38.0   # measured RSSI at 1 m reference distance
_PATH_LOSS_N  =  2.1    # corridor path-loss exponent
```
These override per-AP DB values — all enterprise APs in H07-C are the same model and the corridor path-loss exponent is environment-wide.

### Pipeline
1. **Collapse** scan by physical AP prefix (first 5 BSSID octets); strongest RSSI wins per prefix
2. **Adaptive Kalman** smooth RSSI per prefix — asymmetric Q: Q=3.0 for sudden increase (movement), Q=5.0 for sudden drop (body blockage), Q=1.0 stable
3. **Drop** anchors with raw RSSI < −90 dBm
4. **Log-distance** distance estimate, clamped [0.3m, 80m]:
   `dist = 10^((_RSSI_REF_DBM − rssi_smoothed) / (10 × _PATH_LOSS_N))`
5. **Sort** nearest-first; break ties by strongest raw RSSI
6. **Outlier rejection** — remove anchors > 2σ from mean distance (when >3 anchors)
7. **Top-5** anchors only
8. **Quality check** — drop scan if `avg_rssi_error > 20 dBm` (Kalman residual measure)
9. **Snap** — if strongest raw RSSI > −40 dBm, snap position to that AP (unmistakably adjacent)
10. **Position estimate:**
    - 1 anchor → `None` (distance only, no position)
    - ≥2 anchors → inverse-square weighted centroid: `w = 1 / (d² + 0.1)`; bounds-checked (30% margin), falls back to top-3 centroid if out of bounds
11. **Three-zone adaptive EMA** with hard 6m/scan jump cap:
    - movement < 0.5m → α=0.50 (stationary)
    - movement 0.5–4m → α=0.85 (walking)
    - movement > 4m  → α=0.95 (fast)
    - Position state stale after 15s — accept new position directly (no blend)

### RSSI anchoring in gateway
`BEETLE_RSSI_OFFSET_DB=4.0` applied to all scan RSSIs before localization (compensates for Beetle antenna).
When `anchor_count >= 1`, PDR position is snapped to RSSI estimate each scan (~5s interval).

WebSocket message fields:
- `source = "rssi_anchored"` / `"pdr_only"`
- `mode = "fused"` / `"imu_only"`
- `confidence = min(1.0, anchor_count / 5.0)`
- `rssi_anchors`, `rssi_error`

---

## Android AP Tool (`tools/trakn-ap-tool/`)

Used to survey and register AP positions. Tap a location on the floor plan → 5-second RSSI capture → confirm and save.

### BSSID grouping (`macGroup()`)
Two BSSIDs belong to the same physical AP if their MAC minus the last hex digit is identical:
- `"24:16:1b:76:28:cd"` and `"24:16:1b:76:28:c1"` → group `"24:16:1b:76:28:c"` ✓
- Saves **all bands** (2.4 GHz + 5 GHz) — parent phone needs 5 GHz BSSIDs

### Calibration constants saved
```kotlin
rssiRef   = -38.0   // measured at 1 m, 2.4 GHz
pathLossN = 2.1     // H07-C corridor
```

### RSSI averaging
ScanViewModel keeps a 5-scan rolling average per BSSID to produce stable rssiRef values.

---

## Android Parent App (`tools/trakn-parent-app/`)

### LocalizationEngine.kt
Client-side RSSI positioning — same algorithm as `rssi_localizer.py`.

```kotlin
private const val RSSI_WINDOW  = 1      // no trimmed-mean smoothing — pass raw RSSI directly
private const val MAX_JUMP_M   = 6.0    // hard position jump cap per scan
// EMA alphas
val alpha = when {
    movement < 0.5 -> 0.50
    movement < 4.0 -> 0.85
    else           -> 0.95
}
val w = 1.0 / (d * d + 0.1)            // inverse-square weight
```

### LocateViewModel.kt
- No ViewModel-level RSSI EMA (removed — caused triple-smoothing = ~20s lag)
- Passes filtered scan (RSSI ≥ MIN_RSSI_DBM) directly to LocalizationEngine
- Uses only 2.4 GHz path-loss constants (`RSSI_AT_1M = -38.0`, `PATH_LOSS_EXP = 2.1`)

---

## Web Mapping Tool

- **Source:** `app/web-react/` (React 18 + Vite + Tailwind + Konva.js + Zustand)
- **Build output:** `app/web/` — served by nginx at `/tool/`
- **Build command:** `cd app/web-react && npm install && npm run build`
- **Dev:** `npm run dev` → `http://localhost:5173/tool/`

6-step workflow: Floor Plan → Zones → Grid (0.5m) → APs → Radio Map → Export

---

## Deployment

```
Nginx (443) → FastAPI (8000 internal) → PostgreSQL 16
```

- Docker Compose: `docker compose up -d --build`
- nginx serves `app/web/` at `/tool/` (volume mount)
- Backend internal port 8000 never exposed publicly

### Deploy workflow
```bash
cd ~/child-localization && git pull
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
| Android Parent App (Kotlin) | ✅ Done (no auth — tracking screen functional) |
| Barometer floor detection (BMP180) | ✅ Done (firmware + gateway floor mapping) |
| RSSI Kalman filter + log-distance | ✅ Done |
| Inverse-square weighted centroid | ✅ Done (replaced WRLS) |
| RSSI anchoring of PDR (soft fusion) | ✅ Done |
| 2.4 GHz calibration constants | ✅ Done (rssiRef=−38.0, n=2.1, verified on-site) |
| BSSID grouping fix (all-band AP saves) | ✅ Done |
| Beetle antenna RSSI offset correction | ✅ Done (BEETLE_RSSI_OFFSET_DB=4.0) |
| Tag WiFi reconnection blackout fix | ✅ Done (WiFi.disconnect(false) pre-call) |
| EKF sensor fusion | 🔲 TASK-06 |
| Auth (JWT login, device link) | 🔲 TASK-15 |
| Position persistence to DB | 🔲 TASK-16 |
| Tag registry persistence | 🔲 TASK-17 |
| QR scanner in parent app | 🔲 TASK-18 |
| Radio map DB persistence | 🔲 TASK-19 |

---

## Open Questions

| ID | Question | Impact | Status |
|---|---|---|---|
| OQ-01 | AP physical coordinates in H07-C | High | ✅ Surveyed — re-mapped with corrected tool |
| OQ-02 | Path loss exponent n for H07-C | Medium | ✅ Measured — n=2.1, rssiRef=−38.0 dBm |

---

## What NOT to Do

- Never use `xTaskCreatePinnedToCore()` on Beetle C6 — it is single-core
- Never change the IMU conversion constants without re-running the 88-step SDP1 benchmark
- Never expose port 8000 publicly — all traffic must go through nginx on 443
- Do not flash `beetle_c6_tag.ino` — the active firmware is `new_trakn_tag.ino`
- Do not change `_RSSI_REF_DBM` or `_PATH_LOSS_N` without re-measuring on-site; these are calibrated for H07-C
- Do not re-add ViewModel-level RSSI EMA in LocateViewModel — it caused ~20s triple-smoothing lag
- The `tools/web-mapping/` (vanilla JS), `app/lib/` (Flutter), `tools/trakn-ap-tool-rn/`, `tools/trakn-parent-app-rn/` have all been removed — do not re-add them
