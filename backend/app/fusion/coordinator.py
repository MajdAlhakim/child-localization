"""
Fusion coordinator — async event loop that drives the full localization pipeline.

Person C owns this file.
publish_position() stub is committed early so Person D (TASK-14 WebSocket
broadcaster) can depend on its interface immediately.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ── publish_position stub ────────────────────────────────────────────────────
# Person D (TASK-14) will register the real implementation via
# set_publisher().  Until then the stub silently drops the message.

_publisher = None


def set_publisher(fn) -> None:
    """Register the real publish_position coroutine (called by Person D)."""
    global _publisher
    _publisher = fn


async def publish_position(
    device_id: str,
    position: tuple[float, float],
    source: str,
    confidence: float,
    active_aps: int,
    mode: str,
) -> None:
    """
    Broadcast a fused position update to all WebSocket subscribers.

    Args:
        device_id:   UUID string identifying the tracked child device.
        position:    (x_m, y_m) in corridor coordinate frame.
        source:      One of "fused", "ekf_only", "bayesian_only", "pdr_only".
        confidence:  Scalar in [0, 1] representing estimate reliability.
        active_aps:  Number of APs that contributed RTT measurements this cycle.
        mode:        Operating mode: "normal" | "degraded" | "imu_only" | "disconnected".
    """
    if _publisher is not None:
        await _publisher(
            device_id=device_id,
            position=position,
            source=source,
            confidence=confidence,
            active_aps=active_aps,
            mode=mode,
        )
    else:
        logger.debug(
            "publish_position: no publisher registered — dropping "
            "device=%s pos=%s mode=%s", device_id, position, mode
        )


# ── FusionCoordinator ─────────────────────────────────────────────────────────

class FusionCoordinator:
    """
    Async fusion coordinator.

    Wires together:
      EKF (ekf.py) ← IMU predict + Bayesian MAP update
      PDR (pdr.py) ← IMU dead reckoning
      BayesianGrid (bayesian_grid.py) ← RTT likelihood update
      publish_position() ← WebSocket broadcast (TASK-14)

    Operating modes (per workspace rules §11):
      normal       — ≥2 APs, IMU active   → predict + update R_normal
      degraded     — 1 AP only            → predict + update R_degraded
      imu_only     — 0 APs               → predict only
      disconnected — no data > 5 s       → suspended
    """

    ZUPT_ACCEL_THRESHOLD = 0.05   # m/s²  — magnitude threshold for ZUPT
    ZUPT_DURATION        = 2.0    # s     — must be stationary this long
    DISCONNECT_TIMEOUT   = 5.0    # s     — no data → disconnected
    DIVERGENCE_MAX_CYCLES = 5     # EKF divergence reset after this many cycles

    def __init__(
        self,
        device_id: str,
        ekf,         # ExtendedKalmanFilter
        grid,        # BayesianGrid
        pdr,         # PDRProcessor
        offset_fn=None,   # Callable[[str, str, float], float] (bssid, band, d_raw) → d_corrected
        ap_positions: dict[str, tuple[float, float]] | None = None,
    ):
        self.device_id = device_id
        self.ekf = ekf
        self.grid = grid
        self.pdr = pdr
        self.offset_fn = offset_fn or (lambda bssid, band, d: d)
        self.ap_positions: dict[str, tuple[float, float]] = ap_positions or {}

        self._last_data_t: float = time.monotonic()
        self._zupt_start: float | None = None
        self._divergence_count: int = 0
        self._mode: str = "disconnected"

    # ── IMU data path ─────────────────────────────────────────────────────────

    async def on_imu(
        self,
        ax: float, ay: float, az: float,
        gz: float,
        t: float,
        dt: float,
    ) -> None:
        """
        Called whenever a parsed IMU frame arrives.

        ax, ay, az : accelerometer m/s² (already converted from raw)
        gz         : gyroscope-z rad/s  (already converted from raw)
        t          : device elapsed time in seconds
        dt         : time since last IMU sample in seconds
        """
        self._last_data_t = time.monotonic()

        # EKF predict
        self.ekf.predict(ax, ay, dt)

        # PDR update
        self.pdr.update(ax, ay, az, gz, t, dt)

        # ZUPT guard
        a_mag = float(np.sqrt(ax**2 + ay**2 + az**2))
        if a_mag < self.ZUPT_ACCEL_THRESHOLD:
            if self._zupt_start is None:
                self._zupt_start = t
            elif (t - self._zupt_start) > self.ZUPT_DURATION:
                self.ekf.apply_zupt()
        else:
            self._zupt_start = None

        await self._publish_current()

    # ── RTT data path ─────────────────────────────────────────────────────────

    async def on_rtt(
        self,
        measurements: list[dict[str, Any]],
    ) -> None:
        """
        Called whenever a parsed RTT frame arrives.

        measurements: list of dicts with keys:
            bssid       str
            d_raw_mean  float  (metres)
            d_raw_std   float
            rssi        int
            band        str    "2.4GHz" | "5GHz"
        """
        self._last_data_t = time.monotonic()

        active_aps = 0
        for m in measurements:
            bssid = m["bssid"]
            band  = m["band"]
            d_raw = m["d_raw_mean"]

            if bssid not in self.ap_positions:
                continue  # unknown AP — skip (OQ-03 unresolved)

            d_corr = self.offset_fn(bssid, band, d_raw)
            ap_xy  = self.ap_positions[bssid]
            self.grid.update(d_corr, ap_xy)
            active_aps += 1

        if active_aps > 0:
            map_pos = self.grid.map_position()
            degraded = active_aps < 2

            # Divergence tracking
            if self.ekf.check_divergence(map_pos):
                self._divergence_count += 1
                if self._divergence_count > self.DIVERGENCE_MAX_CYCLES:
                    logger.warning(
                        "EKF diverged for %d cycles — resetting from Bayesian MAP",
                        self._divergence_count,
                    )
                    self.ekf.reset_from_bayes(map_pos)
                    self._divergence_count = 0
            else:
                self._divergence_count = 0

            self.ekf.update(map_pos, degraded=degraded)

        await self._publish_current()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _current_mode(self, active_aps: int) -> str:
        elapsed = time.monotonic() - self._last_data_t
        if elapsed > self.DISCONNECT_TIMEOUT:
            return "disconnected"
        if active_aps >= 2:
            return "normal"
        if active_aps == 1:
            return "degraded"
        return "imu_only"

    async def _publish_current(self, active_aps: int = 0) -> None:
        pos = self.ekf.get_position()
        mode = self._current_mode(active_aps)
        # Confidence: simple heuristic from trace of P (lower trace → higher conf)
        p_trace = float(np.trace(self.ekf.P[:2, :2]))
        confidence = float(np.clip(1.0 - p_trace / 50.0, 0.0, 1.0))
        await publish_position(
            device_id=self.device_id,
            position=pos,
            source="fused",
            confidence=confidence,
            active_aps=active_aps,
            mode=mode,
        )
