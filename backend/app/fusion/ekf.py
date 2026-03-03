"""
backend/app/fusion/ekf.py
Extended Kalman Filter — TASK-12

4-state EKF: [px, py, vx, vy]
IMU-driven predict; Bayesian-MAP-driven update.
All matrix constants are locked by workspace rules.

Person C owns this file.
"""

from __future__ import annotations

import numpy as np


class ExtendedKalmanFilter:
    """
    4-state linear Kalman filter for 2-D position + velocity: [px, py, vx, vy].

    Although named "Extended" to match the project architecture document, the
    measurement and motion models are both linear for this implementation —
    the EKF predict/update equations reduce to the standard Kalman form.

    Constants (locked — do not change without user confirmation):
        P₀ = diag([25, 25, 4, 4])
        Q  = diag([0.01, 0.01, 0.1, 0.1])
        R_normal   = diag([9, 9])     (≥2 APs)
        R_degraded = diag([18, 18])   (<2 APs)
        Divergence reset: |pos_EKF − pos_Bayes| > 10 m for > 5 cycles
    """

    def __init__(self, initial_pos: tuple[float, float] = (0.0, 0.0)):
        px, py = float(initial_pos[0]), float(initial_pos[1])
        self.x = np.array([px, py, 0.0, 0.0])           # state
        self.P = np.diag([25.0, 25.0, 4.0, 4.0])        # covariance
        self.Q = np.diag([0.01, 0.01, 0.1, 0.1])        # process noise
        self.R_normal   = np.diag([9.0,  9.0 ])          # measurement noise (normal)
        self.R_degraded = np.diag([18.0, 18.0])          # measurement noise (degraded)

    # ── Predict step ───────────────────────────────────────────────────────────

    def predict(self, ax: float, ay: float, dt: float) -> None:
        """
        IMU-driven constant-acceleration predict step.

        State transition:
            px' = px + vx·dt + 0.5·ax·dt²
            py' = py + vy·dt + 0.5·ay·dt²
            vx' = vx + ax·dt
            vy' = vy + ay·dt

        Args:
            ax, ay: accelerometer readings in m/s² (corridor frame).
            dt:     elapsed time since last predict, in seconds.
        """
        dt = max(float(dt), 1e-6)
        F = np.array([
            [1.0, 0.0,  dt, 0.0],
            [0.0, 1.0, 0.0,  dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
        B = np.array([
            [0.5 * dt**2, 0.0        ],
            [0.0,         0.5 * dt**2],
            [dt,          0.0        ],
            [0.0,          dt        ],
        ])
        self.x = F @ self.x + B @ np.array([float(ax), float(ay)])
        self.P = F @ self.P @ F.T + self.Q

    # ── Update step ────────────────────────────────────────────────────────────

    def update(self, pos_bayes: tuple[float, float], degraded: bool = False) -> None:
        """
        Bayesian-MAP-driven measurement update.

        Measurement model: z = [px, py]  →  H = [[1,0,0,0],[0,1,0,0]]

        Args:
            pos_bayes: MAP position (x_m, y_m) from the Bayesian grid.
            degraded:  True when only 1 AP contributed → use R_degraded.
        """
        H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])
        R = self.R_degraded if degraded else self.R_normal
        z = np.array([float(pos_bayes[0]), float(pos_bayes[1])])

        y_innov = z - H @ self.x
        S       = H @ self.P @ H.T + R
        K       = self.P @ H.T @ np.linalg.inv(S)

        self.x = self.x + K @ y_innov
        self.P = (np.eye(4) - K @ H) @ self.P

    # ── Divergence / reset ─────────────────────────────────────────────────────

    def check_divergence(self, pos_bayes: tuple[float, float]) -> bool:
        """Return True if EKF position is > 10 m from the Bayesian MAP estimate."""
        diff = self.x[:2] - np.array([float(pos_bayes[0]), float(pos_bayes[1])])
        return bool(np.linalg.norm(diff) > 10.0)

    def reset_from_bayes(self, pos_bayes: tuple[float, float]) -> None:
        """Reset state to Bayesian MAP position, zero velocity, P = P₀."""
        self.x = np.array([float(pos_bayes[0]), float(pos_bayes[1]), 0.0, 0.0])
        self.P = np.diag([25.0, 25.0, 4.0, 4.0])

    # ── ZUPT ──────────────────────────────────────────────────────────────────

    def apply_zupt(self) -> None:
        """Zero-Velocity Update: set vx = vy = 0 when device is stationary."""
        self.x[2] = 0.0
        self.x[3] = 0.0

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_position(self) -> tuple[float, float]:
        """Return current estimated position as (x_m, y_m)."""
        return (float(self.x[0]), float(self.x[1]))

    def get_state(self) -> np.ndarray:
        """Return full 4-state vector [px, py, vx, vy] (copy)."""
        return self.x.copy()
