# Product Requirements Document

## Child Indoor Localization System

### Qatar University — Building H07, C Corridor

**Version:** 4.0
**Date:** March 2026
**Status:** Active — Senior Design Project
**Team:** 4 members
**Change from v3.0:** Simplified to direct Wi-Fi connectivity. GSM and BLE gateway paths removed. Tag connects directly to venue Wi-Fi and POSTs over HTTPS to server on port 443.

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
9. [Mobile Application Requirements](#9-mobile-application-requirements)
10. [Calibration System](#10-calibration-system)
11. [Performance Requirements](#11-performance-requirements)
12. [Failure Modes and Recovery](#12-failure-modes-and-recovery)
13. [Database Schema](#13-database-schema)
14. [API Contracts](#14-api-contracts)
15. [BLE Packet Protocol](#15-ble-packet-protocol)
16. [Infrastructure and Deployment](#16-infrastructure-and-deployment)
17. [Testing Requirements](#17-testing-requirements)
18. [Implementation Plan](#18-implementation-plan)
19. [Open Questions](#19-open-questions)
20. [Glossary](#20-glossary)

---

## 1. Project Overview

This project implements a real-time indoor child localization system for deployment in Qatar University Building H07, C Corridor. A child wearing a BW16 wearable device is tracked continuously. Parents receive live position updates on a Flutter mobile application.

The system fuses one-sided Wi-Fi RTT ranging with IMU-based pedestrian dead reckoning (PDR) through an Extended Kalman Filter (EKF) to achieve sub-4-meter positioning accuracy in a GPS-denied indoor environment.

The device connects directly to venue Wi-Fi and transmits data to the cloud server over HTTPS. No BLE gateway, no GSM module, and no additional infrastructure is required beyond the existing venue Wi-Fi network. The venue IT team registers the device MAC address once, and the device connects automatically on every subsequent power-on.

**Deployment model:** The tag is a venue-managed asset — registered to the venue Wi-Fi by IT staff, rented to parents at the venue entrance (like a stroller or locker key), and returned at exit. The parent links their app to a specific tag by scanning a QR code printed on the device.

**Core user story:** A parent scans the QR code on the tag, opens the app, and sees their child's current position on a floor plan of the corridor, updated at least 4 times per second, with a confidence indicator that degrades gracefully when signal quality drops.

---

## 2. Problem Statement

GPS does not penetrate indoor environments with sufficient accuracy. Fingerprint-based Wi-Fi localization requires expensive site surveys that become stale as infrastructure changes. Camera-based tracking raises unacceptable privacy concerns in a university setting.

One-sided Wi-Fi RTT ranging against existing infrastructure access points, fused with IMU-based step detection and heading estimation, provides a practical and privacy-preserving alternative. The QU H07 corridor has known AP infrastructure (~120 APs across all floors of Corridor C) that serves as ranging anchors. The device connects directly to venue Wi-Fi and transmits data to the cloud server — no additional infrastructure required.

**Constraints specific to this deployment:**

- QU access points do not support IEEE 802.11-2016 cooperative two-sided FTM ranging.
- The BW16 connects to QU Wi-Fi using a registered MAC address (24:42:E3:15:E5:72) — confirmed by QU IT on 4 March 2026.
- The university network cannot be relied upon as the server hosting environment — a GCP cloud VM is used instead.
- Corridor geometry imposes non-line-of-sight (NLOS) RTT bias at longer distances.
- AP physical coordinates not available from IT — manual survey required (OQ-03).

---

## 3. System Architecture

```
┌─────────────────────────┐   HTTPS POST (port 443)   ┌─────────────────────────┐
│  BW16 + MPU6050 (child) │ ────────────────────────► │  Cloud Server           │
│                         │   venue Wi-Fi direct       │  35.238.189.188         │
│  ● IMU @ 100 Hz         │   JSON + base64 payload    │  FastAPI + Postgres      │
│  ● RTT @ ≥2 Hz          │                            │  Nginx (TLS port 443)   │
│  ● Wi-Fi: QU-User       │                            │  EKF + Bayesian fusion  │
│    MAC: 24:42:E3:15:E5:72│                           └────────────┬────────────┘
└─────────────────────────┘                                         │ WSS (port 443)
                                                         ┌──────────▼──────────┐
                                                         │  Flutter Parent App  │
                                                         │  (live map + alerts) │
                                                         └─────────────────────┘
```

**Data flow:**

1. Venue IT registers device MAC address `24:42:E3:15:E5:72` to QU-User Wi-Fi once
2. BW16 powers on → connects to QU-User Wi-Fi automatically
3. BW16 samples IMU at 100 Hz and performs RTT ranging at ≥2 Hz against visible APs
4. BW16 packs readings into JSON with base64-encoded payload and POSTs to server over HTTPS port 443
5. Server authenticates API key, parses packet, runs EKF + Bayesian fusion, publishes position via WebSocket
6. Parent app (subscribed via WSS) renders live position on floor plan at ≥4 Hz

**Parent onboarding flow:**

1. Parent receives/rents the tag at venue entrance
2. Parent opens Flutter app → taps "Add Device"
3. Parent scans QR code printed on the tag (encodes device MAC / device ID)
4. App registers parent account as linked to that device ID on the server
5. App immediately begins receiving live position updates via WebSocket

**Server hosting:** Google Cloud e2-micro VM, static IP 35.238.189.188, Premium network tier. Nginx terminates TLS on port 443 and proxies to FastAPI on port 8000 internally. Port 443 is open inbound in QU firewall by default — no special firewall request required.

---

## 4. Hardware Components

### 4.1 BW16 Embedded Device

- **Manufacturer:** Realtek (RTL8720DN dual-band Wi-Fi + BLE 5.0)
- **Role:** Wearable sensor node worn by the child
- **Capabilities used:** IMU sampling, Wi-Fi RTT ranging (one-sided FTM), Wi-Fi station (direct network connection), BLE advertisement
- **Wi-Fi MAC address:** `24:42:E3:15:E5:72` (hardware MAC — permanent, registered with QU IT)
- **Network:** Connects to QU-User Wi-Fi; POSTs data to server over HTTPS port 443
- **Power:** Battery-powered, must sustain a full day of operation
- **Mounting:** Wrist or lanyard enclosure

### 4.2 IMU Sensor — MPU6050

- **Model:** InvenSense MPU6050 (verified in Senior Design 1 PDR prototype)
- **Interface:** I2C at 400 kHz (fast mode), I2C address 0x68, connected to BW16
- **Axes:** 6-DOF — 3-axis accelerometer + 3-axis gyroscope
- **Sampling rate:** 100 Hz (10 ms loop period)
- **Accelerometer range:** ±4g — register `ACCEL_CONFIG = 0x08` → sensitivity 8192 LSB/g
- **Gyroscope range:** ±500°/s — register `GYRO_CONFIG = 0x08` → sensitivity 65.5 LSB/(°/s)
- **Low-pass filter:** 21 Hz DLPF — register `CONFIG = 0x04` — reduces vibration noise
- **Raw-to-SI conversion (locked — verified values):**
  - Accelerometer: `raw × 0.0011978149` m/s² (= raw × 9.81 / 8192)
  - Gyroscope: `raw × 0.0002663309` rad/s (= raw × π / (180 × 65.5))
- **Outputs:** ax, ay, az (m/s²); gx, gy, gz (rad/s)
- **No magnetometer:** MPU6050 has no mag sensor; MagX/Y/Z fields are zero placeholders

### 4.3 Infrastructure Access Points

- QU Building H07, C Corridor existing Wi-Fi infrastructure
- **Confirmed by IT (4 March 2026):** approximately 120 APs across all floors of Corridor C, male and female sides
- Role: both Wi-Fi connectivity for the device and RTT ranging anchors
- Band: 20 MHz bandwidth confirmed; 40/80 MHz TBD (see OQ-04)
- Physical coordinates: not available from IT — manual survey required (see OQ-03)
- BSSIDs: discoverable by Wi-Fi scan from the device during operation

---

## 5. Communication and Connectivity

### 5.1 Direct Wi-Fi Architecture

The BW16 connects directly to the venue Wi-Fi network as a standard Wi-Fi station and POSTs data to the cloud server over HTTPS. No BLE gateway, no GSM module, no intermediary hardware.

```
BW16 (Wi-Fi station) → venue Wi-Fi → internet → HTTPS POST → server:443
```

### 5.2 Device → Server (Direct Wi-Fi POST)

- **Protocol:** HTTPS POST over venue Wi-Fi
- **Endpoint:** `POST https://trakn.duckdns.org/api/v1/gateway/packet`
- **Port:** 443 (standard HTTPS — enabled by default in QU firewall)
- **Header:** `X-API-Key: <gateway_api_key>` (baked into firmware)
- **Body:** JSON with `device_mac`, `rx_ts_utc`, `payload_b64` (see Section 14)
- **Packet types:** IMU (0x01) and RTT (0x02)
- **Upload cadence:** Batch 25 IMU samples (250 ms at 100 Hz), POST every 250 ms. RTT packets POST immediately on ranging cycle completion (≥2 Hz)
- **On POST failure:** retry once with 500 ms delay; buffer locally up to 30 s; flush with original timestamps on reconnect
- **Wi-Fi credentials:** SSID `QU-User`, MAC `24:42:E3:15:E5:72` registered by IT — device connects automatically on power-on

### 5.3 Server → App (WebSocket)

- Protocol: WSS (WebSocket over TLS, port 443)
- Push model: server publishes position updates at ≥4 Hz
- App subscribes on session open; reconnects automatically on drop
- Endpoint: `wss://trakn.duckdns.org/ws/position/{device_id}`

### 5.4 Server Hosting

- Provider: Google Cloud Platform — e2-micro VM, Premium network tier
- Static IP: **35.238.189.188**
- TLS termination: Nginx on port 443 → FastAPI on port 8000 (internal only — not publicly exposed)
- TLS certificate: Let's Encrypt via nip.io domain or self-signed
- Firewall: TCP 443 open inbound (standard — no special request needed)
- Port 8000 NOT exposed publicly — internal only

---

## 6. Firmware Requirements

### 6.1 IMU Sampling — BW16 + MPU6050

**Hardware setup:**

- MPU6050 connected to BW16 via I2C at 400 kHz
- I2C address: 0x68 (AD0 pin low)
- Wake MPU6050 on startup: write 0x00 to PWR_MGMT_1 (0x6B)
- Apply configuration in order: GYRO_CONFIG, ACCEL_CONFIG, CONFIG (DLPF)
- Verify sensor presence: check `Wire.endTransmission()` == 0 on wake; halt with error BLE packet if not found

**Register configuration (locked — do not change):**

| Register | Address | Value | Setting |
|---|---|---|---|
| PWR_MGMT_1 | 0x6B | 0x00 | Wake up, internal 8MHz oscillator |
| GYRO_CONFIG | 0x1B | 0x08 | ±500°/s range |
| ACCEL_CONFIG | 0x1C | 0x08 | ±4g range |
| CONFIG | 0x1A | 0x04 | 21 Hz DLPF bandwidth |

**Sampling loop:**

- Read all 14 bytes starting at ACCEL_XOUT_H (0x3B) in a single I2C transaction
- Byte order: ax_H, ax_L, ay_H, ay_L, az_H, az_L, temp_H, temp_L, gx_H, gx_L, gy_H, gy_L, gz_H, gz_L
- Discard temperature bytes (bytes 6–7)
- Combine high/low bytes: `raw = (high_byte << 8) | low_byte` as signed int16
- Apply conversion: accel × 0.0011978149 m/s², gyro × 0.0002663309 rad/s
- Loop period: 10 ms (100 Hz)
- Pack into IMU BLE packet (Type 0x01, Section 15) with MCU timestamp and sequence number

### 6.2 One-Sided RTT Ranging

- Use Realtek BW16 SDK one-sided FTM API (OQ-01: confirm API availability)
- Ranging cycle rate: ≥2 Hz
- Per cycle: range against all visible APs, up to 10 (Android 12 API limit applies to receiver side; BW16 initiator limit TBD)
- Use time-last-seen as the AP selection strategy when more than 10 APs are visible
- Record per-AP: mean distance (m), standard deviation (m), RSSI (dBm), band (2.4/5 GHz)
- Pack into RTT BLE packet (Type 0x02, see Section 15)

### 6.3 Wi-Fi Transmission (Direct — Primary and Only Path)

- On startup: connect to SSID `QU-User` using stored credentials (MAC `24:42:E3:15:E5:72`)
- Wait for `WL_CONNECTED` before beginning transmission (timeout 15 s; retry every 30 s on failure)
- **IMU packets:** batch 25 samples (250 ms), encode as base64, POST to `https://trakn.duckdns.org/api/v1/gateway/packet` every 250 ms
- **RTT packets:** POST immediately when ranging cycle completes (≥2 Hz)
- Header: `X-API-Key: <baked-in key>`, `Content-Type: application/json`
- Body format: direct device POST (Section 14.2)
- On POST failure: retry once after 500 ms; buffer locally up to 30 s; flush on reconnect with original timestamps
- On Wi-Fi disconnect: attempt reconnect every 5 s; buffer data locally during outage

---

## 7. Backend Server Requirements

### 7.1 Framework and Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI (async)
- **Database driver:** asyncpg
- **ORM:** SQLAlchemy 2.0 (async session)
- **Database:** PostgreSQL 16
- **Containerization:** Docker + Docker Compose
- **TLS termination:** Nginx reverse proxy or direct Certbot

### 7.2 API Modules

| Module | File | Responsibility |
|---|---|---|
| Gateway | `backend/app/api/gateway.py` | Receive packets from device direct Wi-Fi POST |
| Parent | `backend/app/api/parent.py` | REST endpoints for parent app |
| WebSocket | `backend/app/api/websocket.py` | Real-time position push |
| Admin | `backend/app/api/admin.py` | Calibration data management |

### 7.3 Core Modules

| Module | File | Responsibility |
|---|---|---|
| Config | `backend/app/core/config.py` | Environment-based settings |
| Security | `backend/app/core/security.py` | JWT auth + gateway API key |
| Packet Parser | `backend/app/core/ble_parser.py` | Decode raw packet bytes from base64 payload |

### 7.4 Processing Pipeline (per incoming packet)

The gateway endpoint receives packets from the device via direct Wi-Fi POST.

```
HTTPS POST received  (device direct Wi-Fi)
      ↓
Authenticate API key (reject 401 if invalid)
      ↓
Decode base64 payload_b64
      ↓
Parse packet type byte
  → 0x01 IMU:  parse IMU fields
  → 0x02 RTT:  parse RTT fields
  → unknown:   return 400
      ↓
[If RTT]  Apply per-AP offset correction
      ↓
[If RTT]  Run Bayesian grid update
      ↓
EKF predict (IMU) or EKF predict+update (RTT)
      ↓
Determine operating mode based on RTT AP count:
  ≥2 APs → normal
  1 AP   → degraded
  0 APs  → imu_only
  No data >5 s → disconnected
      ↓
Persist to PostgreSQL
      ↓
Publish position via WebSocket
```

---

## 8. Sensor Fusion Engine

### 8.1 One-Sided RTT Observation Model

Based on Horn (2022), the observation model accounts for the systematic positive bias introduced by one-sided RTT when the AP cannot respond instantaneously.

**Mean function:**

```
μ(x) = x · [1 + A · α · (x − x₀) · exp(−α · (x − x₀))]
```

**Standard deviation function:**

```
σ(x) = σ₀ + σ_m · (x − x₀) · exp(−β · (x − x₀))
```

**Likelihood:**

```
p(y | x) = N(y; μ(x), σ(x)²)
```

**Verified parameters (do not modify without user confirmation):**

| Parameter | Value | Meaning |
|---|---|---|
| x₀ | 5.5 m | AP mounting height (minimum approach distance) |
| A | 2.23 | Amplitude of mean deviation |
| α | 0.043 m⁻¹ | Decay rate of mean deviation |
| σ₀ | 4.0 m | Baseline standard deviation |
| σ_m | 0.55 | Slope of std increase with distance |
| β | 0.015 m⁻¹ | Decay rate of std with distance |

### 8.2 RTT Offset Correction

```
d_corrected = d_raw − d_offset(AP_i, band)
clamp: if d_corrected < 0.5 m → return 0.5 m
```

Expected offset magnitude: 2400–2700 m (5 GHz), ~1500 m (2.4 GHz legacy). Actual values are per-AP and determined during calibration.

### 8.3 Bayesian Grid Localization

- Grid cell size: 0.5 m × 0.5 m (fixed — do not change)
- Grid covers walkable cells of H07 C Corridor floor plan
- Prior: initialized to uniform over walkable cells
- Update: for each AP measurement, multiply each cell's probability by p(y | dist(cell, AP))
- Normalize after each update
- MAP estimate: cell with maximum posterior probability
- Collapse recovery: if probability sum < 1e-10 → reset to uniform prior, log event

### 8.4 Extended Kalman Filter

**State vector:** `x = [p_x, p_y, v_x, v_y]ᵀ`

**Initial covariance:**

```
P₀ = diag([25, 25, 4, 4])
```

**Process noise:**

```
Q = diag([0.01, 0.01, 0.1, 0.1])
```

**Measurement noise:**

```
R_normal   = diag([9.0, 9.0])     (σ_wifi = 3.0 m, ≥2 APs active)
R_degraded = diag([18.0, 18.0])   (σ_wifi = 6.0 m, <2 APs active)
```

**Predict step (IMU-driven):**

```
x̂ = F·x + B·[ax, ay]ᵀ
P̂ = F·P·Fᵀ + Q

F = [[1, 0, dt, 0],     B = [[0.5·dt², 0      ],
     [0, 1, 0,  dt],         [0,       0.5·dt²],
     [0, 0, 1,  0 ],         [dt,      0      ],
     [0, 0, 0,  1 ]]         [0,       dt     ]]
```

**Update step (Bayesian MAP as measurement):**

```
H = [[1, 0, 0, 0],
     [0, 1, 0, 0]]

y = z − H·x̂          (innovation)
S = H·P̂·Hᵀ + R        (innovation covariance)
K = P̂·Hᵀ·S⁻¹         (Kalman gain)
x = x̂ + K·y
P = (I − K·H)·P̂
```

**Divergence reset:** If |pos_EKF − pos_Bayes| > 10 m for more than 5 consecutive cycles, reset EKF: x[:2] = pos_Bayes, x[2:] = 0, P = P₀.

### 8.5 PDR — Pedestrian Dead Reckoning

**Origin:** All algorithms and parameters in this section were verified and calibrated during Senior Design 1 using an Arduino Uno R4 Wi-Fi + MPU6050 with MATLAB. They are now migrated to Python and run on the backend server. The core logic is identical — only the language and execution environment change.

**Implementation file:** `backend/app/fusion/pdr.py`

#### 8.5.1 Signal Filtering

Exponential moving average applied to acceleration magnitude and gyroscope-z before step detection and heading integration.

```
α = 1 − exp(−2π · f_c · dt)     where f_c = 3.2 Hz
a_mag_f(t) = a_mag_f(t−1) + α · (a_mag(t) − a_mag_f(t−1))
gz_f(t)    = gz_f(t−1)    + α · (gz(t)    − gz_f(t−1))
```

#### 8.5.2 Gyroscope Bias Calibration

At device startup, the first 2 seconds of gyro-z readings are averaged to compute a static bias offset. This bias is subtracted from all subsequent gz readings before integration.

```
gyro_bias = mean(gz[0 : t < 2.0 s])
gz_corrected = gz − gyro_bias
```

Do not integrate heading during the calibration window.

#### 8.5.3 Heading Integration

```
θ(t) = θ(t−1) + gz_f_corrected(t) · dt
```

#### 8.5.4 Step Detection

Uses a rolling window of 0.40 s with adaptive peak and swing thresholds.

**Parameters (verified — do not change):**

| Parameter | Value | Meaning |
|---|---|---|
| `win_step` | 0.40 s | Rolling window duration for step detection |
| `min_step_dt` | 0.35 s | Minimum time between accepted steps (debounce) |
| `th_std_factor` | 2.0 | Peak threshold: median + 2 × std(window) |
| `th_swing_factor` | 0.9 | Swing threshold: 0.9 × std(window) |

**False-step suppression (both conditions must pass before checking for a step):**

- `std(window) >= 1.2` — reject if device appears stationary
- `|mean(window) − 9.8| >= 0.4 m/s²` — reject if acceleration is near-gravity flat

**Step validity (all three must be true):**

```
(t − last_step_t) > min_step_dt
AND  max(window) > median(window) + 2 · std(window)
AND  (max(window) − min(window)) > 0.9 · std(window)
```

#### 8.5.5 Stride Length Estimation

Two methods run in parallel. If a trained SVR model is available, they are blended 50/50. If no model is available, Weinberg is used alone.

**Weinberg model (always computed):**

```
L_wein = K_wein · (a_max − a_min)^p_wein

K_wein = 0.47      (calibrated for our setup — do not change)
p_wein = 0.25      (Weinberg exponent)
```

**Stride length clamps:**

```
min_stride = 0.25 m
max_stride = 1.40 m
SVR output is additionally clamped to [0.45, 0.90] m before blending
```

**Hybrid blend (when SVR model is loaded):**

```
stride = 0.5 · L_wein + 0.5 · L_svr
```

**Final stride:** `stride = clamp(blend_or_wein, min_stride, max_stride)`

#### 8.5.6 Log-Binned Histogram Features

On each detected step, compute a 20-bin normalized histogram of the acceleration magnitudes in the current window. These are the feature vector for the SVR model.

**Bin configuration (locked — verified parameters):**

| Parameter | Value |
|---|---|
| `amax` | 20.0 m/s² |
| `Kbin` | 0.117 |
| `Ml` | 10 (bins below gravity) |
| `Mh` | 10 (bins above gravity) |
| Total bins `M` | 20 |

**Bin edge construction:**

```python
# Bins below gravity (logarithmically spaced):
E[i] = 9.8 * (0.5 * Kbin) ** ((Ml + 1 - i) / Ml)   for i in 1..Ml

# Bins above gravity (linearly spaced):
E[i] = 9.8 + (amax - 9.8) * (i - Ml - 1) / Mh        for i in Ml+1..M

# E[0] = 0 always
```

**Feature normalization:** divide bin counts by total count → probability distribution (sums to 1.0).

#### 8.5.7 SVR Model Training and Storage

The SVR model is trained on labeled walk data (ground-truth distance → average stride label per step). It is persisted as `stride_svr.pkl` in `backend/app/fusion/`.

**Model spec:**

- Algorithm: `sklearn.svm.SVR` with RBF (Gaussian) kernel, `kernel_scale='auto'`, standardized features
- Input: 20-bin histogram feature vector (normalized)
- Output: stride length in meters
- Training label: `stride_true = D_true / N_steps` for each step in a labeled walk
- Retraining: append new walk data, retrain from scratch on combined dataset, overwrite `stride_svr.pkl`

**Training data schema (`stride_training_data.json`):**

```json
{ "X": [[...20 floats...], ...], "y": [0.62, 0.58, ...] }
```

#### 8.5.8 Position Update

On each accepted step:

```
X += stride · cos(θ)
Y += stride · sin(θ)
```

This 2D dead-reckoning position feeds into the EKF as the IMU-only position estimate when RTT is unavailable.

### 8.6 Fusion Coordinator

The coordinator is an async loop that:

1. Receives parsed IMU data → calls EKF predict
2. Receives parsed RTT data → runs offset correction → runs Bayesian update → calls EKF update with Bayesian MAP
3. Determines operating mode based on AP count and device activity
4. Calls `publish_position()` with the fused result

```python
# Locked interface — Person C calls this, Person D implements it
async def publish_position(
    device_id: str,
    position: tuple[float, float],   # (x_m, y_m)
    source: str,                      # "fused" | "wifi_only" | "imu_only"
    confidence: float,
    active_aps: int,
    mode: str                         # "normal" | "degraded" | "imu_only" | "disconnected"
) -> None: ...
```

---

## 9. Mobile Application Requirements

### 9.1 Platform

- **Framework:** Flutter
- **Primary target:** Android 12
- **Secondary target:** iOS (best-effort)

### 9.2 Features

- **Authentication:** Parent login via JWT (email + password)
- **Live map:** Floor plan of H07 C Corridor rendered as background image; child position shown as animated marker
- **Position updates:** Received via WebSocket, rendered at ≥4 Hz
- **Mode indicator:** Visual indicator showing current operating mode (normal / degraded / imu_only / disconnected)
- **Confidence indicator:** Numerical or visual confidence score from server
- **Reconnection:** Automatic WebSocket reconnect with exponential backoff on disconnect
- **Offline state:** Show last known position with "disconnected" label when WebSocket drops

### 9.3 File Structure

```
app/lib/
  screens/   live_map_screen.dart
  services/  websocket_service.dart, auth_service.dart
  models/    position_update.dart
```

---

## 10. Calibration System

### 10.1 Purpose

RTT measurements from one-sided FTM contain a systematic per-AP, per-band offset that must be measured and subtracted before applying the observation model. Offsets are on the order of 1500–2700 meters (this is a known quirk of one-sided RTT — the raw value includes processing time converted to distance units).

### 10.2 Calibration Procedure

1. Place the BW16 device at a known position relative to a target AP (x₀ = 5.5 m recommended)
2. Record at least 100 RTT measurements to that AP
3. Compute mean of raw measurements
4. offset = mean_raw − true_distance
5. Repeat for each AP and each band (2.4 GHz and 5 GHz separately)
6. Enter values via the admin API endpoint

### 10.3 Calibration Quality Gate

An AP calibration entry is flagged as unreliable and excluded from Bayesian updates if:

- Standard deviation of calibration measurements > 20 m
- Fewer than 30 measurements were collected

### 10.4 Admin Endpoints

- `POST /api/v1/admin/calibration` — submit calibration data for an AP
- `GET /api/v1/admin/calibration` — retrieve all calibration entries
- `GET /api/v1/admin/calibration/{bssid}` — retrieve calibration for specific AP
- `DELETE /api/v1/admin/calibration/{bssid}` — remove calibration entry

---

## 11. Performance Requirements

All requirements are mandatory. If an implementation cannot meet a target, report it explicitly — do not silently relax the requirement.

| Metric | Required Target | Minimum Acceptable |
|---|---|---|
| IMU sampling rate | ≥ 50 Hz | ≥ 25 Hz |
| RTT cycle rate | ≥ 2 Hz | ≥ 1 Hz |
| Position update rate (WebSocket) | ≥ 4 Hz | ≥ 2 Hz |
| Bayesian grid update time | ≤ 50 ms | ≤ 100 ms |
| EKF predict + update time | ≤ 7 ms | ≤ 15 ms |
| End-to-end latency (device → app) | ≤ 2.0 s | ≤ 2.5 s |
| Fused position RMS error | ≤ 2.5 m | ≤ 4.0 m |
| Wi-Fi-only RMS error | ≤ 4.0 m | ≤ 6.0 m |
| System uptime during demo | ≥ 99% | ≥ 95% |

---

## 12. Failure Modes and Recovery

### 12.1 Operating Modes

Operating mode is determined solely by how many APs returned RTT measurements in the most recent ranging cycle. Transport path (GSM or BLE) does not affect the mode — both paths deliver RTT data.

| Mode | Trigger Condition | EKF Behavior | WebSocket `mode` Value |
|---|---|---|---|
| `normal` | ≥ 2 APs responding, IMU active | predict + update with R_normal | `"normal"` |
| `degraded` | Exactly 1 AP responding | predict + update with R_degraded | `"degraded"` |
| `imu_only` | 0 APs responding (no RTT data) | predict only, no Bayesian update | `"imu_only"` |
| `disconnected` | No device data for > 5 s | All processing suspended | `"disconnected"` |

### 12.2 Special Recovery Cases

- **Bayesian grid collapse** (probability sum < 1e-10): reset prior to uniform over walkable cells, log event, continue without crashing.
- **EKF divergence** (|pos_EKF − pos_Bayes| > 10 m for > 5 cycles): reset EKF state to Bayesian MAP position, zero velocities, reset P to P₀.
- **ZUPT** (|a| < 0.05 m/s² for > 2 s): set v_x = v_y = 0 in EKF state.
- **AP drops out mid-session**: remove from active AP list, recalculate mode, continue.
- **Wi-Fi POST failure**: device buffers locally up to 30 s; flushes with original timestamps on reconnect; server processes in timestamp order.
- **Wi-Fi disconnect**: device retries connection every 5 s; buffers data during outage; resumes transmission on reconnect.
- **WebSocket client disconnects**: server buffers last position; client reconnects and receives latest state immediately.

---

## 13. Database Schema

Seven tables. Schema defined in `backend/app/db/models.py`. Do not add columns or change types without creating a migration.

### `devices`

```sql
device_id    UUID PRIMARY KEY DEFAULT gen_random_uuid()
mac_address  VARCHAR(17) UNIQUE NOT NULL        -- "AA:BB:CC:DD:EE:FF"
label        VARCHAR(100)                       -- human-readable name
created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
is_active    BOOLEAN NOT NULL DEFAULT TRUE
```

### `device_links`

```sql
link_id      UUID PRIMARY KEY DEFAULT gen_random_uuid()
device_id    UUID NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE
parent_user_id UUID NOT NULL REFERENCES parent_users(user_id) ON DELETE CASCADE
linked_at    TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `access_points`

```sql
ap_id        UUID PRIMARY KEY DEFAULT gen_random_uuid()
bssid        VARCHAR(17) UNIQUE NOT NULL
ssid         VARCHAR(100)
x_m          FLOAT                              -- physical position, pending IT (OQ-03)
y_m          FLOAT
z_m          FLOAT
band         VARCHAR(10)                        -- "2.4GHz" or "5GHz"
created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
```

### `ap_calibration`

```sql
cal_id       UUID PRIMARY KEY DEFAULT gen_random_uuid()
ap_id        UUID NOT NULL REFERENCES access_points(ap_id) ON DELETE CASCADE
band         VARCHAR(10) NOT NULL
offset_m     FLOAT NOT NULL
std_dev_m    FLOAT NOT NULL
sample_count INTEGER NOT NULL
calibrated_at TIMESTAMPTZ NOT NULL DEFAULT now()
is_reliable  BOOLEAN NOT NULL DEFAULT TRUE
```

### `imu_samples`

```sql
sample_id    UUID PRIMARY KEY DEFAULT gen_random_uuid()
device_id    UUID NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE
ts_device_ms BIGINT NOT NULL                   -- MCU timestamp
ts_server    TIMESTAMPTZ NOT NULL DEFAULT now()
ax_ms2       FLOAT NOT NULL
ay_ms2       FLOAT NOT NULL
az_ms2       FLOAT NOT NULL
gx_rads      FLOAT NOT NULL
gy_rads      FLOAT NOT NULL
gz_rads      FLOAT NOT NULL
seq          SMALLINT NOT NULL
```

### `rtt_measurements`

```sql
meas_id      UUID PRIMARY KEY DEFAULT gen_random_uuid()
device_id    UUID NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE
ap_id        UUID NOT NULL REFERENCES access_points(ap_id) ON DELETE CASCADE
ts_device_ms BIGINT NOT NULL
ts_server    TIMESTAMPTZ NOT NULL DEFAULT now()
d_raw_mean_m FLOAT NOT NULL
d_raw_std_m  FLOAT NOT NULL
d_corrected_m FLOAT
rssi_dbm     SMALLINT NOT NULL
band         VARCHAR(10) NOT NULL
```

### `position_estimates`

```sql
pos_id       UUID PRIMARY KEY DEFAULT gen_random_uuid()
device_id    UUID NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE
ts_server    TIMESTAMPTZ NOT NULL DEFAULT now()
x_m          FLOAT NOT NULL
y_m          FLOAT NOT NULL
source       VARCHAR(20) NOT NULL               -- "fused" | "wifi_only" | "imu_only"
confidence   FLOAT NOT NULL
active_aps   SMALLINT NOT NULL
mode         VARCHAR(20) NOT NULL
```

---

## 14. API Contracts

### 14.1 Gateway Endpoint

Device POSTs directly to:

```
POST https://trakn.duckdns.org/api/v1/gateway/packet
Header: X-API-Key: <gateway_api_key>
Header: Content-Type: application/json
```

### 14.2 Device Direct POST Body

Sent by the BW16 over venue Wi-Fi:

```json
{
  "device_mac":  "24:42:E3:15:E5:72",
  "rx_ts_utc":   "2026-02-27T10:15:30.123Z",
  "payload_b64": "<base64-encoded packet bytes — IMU 0x01 or RTT 0x02>"
}
```

Both IMU (0x01) and RTT (0x02) packets use this same body format.
`device_mac` is used to look up the registered device in the database.

### 14.3 Server → App (WebSocket Position Message)

```json
{
  "device_id":  "uuid-string",
  "ts_utc":     "2026-02-27T10:15:30.456Z",
  "x_m":        12.5,
  "y_m":        8.3,
  "source":     "fused",
  "confidence": 0.72,
  "active_aps": 3,
  "mode":       "normal"
}
```

`mode` values: `"normal"` | `"degraded"` | `"imu_only"` | `"disconnected"`
`source` values: `"fused"` | `"wifi_only"` | `"imu_only"`

### 14.4 Parent REST Endpoints

```
POST   /api/v1/auth/login              → JWT token
GET    /api/v1/devices                 → list linked devices
GET    /api/v1/devices/{id}/position   → last known position
GET    /api/v1/health                  → system health status
WS     /ws/position/{device_id}        → real-time position stream
```

### 14.5 Health Response

```json
{
  "status": "healthy",
  "database": "connected",
  "fusion_engine": "running",
  "active_devices": 1,
  "uptime_seconds": 3600
}
```

---

## 15. BLE Packet Protocol

All packets are little-endian. Parse using `struct` with `<` prefix.

### 15.1 IMU Packet — Type 0x01 (40 bytes total)

| Offset | Field | Type | Notes |
|---|---|---|---|
| 0 | packet_type | uint8 | = 0x01 |
| 1–6 | device_mac | uint8[6] | 48-bit MAC address |
| 7–14 | timestamp_ms | uint64 | MCU ms since boot |
| 15–18 | ax | float32 | m/s² |
| 19–22 | ay | float32 | m/s² |
| 23–26 | az | float32 | m/s² |
| 27–30 | gx | float32 | rad/s |
| 31–34 | gy | float32 | rad/s |
| 35–38 | gz | float32 | rad/s |
| 39 | seq | uint8 | wraps at 255 |

### 15.2 RTT Packet — Type 0x02 (variable length, little-endian)

**Fixed header (16 bytes):**

| Offset | Field | Type | Notes |
|---|---|---|---|
| 0 | packet_type | uint8 | = 0x02 |
| 1–6 | device_mac | uint8[6] | |
| 7–14 | timestamp_ms | uint64 | |
| 15 | ap_count | uint8 | N (number of AP records) |

**Per AP record (16 bytes, repeated N times starting at byte 16):**

| Offset | Field | Type | Notes |
|---|---|---|---|
| 0–5 | bssid | uint8[6] | |
| 6–9 | d_raw_mean | float32 | meters |
| 10–13 | d_raw_std | float32 | meters |
| 14 | rssi | int8 | dBm |
| 15 | band | uint8 | 0x01=2.4GHz, 0x02=5GHz |

---

## 16. Infrastructure and Deployment

### 16.1 Server Deployment

```yaml
# docker-compose.yml (top-level structure)
services:
  db:       PostgreSQL 16, persistent volume
  backend:  FastAPI app, env vars from .env
  nginx:    TLS termination, reverse proxy to backend
```

### 16.2 Environment Variables (.env)

```
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/localization
SECRET_KEY=<random 64-char hex>
GATEWAY_API_KEY=<random 32-char hex>
ALLOWED_ORIGINS=https://trakn.duckdns.org
```

### 16.3 What to Give the Venue IT Team

- Device Wi-Fi MAC address: `24:42:E3:15:E5:72`
- Network to register on: `QU-User` (internet access only)
- Access type: outbound HTTPS to 35.238.189.188 port 443 only
- Duration: semester duration (~3 months)
- **Status:** Completed — QU IT confirmed registration on 4 March 2026 (contact: Ajay)

### 16.4 File Structure

```
project-root/
├── backend/
│   ├── app/
│   │   ├── api/          gateway.py, parent.py, admin.py, websocket.py
│   │   ├── core/         config.py, security.py, ble_parser.py
│   │   ├── db/           models.py, session.py, init_db.py
│   │   ├── fusion/       ekf.py, bayesian_grid.py, observation_model.py,
│   │   │                 offset_corrector.py, coordinator.py, grid_loader.py,
│   │   │                 pdr.py, stride_svr.pkl, stride_training_data.json
│   │   ├── schemas/      gateway.py, position.py
│   │   └── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── firmware/
│   └── bw16/
│       └── main/         main.ino (unified sketch — IMU + RTT + Wi-Fi sender),
│                         packet_format.h
├── app/
│   └── lib/              screens/, services/, models/
├── tests/
│   ├── test_ble_parser.py
│   ├── test_db_schema.py
│   ├── test_security.py
│   ├── test_offset_corrector.py
│   ├── test_observation_model.py
│   ├── test_bayesian_grid.py
│   ├── test_ekf.py
│   ├── test_pdr.py
│   ├── test_fusion_coordinator.py
│   ├── test_gateway_endpoints.py
│   ├── test_parent_api.py
│   ├── test_websocket.py
│   ├── test_admin_endpoints.py
│   ├── test_health.py
│   ├── test_grid_loader.py
│   └── integration/      test_full_pipeline.py, test_failure_modes.py,
├── tasks.json
├── progress.txt
├── docker-compose.yml
├── .env
└── DEPLOYMENT.md
```

---

## 17. Testing Requirements

### 17.1 Coverage

Minimum 80% line coverage across `backend/app/`. Run with:

```bash
pytest --cov=backend/app --cov-fail-under=80 --tb=short -q
```

### 17.2 Test Categories Required

- **Unit tests:** every function in `backend/app/` has a corresponding test
- **PDR tests:** `tests/test_pdr.py` must cover: filter convergence, gyro bias calibration, step detection (true positive, false positive suppression, debounce), Weinberg stride formula, histogram bin edges, SVR feature extraction, stride clamping, position update math
- **Integration tests:** full pipeline from raw BLE bytes to WebSocket output
- **Failure mode tests:** each failure condition in Section 12 exercised
- **Flutter tests:** `flutter analyze` with zero errors; `flutter build apk --debug` succeeds

### 17.3 Test Naming Convention

```
test_<function_name>_<scenario>
```

Examples: `test_parse_imu_packet_valid`, `test_ekf_update_divergence_reset`, `test_bayesian_grid_collapse_recovery`

---

## 18. Implementation Plan

Twenty-one tasks across 9 phases. Full details in `tasks.json`.

| ID | Title | Owner | Phase |
|---|---|---|---|
| TASK-01 | Initialize project structure | shared | 1 — Scaffolding |
| TASK-02 | requirements.txt and Dockerfile | person-a | 1 — Scaffolding |
| TASK-03 | PostgreSQL schema and SQLAlchemy models | person-a | 1 — Scaffolding |
| TASK-04 | Configuration and security core | person-a | 1 — Scaffolding |
| TASK-05 | BLE packet parser | person-b | 2 — Protocol |
| TASK-05B | BW16 firmware — IMU reader port to BW16+MPU6050 | person-b | 2 — Protocol |
| TASK-05C | BW16 firmware — Wi-Fi transmitter (direct HTTPS POST, IMU + RTT) | person-b | 2 — Protocol |
| TASK-06 | Gateway API endpoint — single direct POST path | person-b | 2 — Protocol |
| TASK-07 | Offset correction engine | person-a | 3 — Calibration |
| TASK-08 | Calibration admin endpoints | person-a | 3 — Calibration |
| TASK-09 | Floor plan grid loader | person-c | 4 — Bayesian Grid |
| TASK-10 | Observation model implementation | person-c | 4 — Bayesian Grid |
| TASK-11 | Bayesian grid update engine | person-c | 4 — Bayesian Grid |
| TASK-12 | EKF predict and update steps | person-c | 5 — EKF Fusion |
| TASK-12B | PDR Python module — MATLAB migration | person-c | 5 — EKF Fusion |
| TASK-13 | Fusion coordinator — unified fusion pipeline | person-c | 5 — EKF Fusion |
| TASK-14 | WebSocket broadcaster | person-d | 6 — Real-time API |
| TASK-15 | Parent REST API endpoints | person-d | 6 — Real-time API |
| TASK-16 | Flutter project setup and WebSocket service | person-d | 7 — Mobile App |
| TASK-17 | Flutter live map screen | person-d | 7 — Mobile App |
| TASK-18 | Full integration test pipeline (direct Wi-Fi path) | person-b | 8 — Integration |
| TASK-19 | Health check and monitoring endpoint | person-a | 8 — Integration |
| TASK-20 | Final validation and cleanup | person-d | 8 — Integration |

### 18.1 Working Session Protocol (4 Agents in Parallel)

- Each laptop runs an Antigravity agent with Claude
- Each agent operates on its own git branch, within its file scope
- Tasks are tracked in `tasks.json` on GitHub (pull-merge-push protocol — see `tasks.json` and agent rules)
- Three sync points during each session: ~1.5h, ~3h, final hour
- TASK-01 is done together on one screen before lanes split

---

## 19. Open Questions

These are unresolved. Any agent implementation touching these areas must stop and flag it to the team.

| ID | Question | Impact |
|---|---|---|
| OQ-01 | Does the BW16 Realtek SDK expose per-BSSID one-sided FTM RTT with burst control? | Critical — determines feasibility of RTT on BW16 |
| OQ-03 | AP (x, y, z) coordinates in H07-C — IT confirmed no floor plan drawings available. Manual survey required. | High — required for offset calibration. Team must walk corridor and record AP positions manually. |
| OQ-04 | Do QU APs support 40/80 MHz bandwidth for RTT, or 20 MHz only? | Medium — affects accuracy estimates |
| OQ-05 | Which QU APs in H07-C are in DFS 5 GHz band? | Medium — DFS APs must be excluded |

---

## 20. Glossary

| Term | Definition |
|---|---|
| BLE | Bluetooth Low Energy |
| BW16 | Realtek RTL8720DN dual-band Wi-Fi + BLE embedded module |
| DLPF | Digital Low-Pass Filter — MPU6050 on-chip filter, configured to 21 Hz |
| EKF | Extended Kalman Filter |
| FTM | Fine Timing Measurement — IEEE 802.11 ranging protocol |
| IMU | Inertial Measurement Unit (accelerometer + gyroscope) |
| MAP | Maximum A Posteriori — the most probable cell in the Bayesian grid |
| MPU6050 | InvenSense 6-DOF IMU (accel + gyro), I2C address 0x68 |
| NLOS | Non-Line-of-Sight — signal path obstructed by walls or furniture |
| PDR | Pedestrian Dead Reckoning — position estimation from step detection and heading |
| RTT | Round-Trip Time — used here as a ranging measurement |
| SVR | Support Vector Regression — ML model for stride length estimation |
| ZUPT | Zero Velocity Update — EKF correction applied when device is stationary |
| QU | Qatar University |
| H07 | Building H07 on the Qatar University campus |
