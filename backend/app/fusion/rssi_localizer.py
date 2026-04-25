"""
backend/app/fusion/rssi_localizer.py

RSSI-based position estimator — Python port of LocalizationEngine.kt.

Pipeline:
  1. Kalman-smooth RSSI per AP prefix (Q=2.0, R=9.0).
  2. Log-distance path loss → distance estimate, clamped [0.3, 80] m.
  3. Sort anchors nearest-first; reject outliers (> 2σ from mean distance).
  4. Limit to top-5 anchors (more anchors ≠ better — bad geometry degrades solver).
  5. ≥3 anchors → Gauss-Newton nonlinear multilateration; bounds-check result;
       fall back to weighted centroid (top-3) if it diverges.
     2 anchors  → weighted centroid.
     1 anchor   → return that AP's position directly.
  6. Temporally smooth the output (α = 0.6, stored in kalman_states["__pos__"]).
  7. Returns {"x", "y", "anchor_count", "avg_rssi_error"} or None.
"""

import math
from dataclasses import dataclass, field


# ── Per-AP Kalman smoother ────────────────────────────────────────────────────

@dataclass
class KalmanState:
    x: float          # estimated RSSI (dBm)
    p: float = 10.0   # error covariance (start uncertain)
    Q: float = 2.0    # process noise — RSSI can drift ~√2 dBm per step
    R: float = 9.0    # measurement noise — empirical indoor std ≈ 3 dBm

    def update(self, z: float) -> float:
        """Kalman predict + update. Returns the smoothed RSSI estimate."""
        p_pred = self.p + self.Q
        k = p_pred / (p_pred + self.R)
        self.x = self.x + k * (z - self.x)
        self.p = (1.0 - k) * p_pred
        return self.x


_SMOOTHING_ALPHA = 0.6   # temporal EMA weight for final position


# ── Distance estimation ───────────────────────────────────────────────────────

def estimate_distance(rssi_ref: float, path_loss_n: float, rssi_smoothed: float) -> float:
    """Log-distance: dist = 10^((rssi_ref − rssi) / (10·n)), clamped [0.3, 80] m."""
    exponent = (rssi_ref - rssi_smoothed) / (10.0 * path_loss_n)
    return max(0.3, min(80.0, 10.0 ** exponent))


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _weighted_centroid(anchors: list) -> tuple[float, float]:
    """w = 1/(dist + 0.5) — linear weighting avoids the AP-pull effect."""
    weights = [1.0 / (d + 0.5) for _, d in anchors]
    w_sum = sum(weights)
    x = sum(w * ap["x"] for (ap, _), w in zip(anchors, weights)) / w_sum
    y = sum(w * ap["y"] for (ap, _), w in zip(anchors, weights)) / w_sum
    return x, y


def _is_within_bounds(pos: tuple[float, float], anchors: list) -> bool:
    """Reject result if it falls > 30% outside the AP cluster bounding box."""
    min_x = min(ap["x"] for ap, _ in anchors)
    max_x = max(ap["x"] for ap, _ in anchors)
    min_y = min(ap["y"] for ap, _ in anchors)
    max_y = max(ap["y"] for ap, _ in anchors)
    mx = max(max_x - min_x, 5.0) * 0.30 + 2.0
    my = max(max_y - min_y, 5.0) * 0.30 + 2.0
    return ((min_x - mx) <= pos[0] <= (max_x + mx) and
            (min_y - my) <= pos[1] <= (max_y + my))


def _multilateral_ls(anchors: list) -> tuple[float, float] | None:
    """
    Gauss-Newton nonlinear multilateration (up to 10 iterations, weighted).

    Initialises at the centroid of anchor positions and iterates:
        x_(k+1) = x_k − (JᵀWJ)⁻¹ Jᵀ W r
    where J is the Jacobian of Euclidean distances, W = diag(1/(d+0.5)),
    and r = dist(x_k, AP_i) − d_i.

    Returns None only if the Hessian is singular at the first step.
    """
    x = sum(ap["x"] for ap, _ in anchors) / len(anchors)
    y = sum(ap["y"] for ap, _ in anchors) / len(anchors)

    for _ in range(10):
        jtj00 = jtj01 = jtj11 = 0.0
        jtr0  = jtr1  = 0.0

        for ap, d in anchors:
            dx   = x - ap["x"]
            dy   = y - ap["y"]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 1e-6:
                dist = 1e-6
            w    = 1.0 / (d + 0.5)
            jx   = dx / dist
            jy   = dy / dist
            res  = dist - d

            jtj00 += w * jx * jx
            jtj01 += w * jx * jy
            jtj11 += w * jy * jy
            jtr0  += w * jx * res
            jtr1  += w * jy * res

        det = jtj00 * jtj11 - jtj01 * jtj01
        if abs(det) < 1e-8:
            return None

        dx_upd = (jtj11 * jtr0 - jtj01 * jtr1) / det
        dy_upd = (jtj00 * jtr1 - jtj01 * jtr0) / det
        x -= dx_upd
        y -= dy_upd

        if math.sqrt(dx_upd * dx_upd + dy_upd * dy_upd) < 1e-3:
            break

    return x, y


# ── Main entry point ──────────────────────────────────────────────────────────

def _prefix(bssid: str) -> str:
    """First 5 octets — identifies a physical radio across its virtual SSIDs."""
    return bssid.lower().rsplit(":", 1)[0]


def localize(
    scan: list[dict],       # [{"bssid": str, "rssi": int|float}, ...]
    known_aps: list[dict],  # [{"bssid", "rssi_ref", "path_loss_n", "x", "y"}, ...]
    kalman_states: dict,    # {prefix → KalmanState, "__pos__" → (x,y)}; mutated in place
) -> dict | None:
    """
    Estimate device position from a Wi-Fi scan.

    BSSIDs are collapsed by first 5 octets (physical AP); strongest RSSI wins.
    Temporal smoothing state is stored in kalman_states["__pos__"] alongside
    the per-AP Kalman states so no additional argument is needed.
    """
    # ── Collapse by physical AP prefix ───────────────────────────────────────
    scan_by_prefix: dict[str, float] = {}
    for entry in scan:
        p    = _prefix(entry["bssid"])
        rssi = float(entry["rssi"])
        if p not in scan_by_prefix or rssi > scan_by_prefix[p]:
            scan_by_prefix[p] = rssi

    known_by_prefix: dict[str, dict] = {}
    for ap in known_aps:
        known_by_prefix.setdefault(_prefix(ap["bssid"]), ap)

    # ── Kalman-smooth RSSI and estimate distances ─────────────────────────────
    anchors: list[tuple[dict, float]] = []
    for prefix, ap in known_by_prefix.items():
        if prefix not in scan_by_prefix:
            continue
        raw_rssi = scan_by_prefix[prefix]
        if prefix not in kalman_states:
            kalman_states[prefix] = KalmanState(x=raw_rssi)
        smoothed = kalman_states[prefix].update(raw_rssi)
        dist = estimate_distance(ap["rssi_ref"], ap["path_loss_n"], smoothed)
        anchors.append((ap, dist))

    if not anchors:
        return None

    # ── Sort nearest-first ────────────────────────────────────────────────────
    anchors.sort(key=lambda t: t[1])

    # ── Outlier rejection (> 2σ from mean distance) ───────────────────────────
    if len(anchors) > 3:
        mean = sum(d for _, d in anchors) / len(anchors)
        std  = math.sqrt(sum((d - mean) ** 2 for _, d in anchors) / len(anchors))
        filtered = [a for a in anchors if abs(a[1] - mean) <= 2.0 * std]
        if filtered:          # keep originals if all were rejected (shouldn't happen)
            anchors = filtered

    # ── Limit to top-5 strongest (nearest) anchors ───────────────────────────
    anchors = anchors[:5]

    # ── Quality metric ────────────────────────────────────────────────────────
    avg_error = sum(
        abs(scan_by_prefix[_prefix(ap["bssid"])] -
            (ap["rssi_ref"] - 10.0 * ap["path_loss_n"] * math.log10(max(dist, 0.001))))
        for ap, dist in anchors
    ) / len(anchors)

    # ── Position estimate ─────────────────────────────────────────────────────
    if len(anchors) == 1:
        ap, _ = anchors[0]
        x, y  = ap["x"], ap["y"]
    elif len(anchors) == 2:
        x, y = _weighted_centroid(anchors)
    else:
        ls = _multilateral_ls(anchors)
        if ls is not None and _is_within_bounds(ls, anchors):
            x, y = ls
        else:
            x, y = _weighted_centroid(anchors[:3])

    # ── Temporal smoothing (EMA per device, stored in kalman_states) ──────────
    last = kalman_states.get("__pos__")
    if last is not None:
        x = _SMOOTHING_ALPHA * x + (1.0 - _SMOOTHING_ALPHA) * last[0]
        y = _SMOOTHING_ALPHA * y + (1.0 - _SMOOTHING_ALPHA) * last[1]
    kalman_states["__pos__"] = (x, y)

    return {
        "x":              round(x, 3),
        "y":              round(y, 3),
        "anchor_count":   len(anchors),
        "avg_rssi_error": round(avg_error, 2),
    }
