"""
backend/app/fusion/observation_model.py
Observation model — TASK-10

Implements p(y | x) from Horn (2022) "Indoor Localization using Uncooperative
Wi-Fi Access Points".

All parameter values are locked by workspace rules — do not change.

Person C owns this file.
"""

from __future__ import annotations

import numpy as np

# ── Locked constants (Horn 2022) ──────────────────────────────────────────────
X0      = 5.5    # m   — minimum approach distance (AP mounting height)
A       = 2.23   # amplitude of mean deviation
ALPHA   = 0.043  # m⁻¹ — decay rate of mean deviation
SIGMA0  = 4.0    # m   — baseline standard deviation
SIGMA_M = 0.55   # slope of std increase with distance
BETA    = 0.015  # m⁻¹ — decay rate of standard deviation


def mu(x: float) -> float:
    """
    Expected RTT-derived distance measurement given true distance x (metres).

    E[y | x] = x · (1 + A · α · (x − x₀) · e^{−α (x − x₀)})
    """
    return x * (1.0 + A * ALPHA * (x - X0) * np.exp(-ALPHA * (x - X0)))


def sigma(x: float) -> float:
    """
    Standard deviation of RTT-derived distance given true distance x (metres).

    σ(x) = σ₀ + σ_m · (x − x₀) · e^{−β (x − x₀)}
    """
    return SIGMA0 + SIGMA_M * (x - X0) * np.exp(-BETA * (x - X0))


def p_observation(y: float, x: float) -> float:
    """
    p(y | x) — likelihood of measuring RTT distance y given true distance x.

    Both y and x are in metres.  x is clamped to x₀ (AP mounting height)
    because the model is only valid for x ≥ x₀.  Sigma is clamped to 0.1
    to avoid division-by-zero for degenerate inputs.

    Args:
        y: observed (corrected) RTT distance in metres.
        x: true distance from cell centre to AP in metres.

    Returns:
        Likelihood value (non-negative float).
    """
    x_c = max(float(x), X0)
    s   = max(float(sigma(x_c)), 0.1)
    m   = float(mu(x_c))
    return (1.0 / (np.sqrt(2.0 * np.pi) * s)) * np.exp(-0.5 * ((y - m) / s) ** 2)
