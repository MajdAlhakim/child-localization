---
trigger: always_on
---

# Workspace Rules — Child Indoor Localization System

**File:** `.agent/rules/child-localization.md`
**Activation:** Always On
**Scope:** This workspace only
**Extends:** `@GEMINI.md` (Global Rules)

---

## 1. Project Identity

Real-time child indoor localization system for Qatar University Building H07, C Corridor.
Stack: BW16 wearable (IMU + one-sided Wi-Fi RTT) → QU-USER Wi-Fi → HTTPS POST →
Cloud FastAPI server (trakn.duckdns.org:443) → EKF + Bayesian grid fusion → WebSocket → Flutter parent app.

Full specification: see `PRD.md` in the repository root.

---

## 2. Session Start Protocol (Mandatory — Every Session)

Execute these steps in exact order before producing any output or writing any code:

```
Step 1.  git pull --rebase origin main
Step 2.  cat tasks.json
Step 3.  cat progress.txt
Step 4.  git log --oneline -10
Step 5.  ls -la
```

Do not skip any step. Do not assume what has been done.
From `tasks.json`, identify: which tasks are done by others (read-only to you),
which of YOUR tasks are pending (start from the first one),
which tasks are in-progress by others (be aware of file contention).

---

## 3. GitHub Task Update Protocol (Mandatory — After Every Completed Task)

When pytest passes and your task is complete, execute this exact sequence:

```
Step 1.  git pull --rebase origin main
         ← Always pull first, even if you pulled 10 minutes ago.

Step 2.  Read tasks.json from disk (the version just pulled).

Step 3.  Update ONLY the entry where "owner" == YOUR_IDENTITY:
         Set "status": "done"
             "completed_at": "<ISO 8601 timestamp>"
             "completed_by": "<your identity>"
             "notes": "<one line: what was implemented>"

Step 4.  Do NOT modify entries owned by anyone else.
         Do NOT modify "owner", "id", "title", or "phase" fields.
         Do NOT reformat or reorder the JSON.

Step 5.  Append one line to progress.txt:
         "DONE [TASK-ID] (owner): <what was implemented> — <timestamp>"

Step 6.  git add tasks.json progress.txt

Step 7.  git commit -m "[TASK-XX] done: <one-line description>"

Step 8.  git push origin main

Step 9.  IF push is rejected (exit code non-zero):
         → Return to Step 1. Pull, re-apply your change, push again.
         → Never use --force. Never overwrite the remote.
```

---

## 4. Task Ownership and File Scope

| Laptop | Owner identity | Tasks | Files (write access) |
|---|---|---|---|
| A | `person-a` | TASK-02,03,04,07,08,19 | `backend/app/db/*`, `backend/app/core/config.py`, `backend/app/core/security.py`, `backend/app/api/admin.py`, `docker-compose.yml`, `Dockerfile`, `backend/requirements.txt` |
| B | `person-b` | TASK-05,05B,05C,06,18 | `backend/app/core/ble_parser.py`, `backend/app/api/gateway.py`, `backend/app/schemas/gateway.py`, `tests/integration/*`, `firmware/bw16/*` |
| C | `person-c` | TASK-09,10,11,12,12B,13 | `backend/app/fusion/*` (includes `pdr.py`, `stride_svr.pkl`, `stride_training_data.json`) |
| D | `person-d` | TASK-14,15,16,17,20 | `backend/app/api/websocket.py`, `backend/app/api/parent.py`, `app/lib/*` |
| All | `shared` | TASK-01 | Project scaffold |

Reading files outside your scope is permitted. Writing outside your scope is not.

---

## 5. Architecture Constraints (Locked — Do Not Revisit)

| Decision | What was decided | Do not propose |
|---|---|---|
| RTT method | One-sided RTT only | Two-sided FTM, RSSI fingerprinting |
| Backend | FastAPI + asyncpg + SQLAlchemy 2.0 async | Flask, Django, sync SQLAlchemy |
| Fusion | EKF 4-state [px, py, vx, vy] | Particle filter, pure Bayesian only |
| Mobile | Flutter (Android 12 primary) | React Native, native Android/iOS |
| Device→Server path | BW16 → direct Wi-Fi POST to cloud VM (QU-USER SSID) | BLE gateway relay, university LAN hosting |
| Server hosting | Cloud VM with public IP | Hosting on university network |
| AP selection | Time-last-seen (primary) | RSSI-only, distance-only |
| Grid cell size | 0.5 m × 0.5 m | Any other cell size |
| Database | PostgreSQL 16 + asyncpg | Any other database |

---

## 6. Mathematical Constants (Do Not Modify)

```
Observation model (Horn 2022):
  x₀ = 5.5 m     A = 2.23     α = 0.043 m⁻¹
  σ₀ = 4.0 m     σ_m = 0.55   β = 0.015 m⁻¹

RTT offset correction:
  d_corrected = d_raw − d_offset(AP, band)
  clamp minimum: 0.5 m
  Expected offset range: 2400–2700 m (5 GHz), ~1500 m (2.4 GHz)

EKF:
  State: [px, py, vx, vy]
  P₀ = diag([25, 25, 4, 4])
  Q  = diag([0.01, 0.01, 0.1, 0.1])
  R_normal   = diag([9.0, 9.0])      σ_wifi = 3.0 m, ≥2 APs
  R_degraded = diag([18.0, 18.0])    σ_wifi = 6.0 m, <2 APs
  Divergence reset threshold: 10 m for > 5 consecutive cycles

PDR (verified in Senior Design 1 — migrated from MATLAB to Python, do not change):
  MPU6050 config: ±4g (8192 LSB/g), ±500°/s (65.5 LSB/°/s), 21 Hz DLPF
  Accel conversion: raw × 0.0011978149 m/s²
  Gyro conversion:  raw × 0.0002663309 rad/s
  EMA filter cutoff: f_c = 3.2 Hz  →  α = 1 − exp(−2π·3.2·dt)
  Gyro bias calibration window: first 2.0 s of data
  Step detection window: 0.40 s rolling
  Min step interval: 0.35 s
  Peak threshold: median(window) + 2.0 × std(window)
  Swing threshold: 0.9 × std(window)
  Stationary guard: std(window) < 1.2 → skip
  Near-gravity guard: |mean(window) − 9.8| < 0.4 → skip
  Weinberg K: 0.47    Weinberg p: 0.25
  Stride clamp: [0.25, 1.40] m    SVR clamp: [0.45, 0.90] m
  Hybrid blend: 0.5·Weinberg + 0.5·SVR (when model loaded)
  Histogram: 20 bins, Kbin=0.117, Ml=10, Mh=10, amax=20 m/s²
  E[0]=0; below-gravity bins log-spaced; above-gravity bins linear

PDR step detection (firmware/Arduino):
  Step trigger: |a_z| > 1.2 g  (used in BW16 firmware for raw step flag in BLE packet)
  ZUPT: |a| < 0.05 m/s² for > 2 s → set vx = vy = 0
```

---

## 7. BLE Packet Wire Format (Locked)

```
IMU (0x01) — 40 bytes, little-endian:
  [0] 0x01 | [1–6] MAC | [7–14] ts uint64 | [15–38] ax,ay,az,gx,gy,gz float32×6 | [39] seq uint8

RTT (0x02) — variable, little-endian:
  Header: [0] 0x02 | [1–6] MAC | [7–14] ts uint64 | [15] N uint8
  Per AP record (16 bytes × N starting at byte 16):
    [0–5] bssid | [6–9] d_raw_mean f32 | [10–13] d_raw_std f32 | [14] rssi i8 | [15] band u8
    band encoding: 0x01 = 2.4 GHz, 0x02 = 5 GHz
```

---

## 8. API Contracts (Locked Wire Formats)

**Gateway POST body (BW16 → server, direct Wi-Fi):**

```json
{ "device_mac": "24:42:E3:15:E5:72",
  "rx_ts_utc": "2026-02-27T10:15:30.123Z", "payload_b64": "<base64>" }
```

Authentication: `X-API-Key` header.

**WebSocket position message (server → app):**

```json
{ "device_id": "uuid", "ts_utc": "...", "x_m": 12.5, "y_m": 8.3,
  "source": "fused", "confidence": 0.72, "active_aps": 3, "mode": "normal" }
```

`mode` values: `"normal"` | `"degraded"` | `"imu_only"` | `"disconnected"`

**publish_position() interface (Person C calls, Person D implements):**

```python
async def publish_position(
    device_id: str, position: tuple[float, float],
    source: str, confidence: float, active_aps: int, mode: str
) -> None: ...
```

---

## 9. Performance Requirements (Non-Negotiable)

| Metric | Target | Minimum |
|---|---|---|
| IMU sampling rate | ≥ 50 Hz | ≥ 25 Hz |
| RTT cycle rate | ≥ 2 Hz | ≥ 1 Hz |
| WebSocket update rate | ≥ 4 Hz | ≥ 2 Hz |
| Bayesian grid update | ≤ 50 ms | ≤ 100 ms |
| End-to-end latency | ≤ 2.0 s | ≤ 2.5 s |
| Fused position RMS error | ≤ 2.5 m | ≤ 4.0 m |

If an implementation cannot meet a target, report it explicitly. Do not silently relax it.

---

## 10. Testing Rules

- Run the task's `test_command` from `tasks.json` before marking any task done.
- All tests must pass (0 failures) before marking done.
- Never delete, skip, comment out, or weaken an existing test.
- Never hard-code expected values to make a test pass.
- If a test appears incorrect, report it — do not work around it.

---

## 11. Failure Mode Reference

| Trigger | Mode | EKF behavior |
|---|---|---|
| ≥ 2 APs responding, IMU active | `normal` | predict + update R_normal |
| 1 AP only | `degraded` | predict + update R_degraded |
| 0 APs | `imu_only` | predict only |
| No device data > 5 s | `disconnected` | suspended |

Grid collapse (sum < 1e-10): reset to uniform prior, log, continue.
EKF divergence (> 10 m for > 5 cycles): reset state from Bayesian MAP, P = P₀.

---

## 12. Open Questions — Stop and Flag if Your Code Touches These

- **OQ-01:** Does BW16 Realtek SDK expose per-BSSID one-sided FTM RTT with burst control?
- ~~**OQ-02:** What BLE gateway protocol do QU APs support?~~ **CLOSED** — BLE gateway not required; direct Wi-Fi used.
- **OQ-03:** Exact AP (x, y, z) coordinates in H07-C — not yet confirmed from IT
- **OQ-04:** QU AP bandwidth — 20 MHz confirmed; 40/80 MHz availability unknown
- **OQ-05:** Which QU APs are in DFS 5 GHz band — list not yet obtained
