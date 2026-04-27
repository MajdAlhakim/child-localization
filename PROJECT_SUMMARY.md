# TRAKN — Project Summary for Report
**Indoor Child Localization System — Qatar University H07-C Corridor**
Senior Design Project, April 2026

---

## 1. System Overview

TRAKN tracks a child's indoor position in real time and streams it to a parent's smartphone. A wearable IoT tag collects IMU and Wi-Fi RSSI data every second and sends it over HTTPS to a cloud server. The server fuses the sensor data using Pedestrian Dead Reckoning (PDR) corrected by Wi-Fi RSSI localization, then pushes the position to the parent app via WebSocket.

---

## 2. System Architecture

```
[Wearable Tag]──HTTPS──▶[GCP Cloud Server]──WebSocket──▶[Parent Android App]
     │                        │
  [Scanner]──UART──▶[Tag]   [PostgreSQL DB]
```

### Components
| Component | Technology | Purpose |
|---|---|---|
| Tag (main board) | Beetle ESP32-C6, FreeRTOS | IMU sampling, HTTP POST, barometer |
| Tag (scanner board) | Beetle ESP32-C6 | Passive Wi-Fi RSSI scanning |
| Cloud backend | Python 3.11, FastAPI | PDR + RSSI fusion, WebSocket broadcast |
| Database | PostgreSQL 16 | Floor plans, AP map, grid |
| Web Mapping Tool | React 18, Konva.js | Floor plan upload, AP placement |
| Android AP Tool | Kotlin, Jetpack Compose | On-site AP surveying |
| Android Parent App | Kotlin, Jetpack Compose | Live child tracking display |
| Server infra | GCP e2-micro, Nginx, Docker Compose | Hosting, TLS termination |

---

## 3. Hardware Design

### Two-Board Tag Architecture
The tag was originally a single board handling both Wi-Fi scanning and TCP/TLS communication. This caused radio contention — the ESP32 cannot scan and maintain a TCP connection simultaneously, leading to scan blackouts and TLS timeouts. The solution splits the workload across two dedicated boards.

**Board 1 — Main Tag (Beetle ESP32-C6):**
- Samples MPU6050 IMU at 100 Hz
- Reads BMP180 barometer at ~1 Hz for floor detection
- Posts packets over HTTPS every ~1 second
- Radio used exclusively for TCP/TLS — never scans

**Board 2 — Scanner (Beetle ESP32-C6):**
- Puts Wi-Fi radio into station mode (no association needed)
- Passive channel sweep every 5 seconds
- Sends AP list as a JSON line over UART to the main board
- Never connects to any network

**UART Link:** Scanner GPIO16 (TX) → Tag GPIO17 (RX), 115200 baud, one-way.

### IMU — MPU6050
- I²C: SDA=GPIO19, SCL=GPIO20, 400 kHz
- Sampling rate: 100 Hz via `vTaskDelayUntil`
- Conversion constants (calibrated, locked):
  - Accelerometer: `raw × 0.0011978149 m/s²`
  - Gyroscope: `raw × 0.0002663309 rad/s`
- Register config: ±4g accelerometer, ±500°/s gyroscope, 21 Hz low-pass filter

### Barometer — BMP180
- I²C addr 0x77, shared bus with MPU6050 (mutex-protected)
- Measures altitude delta from Ground Floor baseline (sampled on boot)
- Floor thresholds: <−2m → Basement, −2–2.5m → Ground, 2.5–5.5m → Floor 1, >5.5m → Floor 2
- 10-reading confirmation window (~10s) before committing a floor change

---

## 4. Firmware

**Active file:** `firmware/beetle_c6_main/new_trakn_tag/new_trakn_tag.ino`

### FreeRTOS Task Structure (single-core Beetle C6)
| Task | Priority | Function |
|---|---|---|
| `imu_task` | 5 | MPU6050 read at 100 Hz, fills ring buffer |
| `uart_task` | 3 | Parse JSON scan from scanner Beetle via UART |
| `wifi_task` | 3 | Maintain Wi-Fi connection, BSSID-targeted roaming |
| `post_task` | 2 | Build + POST JSON packet every 1s |
| `baro_task` | 1 | BMP180 floor detection at ~1 Hz |

### Wi-Fi Reconnection
The wifi_task uses scanner RSSI data to target the strongest QU AP by BSSID, avoiding an ESP32 scan that would contend with the TCP radio. A reconnection bug was fixed: the original code had a status guard that only allowed `WiFi.begin()` from states `WL_IDLE`, `WL_DISCONNECTED`, or `WL_CONNECTED`. After a failed attempt the ESP32 enters `WL_CONNECT_FAILED` — blocked by the guard — causing 60–90 second blackouts. Fixed by calling `WiFi.disconnect(false)` before every `WiFi.begin()` to force state reset.

### Packet Format (JSON, sent every ~1s)
```json
{
  "mac": "9C:9E:6E:77:17:50",
  "ts": 12345,
  "floor": 1,
  "imu": [{"ts":..., "ax":..., "ay":..., "az":..., "gx":..., "gy":..., "gz":...}],
  "wifi": [{"bssid":"24:16:1B:76:28:C0", "ssid":"QU User", "rssi":-57, "ch":11}]
}
```
Each packet carries 25 IMU samples (250ms at 100Hz) and, when a fresh scan is available, the full AP list from the scanner.

---

## 5. Backend Server

**Technology:** Python 3.11, FastAPI, PostgreSQL 16, SQLAlchemy 2.0 async, Uvicorn, Docker.
**Hosting:** GCP e2-micro, Nginx reverse proxy (port 443 only), self-signed TLS certificate.

### Request Pipeline
```
POST /api/v1/gateway/packet
  → Authenticate (X-API-Key header)
  → Assign Tag ID (MAC → TRAKN-XXXX, in-memory)
  → Parse IMU samples → PDR engine
  → Parse Wi-Fi scan → RSSI localizer
  → RSSI anchor PDR position (if scan available)
  → Broadcast via WebSocket
  → Return 200 OK
```

### Data Flow
Every HTTPS packet triggers synchronous PDR computation. When the packet contains a Wi-Fi scan (every ~5s from the scanner), the RSSI localizer runs and snaps the PDR position to the RSSI estimate. Between scans, PDR runs alone.

---

## 6. Pedestrian Dead Reckoning (PDR)

**Verified accuracy:** 3.75% error over an 88-step, 64m test loop (SDP1 benchmark).

### Algorithm
1. **EMA filter** on accelerometer magnitude: `α = 1 − exp(−2π × 3.2 Hz × dt)`
2. **Gyro bias calibration:** mean of first 200 samples (~2s at 100Hz)
3. **Step detection** (all 5 conditions must hold on a 200ms rolling window):
   - Time since last step > 300ms
   - Peak > median + 0.8 × σ
   - Swing (max − min) > 0.7 × σ
   - σ > 0.3 m/s²
   - |mean − 9.8| > 0.1 m/s²
4. **Weinberg stride length:** `L = 0.47 × (a_max − a_min)^0.25`, clamped [0.25m, 1.40m]
5. **Heading integration:** `θ += gz_filtered × dt` with 0.02 rad/s dead zone

---

## 7. RSSI-Based Localization

### AP Calibration
Calibration was performed on-site in H07-C corridor. All enterprise APs are the same model (Aruba), so environment-wide constants apply:
- **Reference RSSI at 1m:** −38.0 dBm (2.4 GHz)
- **Path-loss exponent:** 2.1 (corridor environment)
- These constants are used in both the backend (`rssi_localizer.py`) and the parent app (`LocalizationEngine.kt`)

### Localization Pipeline
1. Collapse scan by physical AP prefix (first 5 BSSID octets — same physical radio across SSIDs)
2. Adaptive Kalman filter smooths RSSI per AP prefix (asymmetric Q: trusts signal increases, resists sudden drops from body blockage)
3. Log-distance path-loss model converts smoothed RSSI to distance: `d = 10^((−38 − rssi) / (10 × 2.1))`
4. Outlier rejection: remove APs > 2σ from mean distance; keep top 5
5. Quality gate: drop scan if avg Kalman residual > 20 dBm
6. Position: **inverse-square weighted centroid** (`w = 1 / (d² + 0.1)`) with 30% bounds check
7. **Three-zone adaptive EMA** smoothing on final position: α=0.50 (stationary) / 0.85 (walking) / 0.95 (fast), with hard 6m/scan jump cap

### BSSID Grouping (AP Tool)
Each physical AP broadcasts 3–6 BSSIDs (different SSIDs + 2.4/5 GHz bands). The AP tool groups BSSIDs by dropping the last hex digit of the MAC: `"24:16:1b:76:28:cd"` and `"24:16:1b:76:28:c1"` → same group. All bands are saved to the database so the parent phone (which can see 5 GHz) benefits from the same AP record.

### Beetle Antenna Compensation
The Beetle PCB antenna is ~4 dBm weaker than a phone antenna. The server applies a +4.0 dBm offset (`BEETLE_RSSI_OFFSET_DB`) to all tag scan values before localization to equalize distance estimates.

### Sensor Fusion (Soft)
Full EKF was not implemented in the project timeline. Instead, **soft RSSI anchoring** is used: whenever a valid RSSI position is computed, the PDR origin is snapped to it. This prevents unbounded PDR drift (~1.5m/min heading error) without the complexity of a full Kalman-based fusion filter. Scan interval is 5s, so PDR runs freely between snaps.

---

## 8. Android AP Surveying Tool

A dedicated Android app for placing APs on the floor plan. Workflow:
1. Select floor plan from server
2. Tap location on map → 5-second RSSI capture (500ms scan intervals)
3. Tool groups all detected BSSIDs by physical AP (macGroup), selects the group with the highest average RSSI
4. Confirm sheet shows best AP; press confirm → saves all BSSIDs to database with calibrated `rssiRef=−38.0`, `pathLossN=2.1`
5. ScanViewModel maintains a 5-scan rolling RSSI average per BSSID for stable reference values

---

## 9. Android Parent App

Displays live child position on the floor plan. Key implementation details:

- Connects to `WSS /ws/position/{tag_id}` at startup
- Receives JSON position updates; renders dot on Konva canvas floor plan
- `LocalizationEngine.kt` runs the same RSSI localization algorithm client-side for the phone's own position (comparing phone location vs child location)
- No smoothing layer in the ViewModel — raw filtered scan passed directly to the engine to avoid compounding delays (triple-smoothing bug was fixed: ViewModel EMA + engine trimmed-mean + position EMA was causing ~20s lag)

---

## 10. Key Numbers and Results

| Metric | Value |
|---|---|
| PDR step accuracy | 3.75% error over 64m (88 steps) |
| RSSI scan interval (scanner board) | 5 seconds |
| RSSI anchor interval (server) | ~5 seconds (every scan with ≥1 known AP) |
| HTTP POST interval (tag) | ~1 second (1000ms interval + ~1.5s TLS overhead) |
| WebSocket update rate | Every POST (~1s IMU-only, ~5s RSSI-anchored) |
| Path-loss exponent (H07-C) | 2.1 (corridor, measured on-site) |
| Reference RSSI at 1m | −38.0 dBm (2.4 GHz, Aruba AP) |
| Max anchors used for position | 5 (top-5 after outlier rejection) |
| Position EMA — stationary | α = 0.50 |
| Position EMA — walking | α = 0.85 |
| Jump cap per scan | 6 m |
| Floor detection settling time | ~10 seconds (10-reading confirmation) |

---

## 11. Known Limitations

- **PDR heading drift:** ~1.5m/min without RSSI correction. The 5s anchor interval keeps accumulated error below ~0.1m between snaps.
- **Tag WiFi reconnection:** After a network dropout, reconnection takes 3–6s. A residual ~1 minute blackout was observed under certain conditions (TLS handshake stall with `setReuse(false)` — every POST opens a new TLS session, which takes ~1.5s over QU's network to GCP).
- **Single floor plan:** System currently targets one floor plan at a time. Multi-floor tracking via barometer is implemented in firmware and gateway but the parent app UI only renders one floor at a time.
- **No authentication:** Parent app connects directly with a shared API key. JWT-based auth (TASK-15) was not implemented.
- **In-memory tag registry:** Tag ID (TRAKN-XXXX) is lost on server restart; tag must re-register.

---

## 12. File Structure Reference

```
child-localization/
├── firmware/
│   ├── beetle_c6_main/new_trakn_tag/   ← ACTIVE tag firmware
│   └── beetle_c6_scanner/              ← Scanner board firmware
├── backend/
│   └── app/
│       ├── api/gateway.py              ← Main packet handler + fusion
│       ├── api/websocket.py            ← WebSocket position stream
│       ├── fusion/pdr.py               ← PDR engine
│       └── fusion/rssi_localizer.py    ← RSSI positioning
├── app/web-react/                      ← Web mapping tool (source)
├── app/web/                            ← Built web tool (served by nginx)
├── tools/trakn-ap-tool/                ← Android AP surveying app
├── tools/trakn-parent-app/             ← Android parent tracking app
├── docker-compose.yml
└── nginx/nginx.conf
```
