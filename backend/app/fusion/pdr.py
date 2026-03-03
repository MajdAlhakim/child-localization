"""
backend/app/fusion/pdr.py
Pedestrian Dead Reckoning — TASK-12B

Full faithful Python migration of the Senior Design 1 MATLAB PDR algorithm.
ALL constants, thresholds and math are locked — do not change without explicit
user instruction.

Reference: KI-2026-001 Artifact 7 (verified against MATLAB output).

Person C owns this file.
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

logger = logging.getLogger(__name__)

# ── Locked constants ──────────────────────────────────────────────────────────
WIN_STEP     = 0.40    # s    — rolling window width for step detection
MIN_STEP_DT  = 0.35    # s    — minimum debounce interval between steps
K_WEIN       = 0.47    # Weinberg coefficient (calibrated)
P_WEIN       = 0.25    # Weinberg exponent
MIN_STRIDE   = 0.25    # m    — Weinberg/hybrid stride clamp lower bound
MAX_STRIDE   = 1.40    # m    — Weinberg/hybrid stride clamp upper bound
SVR_MIN      = 0.45    # m    — SVR output clamp lower bound
SVR_MAX      = 0.90    # m    — SVR output clamp upper bound
FC           = 3.2     # Hz   — EMA low-pass filter cutoff frequency
CAL_WINDOW   = 2.0     # s    — gyro-bias calibration window
STAT_STD_TH  = 1.2     # m/s² — stationary guard: std(window) < threshold → reject
GRAV_FLAT_TH = 0.4     # m/s² — near-gravity guard: |mean − 9.8| < threshold → reject

# ── Histogram constants ───────────────────────────────────────────────────────
AMAX  = 20.0   # m/s² — maximum acceleration for histogram
KBIN  = 0.117  # log-scale compression factor
ML    = 10     # bins below gravity
MH    = 10     # bins above gravity
M     = ML + MH  # total bins = 20

MODEL_PATH = Path(__file__).parent / "stride_svr.pkl"
TRAIN_PATH = Path(__file__).parent / "stride_training_data.json"


# ── Histogram bin edges (built once from locked parameters) ───────────────────

def _build_bin_edges() -> np.ndarray:
    """
    Construct 20-bin acceleration histogram edges.

    Layout (locked — from MATLAB):
      E[0] = 0
      Bins 1..ML : log-spaced below gravity (9.8 m/s²)
      Bins ML+1..M : linearly spaced above gravity up to AMAX
    """
    E = np.zeros(M + 1)
    # E[0] = 0  (already set)
    for i in range(1, M + 1):
        if i <= ML:
            E[i] = 9.8 * (0.5 * KBIN) ** ((ML + 1 - i) / ML)
        else:
            E[i] = 9.8 + (AMAX - 9.8) * (i - ML - 1) / MH
    return E


BIN_EDGES: np.ndarray = _build_bin_edges()


# ── PDRProcessor ─────────────────────────────────────────────────────────────

class PDRProcessor:
    """
    Pedestrian Dead Reckoning processor.

    Accepts IMU samples one at a time via update().
    Internally maintains:
      - EMA-filtered acceleration magnitude and gyro-z
      - Gyro bias calibration (first CAL_WINDOW seconds)
      - Rolling 0.40 s window for adaptive step detection
      - Weinberg stride model with optional SVR hybrid blend
      - 2-D (x, y) dead reckoning position

    All algorithm parameters are locked — calibrated in Senior Design 1.
    """

    def __init__(self) -> None:
        # 2-D position and heading
        self.x: float = 0.0
        self.y: float = 0.0
        self.heading: float = 0.0  # radians, integrated from gz

        # EMA filter state
        self._a_mag_f: float | None = None
        self._gz_f:    float | None = None

        # Gyro bias calibration
        self._bias_collecting: bool  = True
        self._gyro_sum:         float = 0.0
        self._bias_count:       int   = 0
        self._gyro_bias:        float = 0.0

        # Rolling window buffers (time and EMA-filtered a_mag)
        self._buf_t: list[float] = []
        self._buf_a: list[float] = []

        # Step tracking
        self._last_step_t: float        = -np.inf
        self._step_count:  int          = 0
        self._step_features: list[np.ndarray] = []
        self._stride_pred:   list[float]      = []

        # Packet counter (step detection runs every other packet)
        self._pkt_count: int = 0

        # SVR model (loaded if available)
        self._model = self._load_model()

    # ── Model I/O ─────────────────────────────────────────────────────────────

    @staticmethod
    def _load_model():
        """Load persisted SVR pipeline if it exists."""
        if MODEL_PATH.exists():
            with open(MODEL_PATH, "rb") as f:
                return pickle.load(f)
        return None

    # ── Main update ───────────────────────────────────────────────────────────

    def update(
        self,
        ax: float, ay: float, az: float,
        gz: float,
        t: float,
        dt: float,
    ) -> dict:
        """
        Process one IMU sample and advance the PDR state machine.

        Args:
            ax, ay, az : accelerometer m/s² (already converted from raw with
                         factor 0.0011978149 applied by the BLE parser).
            gz         : gyroscope-z rad/s (converted with factor 0.0002663309).
            t          : elapsed time since device start, seconds.
            dt         : time since previous sample, seconds.

        Returns:
            dict with keys: x, y, heading_rad, step_count, total_distance
        """
        dt = max(float(dt), 1e-3)

        # ── 1. Gyro bias calibration ──────────────────────────────────────────
        if self._bias_collecting:
            self._gyro_sum  += gz
            self._bias_count += 1
            if t >= CAL_WINDOW:
                self._gyro_bias       = self._gyro_sum / self._bias_count
                self._bias_collecting = False
            gz_corrected = 0.0        # freeze heading during calibration
        else:
            gz_corrected = gz - self._gyro_bias

        # ── 2. EMA filter ────────────────────────────────────────────────────
        alpha = 1.0 - np.exp(-2.0 * np.pi * FC * dt)
        a_mag = float(np.sqrt(ax**2 + ay**2 + az**2))

        if self._a_mag_f is None:
            self._a_mag_f = a_mag
        self._a_mag_f += alpha * (a_mag - self._a_mag_f)

        if self._gz_f is None:
            self._gz_f = gz_corrected
        self._gz_f += alpha * (gz_corrected - self._gz_f)

        # ── 3. Heading integration ────────────────────────────────────────────
        self.heading += self._gz_f * dt

        # ── 4. Maintain rolling buffer ────────────────────────────────────────
        self._buf_t.append(t)
        self._buf_a.append(self._a_mag_f)
        cutoff = t - WIN_STEP
        while self._buf_t and self._buf_t[0] < cutoff:
            self._buf_t.pop(0)
            self._buf_a.pop(0)

        # ── 5. Step detection (every other packet) ────────────────────────────
        self._pkt_count += 1
        if self._pkt_count % 2 == 0 and len(self._buf_a) >= 2:
            buf = np.array(self._buf_a, dtype=np.float64)

            # False-step suppression — stationary guard
            if np.std(buf) < STAT_STD_TH:
                return self._state()

            # False-step suppression — near-gravity guard
            if abs(np.mean(buf) - 9.8) < GRAV_FLAT_TH:
                return self._state()

            a_max   = float(np.max(buf))
            a_min   = float(np.min(buf))
            swing   = a_max - a_min
            buf_med = float(np.median(buf))
            buf_std = float(np.std(buf))

            th_peak  = buf_med + 2.0 * buf_std
            th_swing = 0.9 * buf_std
            dt_step  = t - self._last_step_t

            if dt_step > MIN_STEP_DT and a_max > th_peak and swing > th_swing:
                self._last_step_t = t
                self._step_count  += 1

                # Histogram feature vector
                counts, _ = np.histogram(buf, bins=BIN_EDGES)
                hfeat = counts / max(float(counts.sum()), 1.0)

                # Stride estimation
                wein = K_WEIN * (swing ** P_WEIN)
                if self._model is not None:
                    try:
                        svr_raw = float(self._model.predict(hfeat.reshape(1, -1))[0])
                        svr_pred = float(np.clip(svr_raw, SVR_MIN, SVR_MAX))
                        stride  = 0.5 * wein + 0.5 * svr_pred
                    except Exception:
                        logger.exception("SVR predict failed — falling back to Weinberg")
                        stride = wein
                else:
                    stride = wein

                stride = float(np.clip(stride, MIN_STRIDE, MAX_STRIDE))

                self._stride_pred.append(stride)
                self._step_features.append(hfeat)

                # Dead reckoning
                self.x += stride * np.cos(self.heading)
                self.y += stride * np.sin(self.heading)

        return self._state()

    # ── State snapshot ────────────────────────────────────────────────────────

    def _state(self) -> dict:
        return {
            "x":              self.x,
            "y":              self.y,
            "heading_rad":    self.heading,
            "step_count":     self._step_count,
            "total_distance": float(sum(self._stride_pred)),
        }

    # ── ZUPT ──────────────────────────────────────────────────────────────────

    def apply_zupt(self) -> None:
        """
        Zero-Velocity Update.
        ZUPT velocity-zeroing is applied to the EKF externally by the
        coordinator (ekf.apply_zupt()).  This method is a no-op hook for
        PDR-level bookkeeping if needed in future.
        """
        pass

    # ── Training data / model retraining ──────────────────────────────────────

    def save_training_data(self, d_true: float) -> None:
        """
        Append this walk's histogram features + true stride label to the
        training dataset at TRAIN_PATH.

        Args:
            d_true: ground-truth total walk distance in metres, measured
                    externally (e.g. tape measure / reference system).
        """
        n = len(self._step_features)
        if n == 0:
            return
        stride_true = d_true / n

        existing: dict = {"X": [], "y": []}
        if TRAIN_PATH.exists():
            with open(TRAIN_PATH, encoding="utf-8") as f:
                existing = json.load(f)

        existing["X"].extend([feat.tolist() for feat in self._step_features])
        existing["y"].extend([stride_true] * n)

        with open(TRAIN_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f)

    @staticmethod
    def retrain_model() -> None:
        """
        Retrain the SVR pipeline on all accumulated training data and
        persist the new model to MODEL_PATH (stride_svr.pkl).

        Uses:
            sklearn SVR with RBF kernel, γ='scale'
            StandardScaler preprocessing pipeline
        Raises:
            FileNotFoundError: if TRAIN_PATH does not exist.
        """
        if not TRAIN_PATH.exists():
            raise FileNotFoundError(f"No training data at {TRAIN_PATH}")

        with open(TRAIN_PATH, encoding="utf-8") as f:
            data = json.load(f)

        X = np.array(data["X"], dtype=np.float64)
        y = np.array(data["y"],  dtype=np.float64)

        mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
        X, y = X[mask], y[mask]
        if len(y) == 0:
            raise ValueError("No finite training samples after filtering.")

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("svr",    SVR(kernel="rbf", gamma="scale")),
        ])
        model.fit(X, y)

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        logger.info("PDR SVR model retrained on %d samples → %s", len(y), MODEL_PATH)
