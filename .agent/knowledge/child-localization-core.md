# Knowledge Item: Child Indoor Localization System — Core Context

**ID:** KI-2026-001
**File:** `.agent/knowledge/child-localization-core.md`
**Created:** 2026-02-27
**Updated:** 2026-02-28
**Version:** 2
**Confidence:** HIGH
**Status:** ACTIVE

---

## Summary

This KI captures the full verified context of the QU Senior Design child indoor
localization system. The system localizes a BW16-wearing child in Building H07,
C Corridor at Qatar University using one-sided Wi-Fi RTT + IMU/PDR fused via EKF.
All architecture decisions, mathematical parameters, BLE packet contracts, API schemas,
failure modes, and team structure documented here were established during Senior Design
(February 2026). Load this KI at the start of any session touching this project.

---

## Relevance Triggers

child localization, indoor localization, BW16, RTT, IMU, EKF, PDR, Bayesian grid,
observation model, offset calibration, sensor fusion, FastAPI, asyncpg, Flutter,
WebSocket, BLE gateway (Model 2 future work), Qatar University, H07, corridor, senior design, tasks.json,
TASK-01, TASK-02, TASK-03, TASK-04, TASK-05, TASK-05B, TASK-05C, TASK-06, TASK-07, TASK-08,
TASK-09, TASK-10, TASK-11, TASK-12, TASK-12B, TASK-13, TASK-14, TASK-15, TASK-16,
TASK-17, TASK-18, TASK-19, TASK-20, person-a, person-b, person-c, person-d,
MPU6050, step detection, stride length, Weinberg, SVR, histogram, pdr.py,
gyro bias, EMA filter, pedestrian dead reckoning, MATLAB migration

---

## Tags

`algorithm` `architecture` `firmware` `mobile` `database` `calibration`
`child-localization` `senior-design` `qatar-university` `ekf` `bayesian` `pdr` `svr` `mpu6050`

---

## Artifact 1 — Architecture Decisions (Locked)

```
Type: decision
Verified: 2026-03-01
```

| Component | Decision | Rationale |
|---|---|---|
| RTT method | One-sided RTT (legacy AP compatible) | QU APs do not support cooperative two-sided FTM |
| AP selection | Time-last-seen (primary strategy) | Outperforms distance-based and RSSI-based (Horn 2022) |
| Fusion | EKF, 4-state [px, py, vx, vy] | Computationally efficient; adequate for Gaussian noise model |
| Backend | FastAPI + asyncpg + SQLAlchemy 2.0 async | Async WebSocket + REST on single process |
| Mobile | Flutter (Android 12 primary) | Single codebase; sufficient for map rendering |
| Primary transport | Direct Wi-Fi — device POSTs IMU + RTT over venue Wi-Fi to server port 443 | GSM, BLE gateway (Model 2 future work) |
| Server port | 443 via Nginx — port 8000 internal only | Exposing port 8000 |
| RTT operation | Always active — device ranges against QU APs | Disabling RTT |
| Deployment | Venue-managed tag — IT registers MAC once | Consumer-owned device |
| Server hosting | GCP e2-micro, static IP 35.238.189.188 | Free tier; static IP required for IT AP config |
| Grid cell size | 0.5 m × 0.5 m | Matches Horn 2022 reference implementation |
| Database | PostgreSQL 16 + asyncpg | |

**These decisions are final. Do not reopen without explicit user instruction.**

---

## Artifact 2 — Verified Mathematical Parameters

```
Type: code-pattern
Source: Horn (2022) "Indoor Localization using Uncooperative Wi-Fi Access Points"
Verified: 2026-02-27
```

```python
# File: backend/app/fusion/observation_model.py
# All parameter values are locked — do not change without user confirmation
import numpy as np

X0      = 5.5    # m   — minimum approach distance (AP mounting height)
A       = 2.23   # amplitude of mean deviation
ALPHA   = 0.043  # m⁻¹ — decay rate of mean deviation
SIGMA0  = 4.0    # m   — baseline standard deviation
SIGMA_M = 0.55   # slope of std increase with distance
BETA    = 0.015  # m⁻¹ — decay rate of standard deviation

def mu(x: float) -> float:
    """Expected RTT measurement given true distance x (meters)."""
    return x * (1 + A * ALPHA * (x - X0) * np.exp(-ALPHA * (x - X0)))

def sigma(x: float) -> float:
    """Standard deviation of RTT measurement given true distance x."""
    return SIGMA0 + SIGMA_M * (x - X0) * np.exp(-BETA * (x - X0))

def p_observation(y: float, x: float) -> float:
    """p(y | x) — likelihood of measuring y given true distance x."""
    x_c = max(x, X0)
    s   = max(sigma(x_c), 0.1)
    return (1.0 / (np.sqrt(2 * np.pi) * s)) * np.exp(-0.5 * ((y - mu(x_c)) / s) ** 2)
```

```python
# File: backend/app/fusion/ekf.py
import numpy as np

class ExtendedKalmanFilter:
    def __init__(self, initial_pos: tuple[float, float]):
        self.x = np.array([initial_pos[0], initial_pos[1], 0.0, 0.0])
        self.P = np.diag([25.0, 25.0, 4.0, 4.0])
        self.Q = np.diag([0.01, 0.01, 0.1, 0.1])
        self.R_normal   = np.diag([9.0, 9.0])
        self.R_degraded = np.diag([18.0, 18.0])

    def predict(self, ax: float, ay: float, dt: float) -> None:
        F = np.array([[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]])
        B = np.array([[0.5*dt**2,0],[0,0.5*dt**2],[dt,0],[0,dt]])
        self.x = F @ self.x + B @ np.array([ax, ay])
        self.P = F @ self.P @ F.T + self.Q

    def update(self, pos_bayes: tuple[float, float], degraded: bool = False) -> None:
        H = np.array([[1,0,0,0],[0,1,0,0]])
        R = self.R_degraded if degraded else self.R_normal
        z = np.array(pos_bayes)
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P

    def check_divergence(self, pos_bayes: tuple[float, float]) -> bool:
        return np.linalg.norm(self.x[:2] - np.array(pos_bayes)) > 10.0

    def reset_from_bayes(self, pos_bayes: tuple[float, float]) -> None:
        self.x = np.array([pos_bayes[0], pos_bayes[1], 0.0, 0.0])
        self.P = np.diag([25.0, 25.0, 4.0, 4.0])

    def apply_zupt(self) -> None:
        self.x[2] = 0.0
        self.x[3] = 0.0

    def get_position(self) -> tuple[float, float]:
        return (float(self.x[0]), float(self.x[1]))
```

```python
# File: backend/app/fusion/offset_corrector.py
def correct(d_raw_m: float, offset_m: float) -> float:
    """Subtract per-AP, per-band calibrated offset. Clamp minimum 0.5 m."""
    return max(d_raw_m - offset_m, 0.5)
```

---

## Artifact 3 — BLE Packet Wire Format

```
Type: api-contract
Verified: 2026-02-27
Encoding: little-endian throughout
```

**IMU Packet (Type 0x01) — 40 bytes:**

| Offset | Field | Type |
|---|---|---|
| 0 | packet_type = 0x01 | uint8 |
| 1–6 | device_mac | uint8[6] |
| 7–14 | timestamp_ms | uint64 |
| 15–38 | ax, ay, az, gx, gy, gz | float32 × 6 |
| 39 | seq | uint8 (wraps at 255) |

Parse: `struct.unpack_from("<Qfffffff", data, 7)` → ts, ax, ay, az, gx, gy, gz

**RTT Packet (Type 0x02) — variable:**

Fixed header bytes 0–15 (type, MAC, ts uint64, ap_count N).
Per AP record (16 bytes × N, starting at byte 16):
bssid[6], d_raw_mean f32, d_raw_std f32, rssi i8, band u8
band: 0x01 = 2.4 GHz, 0x02 = 5 GHz

---

## Artifact 4 — AP Calibration Data Structure

```
Type: configuration
Status: PENDING — real values to be filled after calibration walk
```

```python
# File: backend/app/fusion/offset_corrector.py
# Key: (BSSID_uppercase, band_string) → offset in meters

CALIBRATION_OFFSETS: dict[tuple[str, str], float] = {
    # ("AA:BB:CC:DD:EE:FF", "5GHz"):   2587.3,   ← fill after calibration
    # ("AA:BB:CC:DD:EE:FF", "2.4GHz"): 1542.1,
}

# APs excluded if calibration std_dev > 20 m or sample_count < 30
UNRELIABLE_APS: set[str] = set()

# AP physical positions — pending IT confirmation (OQ-03)
AP_POSITIONS: dict[str, dict] = {
    # "AA:BB:CC:DD:EE:FF": {"x_m": 0.0, "y_m": 0.0, "z_m": 6.5}
}
```

---

## Artifact 5 — Operating Modes and Failure Recovery

```
Type: constraint
Verified: 2026-02-27
```

| Mode | Trigger | EKF | WebSocket mode field |
|---|---|---|---|
| `normal` | ≥ 2 APs, IMU active | predict + update R_normal | `"normal"` |
| `degraded` | 1 AP only | predict + update R_degraded | `"degraded"` |
| `imu_only` | 0 APs | predict only | `"imu_only"` |
| `disconnected` | No data > 5 s | suspended | `"disconnected"` |

Grid collapse (sum < 1e-10) → reset uniform prior, log, continue.
EKF divergence (> 10 m for > 5 cycles) → reset from Bayesian MAP, P = P₀.
ZUPT (|a| < 0.05 m/s² for > 2 s) → set vx = vy = 0.

---

## Artifact 6 — Team and Task Ownership

```
Type: reference
Verified: 2026-03-04
```

4-person team. All work done in joint working sessions using Antigravity IDE with Claude agents.
Each laptop runs one agent. Agents work in parallel on separate task sets.
`tasks.json` is on GitHub. Pull-merge-push protocol prevents overwrites (see workspace rules).

| Identity | Tasks |
|---|---|
| person-a | TASK-02, 03, 04, 07, 08, 19 (Infrastructure & Calibration) |
| person-b | TASK-05, 05B, 05C, 06, 18 (Firmware, Protocol, BW16 unified sketch) |
| person-c | TASK-09, 10, 11, 12, 12B, 13 (Fusion Engine + PDR Python module) |
| person-d | TASK-14, 15, 16, 17, 20 (Mobile & WebSocket) |
| shared | TASK-01 (done together first) |

---

## Artifact 7 — PDR Python Module (Verified Algorithm Migration)

```
Type: code-pattern
Origin: Senior Design 1 MATLAB implementation, verified on Arduino Uno R4 + MPU6050
Migrated: Python 3.11 / NumPy / scikit-learn
File: backend/app/fusion/pdr.py
Status: ACTIVE — parameters are locked
```

```python
# backend/app/fusion/pdr.py
# Full PDR implementation migrated from MATLAB (Senior Design 1).
# All constants are calibrated/verified — do not change without user confirmation.

import numpy as np
import pickle
import json
from pathlib import Path
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

# ── Locked constants ────────────────────────────────────────────────────────
WIN_STEP      = 0.40    # s — rolling window for step detection
MIN_STEP_DT   = 0.35    # s — minimum interval between steps
K_WEIN        = 0.47    # Weinberg coefficient (calibrated)
P_WEIN        = 0.25    # Weinberg exponent
MIN_STRIDE    = 0.25    # m
MAX_STRIDE    = 1.40    # m
SVR_MIN       = 0.45    # m — SVR output clamp lower bound
SVR_MAX       = 0.90    # m — SVR output clamp upper bound
FC            = 3.2     # Hz — EMA filter cutoff
CAL_WINDOW    = 2.0     # s — gyro bias calibration duration
STAT_STD_TH   = 1.2     # m/s² — stationary guard threshold
GRAV_FLAT_TH  = 0.4     # m/s² — near-gravity flat guard

# Histogram bin config
AMAX    = 20.0
KBIN    = 0.117
ML      = 10    # bins below gravity
MH      = 10    # bins above gravity
M       = ML + MH

MODEL_PATH    = Path(__file__).parent / "stride_svr.pkl"
TRAIN_PATH    = Path(__file__).parent / "stride_training_data.json"


def _build_bin_edges() -> np.ndarray:
    """Build log-linear bin edges for acceleration histogram (locked parameters)."""
    E = np.zeros(M + 1)
    for i in range(1, M + 1):
        if i <= ML:
            E[i] = 9.8 * (0.5 * KBIN) ** ((ML + 1 - i) / ML)
        else:
            E[i] = 9.8 + (AMAX - 9.8) * (i - ML - 1) / MH
    return E


BIN_EDGES = _build_bin_edges()


class PDRProcessor:
    """
    Pedestrian Dead Reckoning processor.
    Receives IMU samples one at a time, emits (x, y, heading, step_count) on each update.
    All algorithm parameters are locked — calibrated in Senior Design 1.
    """

    def __init__(self):
        self.x: float = 0.0
        self.y: float = 0.0
        self.heading: float = 0.0

        # EMA state
        self._a_mag_f: float | None = None
        self._gz_f: float | None = None

        # Gyro bias calibration
        self._bias_collecting: bool = True
        self._gyro_sum: float = 0.0
        self._bias_count: int = 0
        self._gyro_bias: float = 0.0

        # Rolling buffers
        self._buf_t: list[float] = []
        self._buf_a: list[float] = []

        # Step tracking
        self._last_step_t: float = -np.inf
        self._step_count: int = 0
        self._step_features: list[np.ndarray] = []
        self._stride_pred: list[float] = []

        # Packet counter for subsampling
        self._pkt_count: int = 0

        # SVR model
        self._model = self._load_model()

    @staticmethod
    def _load_model():
        if MODEL_PATH.exists():
            with open(MODEL_PATH, "rb") as f:
                return pickle.load(f)
        return None

    def update(
        self,
        ax: float, ay: float, az: float,
        gz: float,
        t: float,
        dt: float
    ) -> dict:
        """
        Process one IMU sample.

        Args:
            ax, ay, az: accelerometer (m/s²)
            gz: gyroscope-z (rad/s, already converted from raw)
            t:  elapsed time since device start (seconds)
            dt: time since last sample (seconds)

        Returns dict with keys: x, y, heading_rad, step_count, total_distance
        """
        dt = max(dt, 1e-3)

        # ── Gyro bias calibration ────────────────────────────────────────────
        if self._bias_collecting:
            self._gyro_sum += gz
            self._bias_count += 1
            if t >= CAL_WINDOW:
                self._gyro_bias = self._gyro_sum / self._bias_count
                self._bias_collecting = False
            gz_corrected = 0.0  # freeze heading during calibration
        else:
            gz_corrected = gz - self._gyro_bias

        # ── EMA filter ───────────────────────────────────────────────────────
        alpha = 1.0 - np.exp(-2.0 * np.pi * FC * dt)
        a_mag = np.sqrt(ax**2 + ay**2 + az**2)

        if self._a_mag_f is None:
            self._a_mag_f = a_mag
        self._a_mag_f += alpha * (a_mag - self._a_mag_f)

        if self._gz_f is None:
            self._gz_f = gz_corrected
        self._gz_f += alpha * (gz_corrected - self._gz_f)

        # ── Heading integration ───────────────────────────────────────────────
        self.heading += self._gz_f * dt

        # ── Rolling buffer ───────────────────────────────────────────────────
        self._buf_t.append(t)
        self._buf_a.append(self._a_mag_f)
        cutoff = t - WIN_STEP
        while self._buf_t and self._buf_t[0] < cutoff:
            self._buf_t.pop(0)
            self._buf_a.pop(0)

        # ── Step detection (every other packet) ──────────────────────────────
        self._pkt_count += 1
        if self._pkt_count % 2 == 0 and len(self._buf_a) >= 2:
            buf = np.array(self._buf_a)

            # False-step suppression guards
            if np.std(buf) < STAT_STD_TH:
                return self._state()
            if abs(np.mean(buf) - 9.8) < GRAV_FLAT_TH:
                return self._state()

            a_max = float(np.max(buf))
            a_min = float(np.min(buf))
            swing = a_max - a_min
            th_peak  = float(np.median(buf)) + 2.0 * float(np.std(buf))
            th_swing = 0.9 * float(np.std(buf))
            dt_step  = t - self._last_step_t

            if dt_step > MIN_STEP_DT and a_max > th_peak and swing > th_swing:
                self._last_step_t = t
                self._step_count += 1

                # Histogram features
                counts, _ = np.histogram(buf, bins=BIN_EDGES)
                hfeat = counts / max(counts.sum(), 1.0)

                # Stride estimation
                wein = K_WEIN * (swing ** P_WEIN)
                if self._model is not None:
                    svr_pred = float(self._model.predict(hfeat.reshape(1, -1))[0])
                    svr_pred = np.clip(svr_pred, SVR_MIN, SVR_MAX)
                    stride = 0.5 * wein + 0.5 * svr_pred
                else:
                    stride = wein
                stride = float(np.clip(stride, MIN_STRIDE, MAX_STRIDE))

                self._stride_pred.append(stride)
                self._step_features.append(hfeat)

                # Dead reckoning
                self.x += stride * np.cos(self.heading)
                self.y += stride * np.sin(self.heading)

        return self._state()

    def _state(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "heading_rad": self.heading,
            "step_count": self._step_count,
            "total_distance": sum(self._stride_pred),
        }

    def apply_zupt(self) -> None:
        """Call when |a| < 0.05 m/s² for > 2 s. Zeroes velocity in EKF via caller."""
        # ZUPT is applied to EKF state externally; PDR records the event
        pass

    def save_training_data(self, d_true: float) -> None:
        """Append current walk's features + true stride label to training dataset."""
        n = len(self._step_features)
        if n == 0:
            return
        stride_true = d_true / n
        existing = {"X": [], "y": []}
        if TRAIN_PATH.exists():
            with open(TRAIN_PATH) as f:
                existing = json.load(f)
        existing["X"].extend([f.tolist() for f in self._step_features])
        existing["y"].extend([stride_true] * n)
        with open(TRAIN_PATH, "w") as f:
            json.dump(existing, f)

    @staticmethod
    def retrain_model() -> None:
        """Retrain SVR on full dataset and overwrite stride_svr.pkl."""
        if not TRAIN_PATH.exists():
            raise FileNotFoundError("No training data found.")
        with open(TRAIN_PATH) as f:
            data = json.load(f)
        X = np.array(data["X"])
        y = np.array(data["y"])
        mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        X, y = X[mask], y[mask]
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("svr", SVR(kernel="rbf", gamma="scale")),
        ])
        model.fit(X, y)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)
```

---

## Artifact 8 — Open Questions

```
Type: constraint
Status: Unresolved — flag if code touches these areas
```

| ID | Question | Impact |
|---|---|---|
| OQ-01 | BW16 SDK: per-BSSID one-sided FTM RTT with burst control? | Critical |
| OQ-02 [CLOSED] | QU AP BLE gateway (Model 2 future work) protocol? (HTTP / MQTT / CMX) | Critical |
| OQ-03 | AP (x, y, z) coordinates confirmed by IT? | High |
| OQ-04 | AP bandwidth: 40/80 MHz or 20 MHz only? | Medium |
| OQ-05 | Which QU APs are in DFS 5 GHz band? | Medium |

---

## Update Instructions

Update this KI (increment version, update `updated` date) when:

- Calibration offsets collected → update Artifact 4 with real values
- Any OQ resolved → update Artifact 7, mark resolved
- A code pattern confirmed working via tests → add `# Tested: [date]` comment
- Architecture decision revisited → update Artifact 1, document reason

Do not update for: session scaffolding, unverified assumptions, temporary paths.
