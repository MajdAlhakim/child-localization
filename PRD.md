# Product Requirements Document

## TRAKN — Indoor Child Localization System

### Qatar University — Building H07, C Corridor

**Version:** 6.0
**Date:** March 2026
**Status:** Active — Senior Design Project
**Team:** 4 members

**Changelog from v5.0:**

- Hardware: Single-board tag (XIAO ESP32-C5 only) replaced with **two-board tag architecture**
  - XIAO ESP32-C5: IMU sampling + HTTP POST (radio dedicated to TCP/TLS only)
  - Beetle ESP32-C6: dedicated Wi-Fi scanner (radio dedicated to scanning only)
  - BW16 (RTL8720DN): retired — Realtek SDK does not expose per-AP BSSID from scan results
- Root cause resolved: single-radio contention between TCP/TLS and Wi-Fi channel sweep eliminated
- UART link: Beetle C6 GPIO16 (TX) → ESP32-C5 GPIO12 (RX) at 115200 baud
- Beetle C6 does NOT connect to Wi-Fi — scanning works without association (passive beacon collection)
- POST interval: 200ms (5 packets/sec) — reduced from 50ms for power saving
- IMU batch: 5 samples drained per POST — no backlog, no large packets
- Scan interval: 10s — Beetle C6 scans freely with no radio contention
- Firmware: confirmed end-to-end working — `[POST] 200, wifi=yes` verified in Serial Monitor

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [System Architecture](#3-system-architecture)
4. [Hardware Components](#4-hardware-components)
5. [Communication and Connectivity](#5-communication-and-connectivity)
6. [Firmware Requirements](#6-firmware-requirements)
7. [Backend Server Requirements](#7-backend-server-requirements)
8. [Sensor Fusion Engine](#8-sensor-fusion-engine)
9. [Web Mapping Tool](#9-web-mapping-tool)
10. [Android AP Localization Tool](#10-android-ap-localization-tool)
11. [Mobile Parent Application](#11-mobile-parent-application)
12. [Calibration System](#12-calibration-system)
13. [Performance Requirements](#13-performance-requirements)
14. [Failure Modes and Recovery](#14-failure-modes-and-recovery)
15. [Database Schema](#15-database-schema)
16. [API Contracts](#16-api-contracts)
17. [Infrastructure and Deployment](#17-infrastructure-and-deployment)
18. [Testing Requirements](#18-testing-requirements)
19. [Implementation Plan](#19-implementation-plan)
20. [Open Questions](#20-open-questions)
21. [Glossary](#21-glossary)

---

## 1. Project Overview

TRAKN is a real-time indoor child localization system for deployment in Qatar University Building H07, C Corridor. A child wears a compact two-board IoT tag. If separated from their parent, the parent opens the TRAKN mobile application, enters the tag's unique ID, and sees their child's position plotted in real time on the venue floor map.

The system fuses two complementary positioning methods:

| Method | Strength | Weakness |
|---|---|---|
| **PDR (IMU-based)** | 100 Hz, continuous motion tracking | Drifts over time |
| **Wi-Fi RSSI positioning** | Absolute position reference, drift-free | ~10s scan cycle, affected by multipath |

Sensor fusion via an **Extended Kalman Filter (EKF)** combines both: PDR provides continuous high-frequency position updates while RSSI corrections prevent drift accumulation.

**Positioning method:** RSSI log-distance path loss model + weighted intersection point scoring. AP locations are determined once during venue setup using the Android AP Localization Tool, then used to build a pre-computed radio map. At runtime, live RSSI readings are matched against the radio map to estimate position.

**Deployment model:** Tags are venue-managed assets. A parent links to a specific tag by entering the **unique tag ID** printed on the device into the mobile app.

**Hardware status:** Two-board firmware confirmed working end-to-end as of March 2026.

---

## 2. Problem Statement

GPS does not penetrate indoor environments. Fingerprint-based Wi-Fi localization requires expensive site surveys. Camera-based tracking raises privacy concerns.

RSSI log-distance ranging against known AP positions, fused with IMU-based PDR, provides a practical alternative. The QU H07 corridor has existing Wi-Fi infrastructure that serves as RSSI anchors.

**Key constraints:**

- Single-radio chips cannot scan and maintain TCP/TLS simultaneously — solved by two-board architecture
- QU APs do not support cooperative two-sided FTM ranging at runtime
- ESP32-C5 MAC `24:42:E3:15:E5:72` registered on QU-User Wi-Fi — no password needed on-site
- GCP cloud VM used for server hosting — university network not reliable for hosting
- Port 8000 blocked by QU firewall — all traffic through Nginx on port 443
- AP physical coordinates not available from IT — manual survey required

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRAKN Tag (wearable)                               │
│                                                                               │
│  ┌──────────────────────┐   UART 115200 baud    ┌────────────────────────┐  │
│  │  Beetle ESP32-C6     │ ─────────────────────►│  XIAO ESP32-C5         │  │
│  │  (scanner board)     │   GPIO16→GPIO11        │  (main board)          │  │
│  │                      │   JSON line per scan   │                        │  │
│  │  • WiFi.mode(STA)    │                        │  • MPU6050 IMU 100Hz   │  │
│  │  • No association    │                        │  • FreeRTOS 4 tasks    │  │
│  │  • Passive scan      │                        │  • HTTP POST 200ms     │  │
│  │  • Every 10s         │                        │  • TLS keepalive       │  │
│  │  • Full BSSID+RSSI   │                        │  • MAC: 24:42:E3:...   │  │
│  └──────────────────────┘                        └──────────┬─────────────┘  │
│                                                             │                 │
└─────────────────────────────────────────────────────────────┼─────────────────┘
                                                              │ HTTPS POST port 443
                                                              │ JSON, 200ms interval
                                                              ▼
                                              ┌───────────────────────────────┐
                                              │   GCP Cloud Server            │
                                              │   35.238.189.188              │
                                              │   Nginx → FastAPI → PDR+EKF  │
                                              └───────────────┬───────────────┘
                                                              │ WSS port 443
                                                              ▼
                                              ┌───────────────────────────────┐
                                              │   Flutter Parent App          │
                                              │   Enter Tag ID → Live Map     │
                                              └───────────────────────────────┘
```

**Why two boards:**
A single ESP32 radio cannot simultaneously maintain a TLS TCP connection (needs continuous radio attention) and perform a passive Wi-Fi channel sweep across 13 channels (~10–25s depending on AP density). Attempting both causes TLS timeouts and dropped packets. The two-board architecture gives each job a dedicated radio with zero contention.

**Data flow (runtime):**

1. Beetle C6 passively scans all channels every 10s, sends JSON line over UART to ESP32-C5
2. ESP32-C5 reads MPU6050 at 100Hz, batches 5 samples, POSTs JSON to server every 200ms
3. Each POST includes IMU samples + latest RSSI scan if one arrived since last POST
4. Server runs PDR on IMU samples, runs RSSI positioning when scan arrives, EKF fuses both
5. Position pushed to parent app via WebSocket

**Setup flow (one-time per venue):**

1. Upload floor plan to Web Mapping Tool, define walkable area, generate 0.5m grid
2. Walk venue with Android AP Localization Tool, pin AP locations on map
3. Web Mapping Tool computes radio map (estimated RSSI at every grid point from every AP)
4. Radio map stored in database — used by backend at runtime

---

## 4. Hardware Components

### 4.1 Tag — Two-Board Assembly

The tag consists of two boards enclosed together in a single 3D-printed enclosure:

| Board | Role | Connects to |
|---|---|---|
| XIAO ESP32-C5 | IMU + HTTP POST | Wi-Fi network, server, MPU6050 via I²C, Beetle via UART RX |
| Beetle ESP32-C6 | Wi-Fi scanner | XIAO ESP32-C5 via UART TX |

**Enclosure:** 3D-printed, waist-clip mount, vented dash holes for passive convection.
**Mounting:** Child's belt loop or bag strap at waist level (not wrist — IMU accuracy requires waist mount).
**Power:** Single shared LiPo battery (1000mAh recommended — 8 hours at optimised intervals).

**Thermal profile:**

```
ESP32-C5 average current:  ~45mA
Beetle C6 average current: ~75mA
MPU6050:                   ~3.5mA
Total:                     ~124mA @ 3.3V = ~410mW
Temperature rise (vented enclosure, 9°C/W): ~4°C above ambient
Surface temp at 22°C ambient: ~26°C — not noticeable
```

### 4.2 XIAO ESP32-C5 (Main Board)

| Property | Value |
|---|---|
| SoC | ESP32-C5, single-core RISC-V 240MHz |
| Role | IMU sampling, JSON POST to server |
| Wi-Fi | 2.4GHz + 5GHz — used for TCP/TLS only, never scans |
| MAC | `24:42:E3:15:E5:72` (registered with QU IT) |
| Board package | esp32 by Espressif v3.3.5+ |
| Board selection | XIAO_ESP32C5 |
| USB CDC On Boot | Enabled |
| I²C pins | SDA=GPIO23 (D4), SCL=GPIO24 (D5) |
| UART RX pin | GPIO12 (receives from Beetle C6) |
| UART TX pin | GPIO11 (unused — ESP32-C5 never sends to C6) |

**Critical:** Single-core chip — use `xTaskCreate()` NEVER `xTaskCreatePinnedToCore()`.

### 4.3 Beetle ESP32-C6 (Scanner Board)

| Property | Value |
|---|---|
| SoC | ESP32-C6, single-core RISC-V 160MHz |
| SKU | DFR1117 (DFRobot) |
| Role | Passive Wi-Fi RSSI scanning only |
| Wi-Fi | 2.4GHz only — used for scanning only, never connects |
| Board selection | ESP32C6 Dev Module |
| USB CDC On Boot | Enabled |
| UART TX pin | GPIO16 (sends scan results to ESP32-C5) |
| UART RX pin | GPIO17 (unused) |

**Key design decision:** Beetle C6 does NOT connect to any Wi-Fi network. `WiFi.mode(WIFI_STA)` + `WiFi.disconnect()` enables the radio for passive scanning without association. This means:

- No credentials stored on scanner board
- Scans work in any venue without reconfiguration
- No reconnection logic needed
- Full beacon frames received from all APs regardless of security type

### 4.4 UART Link (Beetle C6 → ESP32-C5)

| Property | Value |
|---|---|
| Direction | One-way: Beetle C6 → ESP32-C5 only |
| Baud rate | 115200 |
| Beetle TX | GPIO16 |
| ESP32-C5 RX | GPIO12 |
| Shared GND | Required — both boards must share GND |
| Voltage | 3.3V logic on both boards — no level shifter needed |
| Format | One newline-terminated JSON line per scan |
| UART peripheral | `Serial1` on ESP32-C5 (Serial2 does not exist on this chip) |

### 4.5 IMU — MPU6050

| Property | Value |
|---|---|
| Interface | I²C 400kHz, address 0x68 |
| Pins | SDA=GPIO23, SCL=GPIO24 on XIAO ESP32-C5 |
| Sample rate | 100Hz via `vTaskDelayUntil` |
| Accel range | ±4g, `ACCEL_CONFIG=0x08` |
| Gyro range | ±500°/s, `GYRO_CONFIG=0x08` |
| DLPF | 21Hz, `CONFIG=0x04` |

**Conversion constants (LOCKED — verified SDP1, never change):**

```
ax_SI = raw × 0.0011978149  [m/s²]
gz_SI = raw × 0.0002663309  [rad/s]
```

**Register config (LOCKED):**

| Register | Address | Value |
|---|---|---|
| PWR_MGMT_1 | 0x6B | 0x00 |
| GYRO_CONFIG | 0x1B | 0x08 |
| ACCEL_CONFIG | 0x1C | 0x08 |
| CONFIG | 0x1A | 0x04 |

### 4.6 Infrastructure Access Points

- QU Building H07 C Corridor: ~120 APs
- Role at runtime: RSSI anchors
- Role during setup: RTT ranging via Android tool to pin physical locations
- Beetle C6 collects: BSSID, SSID, RSSI, channel — full data per AP

---

## 5. Communication and Connectivity

### 5.1 Intra-Tag UART (Beetle C6 → ESP32-C5)

```
Format: {"wifi":[{"bssid":"AA:BB:CC:DD:EE:FF","ssid":"Name","rssi":-46,"ch":6},...]}
Terminator: \r\n (Serial.println on Beetle C6)
Interval: every 10s (one line per scan)
Max APs per line: 30
Max line length: ~2400 bytes (30 APs × ~80 bytes)
UART buffer on ESP32-C5: 3072 bytes
```

### 5.2 Tag → Server (ESP32-C5 → GCP)

```
Protocol: HTTPS POST
URL: https://35.238.189.188/api/v1/gateway/packet
Port: 443 (only open port in QU firewall)
Header: X-API-Key, Content-Type: application/json
Interval: 200ms (5 packets/sec)
TLS: self-signed cert, client.setInsecure()
Keepalive: http.setReuse(true)
Timeout: 3000ms
Typical size: ~490 bytes (IMU only), ~1000-1800 bytes (with WiFi scan)
```

**Wi-Fi credentials (ESP32-C5 only):**

- Dev/home: SSID=`Alhakim`, PASS=`sham@2014`
- QU deployment: SSID=`QU-User`, PASS=`""` (MAC-authenticated, no password)

### 5.3 Server → Parent App

```
Protocol: WSS (WebSocket over TLS, port 443)
Endpoint: wss://35.238.189.188/ws/position/{tag_id}
Rate: ≥4 Hz
Reconnect: exponential backoff on client
```

### 5.4 Server Infrastructure

| Property | Value |
|---|---|
| Provider | Google Cloud Platform |
| VM | e2-micro, static IP `35.238.189.188` |
| Domain | `trakn.duckdns.org` |
| Stack | Nginx → FastAPI (port 8000 internal) → PostgreSQL 16 |
| TLS | Self-signed, Nginx terminates on port 443 |

---

## 6. Firmware Requirements

### 6.1 Beetle ESP32-C6 — Scanner Firmware

**File:** `firmware/beetle_c6/beetle_c6_scanner.ino`

**Single responsibility:** scan and transmit. No HTTP, no TLS, no credentials.

```
setup():
  Serial.begin(115200)          — USB debug
  Serial1.begin(115200, SERIAL_8N1, GPIO17, GPIO16)  — UART TX on GPIO16
  WiFi.mode(WIFI_STA)           — enable radio
  WiFi.disconnect()             — ensure not associated
  delay(100)

loop():
  n = WiFi.scanNetworks()       — blocking, fine (no TCP stack)
  build JSON line               — bssid, ssid, rssi, ch per AP
  Serial1.println(json)         — send to ESP32-C5
  WiFi.scanDelete()             — free scan memory
  delay(10000)                  — wait 10s before next scan
```

**Scan API used (ESP-IDF / Arduino ESP32):**

- `WiFi.BSSIDstr(i)` → `String` "AA:BB:CC:DD:EE:FF"
- `WiFi.SSID(i)` → `String`
- `WiFi.RSSI(i)` → `int32_t` dBm
- `WiFi.channel(i)` → `int32_t`

### 6.2 XIAO ESP32-C5 — Main Firmware

**File:** `firmware/esp32c5/trakn_tag.ino`

**Four FreeRTOS tasks (xTaskCreate only — single-core chip):**

| Task | Priority | Stack | Responsibility |
|---|---|---|---|
| `imu_task` | 5 | 8192 | MPU6050 at 100Hz, fills ring buffer |
| `uart_task` | 3 | 8192 | Reads JSON lines from Beetle C6 via Serial1 |
| `wifi_task` | 3 | 8192 | Maintains Wi-Fi station connection |
| `post_task` | 2 | 16384 | Drains 5 IMU samples, POSTs JSON every 200ms |

**Key sizing:**

```cpp
#define MAX_APS          30
#define IMU_BATCH_SIZE    5    // ring buffer
#define IMU_DRAIN_SIZE    5    // drained per POST
#define POST_INTERVAL_MS  200  // 5 packets/sec
#define UART_RX_PIN       12   // GPIO12
#define UART_TX_PIN       11   // GPIO11 (unused)
#define UART_BAUD         115200
#define UART_BUF_SIZE     3072  // handles max JSON line from C6
```

**UART parsing strategy:** plain C `strstr`/`atoi` — no JSON library. Searches for `"bssid":"` blocks, extracts 17-char BSSID, then finds `ssid`, `rssi`, `ch` fields in order. Handles `\r\n` line termination from `Serial.println()`.

**JSON packet sent to server:**

```json
{
  "mac":  "24:42:E3:15:E5:72",
  "ts":   12450,
  "imu":  [{"ts":12340,"ax":0.034,"ay":-0.012,"az":9.812,
             "gx":0.0002,"gy":-0.0001,"gz":0.0003}],
  "wifi": [{"bssid":"92:3B:AD:A6:E5:B8","ssid":"Alhakim","rssi":-46,"ch":9}]
}
```

- `imu[]`: 0–5 samples per packet
- `wifi[]`: populated once per scan (~10s), empty `[]` between scans
- `mac`: ESP32-C5 MAC, hardcoded, used as device identifier

**QU deployment change:**

```cpp
// Home dev:
#define WIFI_SSID "Alhakim"
#define WIFI_PASS "sham@2014"
// QU deployment:
#define WIFI_SSID "QU-User"
#define WIFI_PASS ""
```

### 6.3 Confirmed Working State (March 2026)

```
Beetle C6 Serial Monitor:
  [C6] TRAKN scanner starting...
  [C6] radio ready, scanning...
  [C6] 11 APs found
  [C6] sent 645 bytes to ESP32-C5

ESP32-C5 Serial Monitor:
  [TRAKN] starting (ESP32-C5 + Beetle C6)...
  [IMU] ready
  [UART] listening on GPIO11
  [WIFI] connected, IP: 192.168.x.x
  [POST] task started
  [UART] 11 APs from Beetle C6
  [POST] 200 — 490 bytes, wifi=no, buf=5
  [POST] 200 — 1263 bytes, wifi=yes, buf=5
  [POST] 200 — 490 bytes, wifi=no, buf=5
```

---

## 7. Backend Server Requirements

### 7.1 Framework and Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Framework | FastAPI (async) |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 async |
| DB driver | asyncpg |
| Container | Docker + Docker Compose |
| TLS | Nginx reverse proxy |
| Math | NumPy, SciPy |

### 7.2 API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/gateway/packet` | API Key | Receive JSON from ESP32-C5 tag |
| `GET` | `/health` | None | Health check |
| `POST` | `/api/v1/auth/register` | None | Parent account creation |
| `POST` | `/api/v1/auth/login` | None | Returns JWT |
| `POST` | `/api/v1/devices/link` | JWT | Link tag ID to parent |
| `GET` | `/api/v1/devices/{tag_id}/position` | JWT | Latest position |
| `WSS` | `/ws/position/{tag_id}` | JWT | Real-time position stream |
| `POST` | `/api/v1/venue/floor-plan` | Admin | Upload floor plan |
| `POST` | `/api/v1/venue/grid-points` | Admin | Upload 0.5m grid |
| `POST` | `/api/v1/venue/ap` | Admin | Register AP location |
| `GET` | `/api/v1/venue/radio-map` | JWT | Pre-computed radio map |

### 7.3 Gateway Processing Pipeline

```
POST /api/v1/gateway/packet
        │
        ▼
Validate X-API-Key
        │
        ▼
Parse JSON: mac, ts, imu[], wifi[]
        │
        ▼
Get or create DeviceState for mac (in-memory)
        │
        ▼
For each sample in imu[]:
  → PDR engine: EMA filter, bias cal, heading, step detection, Weinberg stride
  → EKF predict step
        │
        ▼
If wifi[] non-empty:
  → Kalman smooth RSSI per AP
  → Log-distance → estimated distance per AP
  → Weighted trilateration + intersection scoring
  → EKF correction step
        │
        ▼
Broadcast position via WebSocket (async, non-blocking)
        │
        ▼
Persist to DB asynchronously (fire-and-forget)
        │
        ▼
Return {"status":"ok", "mac":"...", "imu_samples":N, "wifi_aps":M}
```

**Critical design principle:** PDR runs in-memory on the server using device timestamps (`ts` field). The 10s gap between RSSI scans is invisible to the PDR math because `dt = ts[i+1] - ts[i]` uses the device clock, not server arrival time.

---

## 8. Sensor Fusion Engine

### 8.1 PDR — Pedestrian Dead Reckoning

All parameters verified in SDP1 (88 steps, 64m loop, 3.75% error). Runs on backend server, not on device.

#### EMA Filter

```
α = 1 − exp(−2π × 3.2Hz × dt)
a_filt(t) = a_filt(t−1) + α × (a_mag(t) − a_filt(t−1))
gz_filt(t) = gz_filt(t−1) + α × (gz_corrected − gz_filt(t−1))
```

#### Gyro Bias Calibration

```
bias_gz = mean(gz_samples[:200])   # first 200 samples = 2s at 100Hz
gz_corrected = gz_raw − bias_gz
```

#### Heading Integration

```
heading(t) = heading(t−1) + gz_filt(t) × dt
```

#### Step Detection (all 5 conditions must be true)

```
(1) dt_since_last_step > 0.35s
(2) a_max > median(buf) + 2 × std(buf)
(3) a_max − a_min > 0.9 × std(buf)
(4) std(buf) > 1.2 m/s²
(5) |mean(buf) − 9.8| > 0.4 m/s²
```

#### Weinberg Stride (LOCKED)

```
L = 0.47 × (a_max − a_min)^0.25
L = clamp(L, 0.25m, 1.40m)
```

#### Position Update

```
X += L × cos(heading)
Y += L × sin(heading)
```

---

### 8.2 Wi-Fi RSSI Positioning

#### RSSI Kalman Smoother (per AP)

```
Q = 2.0 dBm²,  R = 9.0 dBm²
K = P / (P + R)
x̂ = x̂ + K × (z − x̂)
P = (1 − K) × P
```

Exclude APs with σ > 3.0 dBm over recent samples.

#### Log-Distance Path Loss

```
d = d_0 × 10^((RSSI_0 − RSSI_smoothed) / (10 × n))
d_0 = 1.0m,  n = 2.7 (default mixed indoor)
clamp(d, 0.5m, 100.0m)
```

#### Radio Map (Pre-computed at setup)

```
For each AP_i at (xi, yi), each grid point_j at (xj, yj):
  d_ij = sqrt((xj−xi)² + (yj−yi)²)
  RSSI_est_ij = RSSI_0_i − 10 × n_i × log10(d_ij)
```

Stored in `radio_map` table. Queried at runtime.

#### Weighted Trilateration

```
Minimize: Σ_i  w_i × ((X−xi)² + (Y−yi)² − d_i²)²
w_i = 1 / d_i²
```

#### Intersection Point Scoring

```
Score_j = Σ_i  w_i × exp(−(d_measured_ij − d_estimated_ij)² / (2 × 3.0²))
Best position = grid point j* with max Score_j
```

---

### 8.3 EKF Sensor Fusion

**State:** `x = [X, Y, heading, vx, vy]ᵀ`

**Process noise:** `Q = diag([0.01, 0.01, 0.005, 0.1, 0.1])`

**Measurement noise:**

```
R_normal = diag([4.0, 4.0])    — good RSSI conditions
R_noisy  = diag([9.0, 9.0])    — σ(RSSI) > 5 dBm
```

**Confidence:** `confidence = 1 / (1 + trace(P[0:2, 0:2]))`

---

## 9. Web Mapping Tool

Browser-based single-page app for venue setup. Not visible to parents.

**Features:**

1. Floor plan upload (PNG/SVG/PDF), scale setting by clicking two points
2. Wall and obstacle drawing — stored as line segments
3. 0.5m × 0.5m walkable grid generation
4. AP import and RSSI heatmap visualisation
5. Radio map computation trigger and verification display
6. Path loss exponent fitting from CSV walk data

**Tech:** Vanilla HTML + JavaScript + Canvas API. Single `index.html`, no build toolchain.

---

## 10. Android AP Localization Tool

Used once per venue to pin AP physical locations. Uses one-sided RTT for distance estimation during pinning — **RTT used during setup only, not at runtime.**

**Features:**

- Tab 1: AP discovery with live RTT distance
- Tab 2: Floor plan map, walk toward AP, tap to pin location
- Saves `{bssid, ssid, rssi_at_1m, n, x, y}` to backend

**Tech:** Kotlin, Android 12+, WifiRttManager API, Retrofit 2.

---

## 11. Mobile Parent Application

**Tag linking:** Parent enters tag ID (e.g. `TRAKN-0042`) printed on device — no QR scanning.

**Tech:** Flutter, `web_socket_channel`, `flutter_map`, `dio`, JWT auth.

**Map screen:** Clean floor plan, animated child marker, position updates ≥4Hz via WebSocket, confidence indicator, mode indicator (`normal` / `imu_only` / `disconnected`).

---

## 12. Calibration System

**Per-AP RSSI reference:** Android tool captures RSSI at ~1m from each AP. Minimum 30 measurements, σ < 5 dBm required.

**Path loss exponent:** Web Mapping Tool fits `n` per AP from `{distance_m, rssi_dBm}` walk data. Default fallback: `n = 2.7`.

**Radio map:** Recomputed automatically after any AP position update.

---

## 13. Performance Requirements

| Metric | Target | Minimum |
|---|---|---|
| IMU sampling rate | 100 Hz | 50 Hz |
| RSSI scan interval | 10s | 20s max |
| POST rate | 5 packets/sec | 2 packets/sec |
| WebSocket update rate | ≥4 Hz | ≥2 Hz |
| End-to-end latency | ≤200ms | ≤500ms |
| PDR error (64m loop) | ≤5% | ≤10% |
| RSSI positioning error (≥3 APs) | ≤4m CEP | ≤6m CEP |
| Fused positioning error | ≤3m CEP | ≤5m CEP |
| Tag battery life (1000mAh) | 8 hours | 4 hours |

---

## 14. Failure Modes and Recovery

| Mode | Trigger | EKF | App Indicator |
|---|---|---|---|
| `normal` | ≥2 APs in scan, IMU active | predict + update R_normal | Green |
| `imu_only` | 0 APs or no scan yet | predict only | Yellow |
| `disconnected` | No data >5s | suspended | Red |

**Additional recovery:**

- UART line overflow (>3072 bytes): discard and reset buffer, log event
- WiFi scan returns 0 APs: retry after 10s, no UART transmission
- POST failure on ESP32-C5: retry once after 500ms, continue IMU collection
- Wi-Fi disconnect on ESP32-C5: WiFi.reconnect() every 3s, IMU continues unaffected
- WebSocket drop on app: exponential backoff reconnect (1s, 2s, 4s, max 30s)

---

## 15. Database Schema

### `devices`

```sql
tag_id        VARCHAR(20) PRIMARY KEY    -- "TRAKN-0042", printed on device
mac_address   VARCHAR(17) UNIQUE NOT NULL -- ESP32-C5 MAC
label         VARCHAR(100)
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
is_active     BOOLEAN NOT NULL DEFAULT TRUE
```

### `device_links`

```sql
link_id         UUID PRIMARY KEY DEFAULT gen_random_uuid()
tag_id          VARCHAR(20) NOT NULL REFERENCES devices(tag_id)
parent_user_id  UUID NOT NULL REFERENCES users(user_id)
child_name      VARCHAR(100) NOT NULL
linked_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `users`

```sql
user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid()
email         VARCHAR(255) UNIQUE NOT NULL
password_hash VARCHAR(255) NOT NULL
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `venues`

```sql
venue_id      UUID PRIMARY KEY DEFAULT gen_random_uuid()
name          VARCHAR(255) NOT NULL
floor_plan_url TEXT
px_per_meter  FLOAT NOT NULL DEFAULT 1.0
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `grid_points`

```sql
grid_point_id UUID PRIMARY KEY DEFAULT gen_random_uuid()
venue_id      UUID REFERENCES venues(venue_id)
x             FLOAT NOT NULL
y             FLOAT NOT NULL
is_walkable   BOOLEAN NOT NULL DEFAULT TRUE
```

### `access_points`

```sql
bssid         VARCHAR(17) PRIMARY KEY
venue_id      UUID REFERENCES venues(venue_id)
ssid          VARCHAR(255)
x             FLOAT NOT NULL
y             FLOAT NOT NULL
rssi_ref      FLOAT NOT NULL    -- RSSI_0 at 1m
path_loss_n   FLOAT NOT NULL DEFAULT 2.7
updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `radio_map`

```sql
bssid         VARCHAR(17) REFERENCES access_points(bssid)
grid_point_id UUID REFERENCES grid_points(grid_point_id)
estimated_rssi FLOAT NOT NULL
estimated_dist FLOAT NOT NULL
PRIMARY KEY (bssid, grid_point_id)
```

### `positions`

```sql
pos_id        BIGSERIAL PRIMARY KEY
tag_id        VARCHAR(20) REFERENCES devices(tag_id)
x             FLOAT NOT NULL
y             FLOAT NOT NULL
heading       FLOAT NOT NULL DEFAULT 0.0
step_count    INTEGER NOT NULL DEFAULT 0
confidence    FLOAT NOT NULL DEFAULT 0.0
source        VARCHAR(20) NOT NULL   -- "fused"|"pdr_only"|"rssi_only"
ts            TIMESTAMPTZ NOT NULL DEFAULT now()
```

---

## 16. API Contracts

### 16.1 Gateway Packet (ESP32-C5 → Server)

```
POST /api/v1/gateway/packet
X-API-Key: 580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990
Content-Type: application/json
```

**Request:**

```json
{
  "mac":  "24:42:E3:15:E5:72",
  "ts":   12450,
  "imu":  [{"ts":12340,"ax":0.034,"ay":-0.012,"az":9.812,
             "gx":0.0002,"gy":-0.0001,"gz":0.0003}],
  "wifi": [{"bssid":"92:3B:AD:A6:E5:B8","ssid":"Alhakim","rssi":-46,"ch":9}]
}
```

**Response 200:**

```json
{
  "status": "ok",
  "mac": "24:42:E3:15:E5:72",
  "imu_samples": 5,
  "wifi_aps": 11
}
```

### 16.2 WebSocket Position (Server → App)

```json
{
  "tag_id":     "TRAKN-0042",
  "x":          12.4,
  "y":          7.8,
  "heading":    1.57,
  "step_count": 143,
  "confidence": 0.87,
  "source":     "fused",
  "mode":       "normal",
  "ts":         "2026-03-26T23:04:05.784Z"
}
```

---

## 17. Infrastructure and Deployment

### 17.1 Docker Stack

```
Nginx (443) → FastAPI (8000 internal) → PostgreSQL 16
```

### 17.2 Environment Variables

```
DATABASE_URL=postgresql+asyncpg://admin:changeme@db:5432/localization
JWT_SECRET=<64-char hex>
GATEWAY_API_KEY=580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990
ALLOWED_ORIGINS=https://35.238.189.188,https://trakn.duckdns.org
```

### 17.3 Deploy Workflow

```bash
cd ~/trakn && git pull
cp -r backend/app ~/child-localization/backend/
cd ~/child-localization && docker compose up -d --build backend
docker logs -f child-localization-backend-1 --tail 20
```

### 17.4 QU IT Registration

- MAC: `24:42:E3:15:E5:72` (ESP32-C5 only — Beetle C6 never connects)
- Network: `QU-User`
- Status: **Confirmed — QU IT, contact Ajay, 4 March 2026**

---

## 18. Testing Requirements

### 18.1 Firmware Tests

```
✅ Beetle C6: scan returns APs, JSON sent over UART
✅ ESP32-C5: UART received, parsed, wifi=yes in POST log
✅ ESP32-C5: POST 200 confirmed from server
✅ Packet size: ~490 bytes IMU-only, ~1000–1800 bytes with WiFi
✅ No TLS timeouts (confirmed March 2026)
```

### 18.2 Backend Tests (pending)

```
□ POST /health returns 200
□ POST /gateway/packet with IMU-only returns 200
□ POST /gateway/packet with WiFi returns 200
□ PDR step count matches manual count (±2 steps over 88)
□ Position updates appear on WebSocket within 200ms
```

### 18.3 Accuracy Benchmarks

| Test | Pass Criterion |
|---|---|
| 88-step rectangular loop, PDR only | Distance error ≤5% |
| Static position, ≥3 APs visible | RSSI error ≤4m |
| Walking, fusion active, ≥3 APs | 95th percentile ≤5m |

---

## 19. Implementation Plan

| ID | Title | Status |
|---|---|---|
| TASK-01 | Project structure and Docker setup | ✅ Done |
| TASK-02 | Gateway endpoint — receive + log packets | ✅ Done (Milestone 1) |
| TASK-03 | PDR engine — in-memory, per-device state | ✅ Done (Milestone 2) |
| TASK-04 | RSSI Kalman filter + log-distance model | 🔲 Pending |
| TASK-05 | Weighted trilateration + intersection scoring | 🔲 Pending |
| TASK-06 | EKF sensor fusion | 🔲 Pending |
| TASK-07 | WebSocket position broadcaster | 🔲 Pending |
| TASK-08 | Database persistence (async, non-blocking) | 🔲 Pending |
| TASK-09 | Web Mapping Tool | 🔲 Pending |
| TASK-10 | Android AP Localization Tool | 🔲 Pending |
| TASK-11 | Flutter parent app — auth + tag linking | 🔲 Pending |
| TASK-12 | Flutter parent app — live map screen | 🔲 Pending |
| TASK-13 | Integration test — full pipeline walk | 🔲 Pending |
| TASK-14 | Walk accuracy benchmark | 🔲 Pending |

---

## 20. Open Questions

| ID | Question | Impact |
|---|---|---|
| OQ-01 | AP physical coordinates in H07-C — manual survey required | High |
| OQ-02 | Path loss exponent n for H07-C — needs on-site measurement | Medium |
| OQ-03 | QU AP channel bandwidth (20/40/80 MHz)? | Low |
| OQ-04 | Which QU APs are in DFS 5GHz band? | Low |

---

## 21. Glossary

| Term | Definition |
|---|---|
| Beetle C6 | DFRobot Beetle ESP32-C6 (DFR1117) — scanner board in two-board tag |
| BSSID | MAC address of a specific AP radio — unique per physical AP |
| DLPF | Digital Low-Pass Filter — MPU6050, configured 21Hz |
| EKF | Extended Kalman Filter — fuses PDR and RSSI |
| ESP32-C5 | XIAO ESP32-C5 — main board, handles IMU + HTTP POST |
| IMU | Inertial Measurement Unit — MPU6050 accel + gyro |
| MPU6050 | InvenSense 6-DOF IMU, I²C 0x68 |
| PDR | Pedestrian Dead Reckoning — position from steps + heading |
| Radio Map | Pre-computed RSSI estimates from each AP to each grid point |
| RSSI | Received Signal Strength Indicator — used for distance estimation |
| RTT | Round-Trip Time — used during setup only to pin AP locations |
| Tag ID | Alphanumeric code on device (e.g. TRAKN-0042) entered by parent |
| UART | Universal Asynchronous Receiver-Transmitter — Beetle C6 → ESP32-C5 link |
| QU | Qatar University |
| GCP | Google Cloud Platform |
