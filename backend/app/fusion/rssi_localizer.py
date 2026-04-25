"""
backend/app/fusion/rssi_localizer.py

RSSI-based position estimator.

Pipeline:
  1. Adaptive Kalman-smooth RSSI per AP prefix: Q rises to 6.0 when residual > 5 dBm
     (moving) and drops to 1.0 when stable — fast reaction + noise suppression.
  2. Log-distance path loss → distance estimate, clamped [0.3, 80] m.
  3. Sort by (distance asc, rssi desc) — prefer close AND strong.
  4. Reject outliers > 2σ from mean distance; limit to top-5 anchors.
  5. Snap directly to an AP when its estimated distance < 2 m (fast bootstrap).
  6. ≥3 anchors → Gauss-Newton nonlinear multilateration; bounds-check result;
       fall back to weighted centroid (top-3) if it diverges.
     2 anchors  → weighted centroid.
     1 anchor   → that AP's position.
  7. Drop result when avg_rssi_error > 10 dB (unreliable scan).
  8. Adaptive EMA smoothing: α=0.85 when movement > 2 m, α=0.5 when stationary.
     State stored in kalman_states["__pos__"] (per-device, no extra argument needed).
  9. Returns {"x", "y", "anchor_count", "avg_rssi_error"} or None.
"""

import math
from dataclasses import dataclass


# ── Per-AP adaptive Kalman smoother ──────────────────────────────────────────

@dataclass
class KalmanState:
    x: float          # estimated RSSI (dBm)
    p: float = 10.0   # error covariance (start uncertain)
    R: float = 9.0    # measurement noise — empirical indoor std ≈ 3 dBm

    def update(self, z: float) -> float:
        """Adaptive Kalman: raise Q when RSSI jumps (moving), lower when stable."""
        residual = abs(z - self.x)
        q = 6.0 if residual > 5.0 else 1.0   # fast adapt vs. noise suppress
        p_pred = self.p + q
        k = p_pred / (p_pred + self.R)
        self.x = self.x + k * (z - self.x)
        self.p = (1.0 - k) * p_pred
        return self.x


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
    Initialises at the centroid; iterates x -= (JᵀWJ)⁻¹ Jᵀ W r.
    Returns None only if the Hessian is singular.
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
    BSSIDs collapsed by first 5 octets; strongest RSSI per physical AP wins.
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

    # ── Adaptive Kalman-smooth RSSI and estimate distances ────────────────────
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

    # ── Sort: nearest first; break ties by strongest raw RSSI ────────────────
    anchors.sort(key=lambda t: (t[1], -scan_by_prefix[_prefix(t[0]["bssid"])]))

    # ── Outlier rejection (> 2σ from mean distance) ───────────────────────────
    if len(anchors) > 3:
        mean = sum(d for _, d in anchors) / len(anchors)
        std  = math.sqrt(sum((d - mean) ** 2 for _, d in anchors) / len(anchors))
        filtered = [a for a in anchors if abs(a[1] - mean) <= 2.0 * std]
        if filtered:
            anchors = filtered

    # ── Limit to top-5 ───────────────────────────────────────────────────────
    anchors = anchors[:5]

    # ── Quality metric ────────────────────────────────────────────────────────
    avg_error = sum(
        abs(scan_by_prefix[_prefix(ap["bssid"])] -
            (ap["rssi_ref"] - 10.0 * ap["path_loss_n"] * math.log10(max(dist, 0.001))))
        for ap, dist in anchors
    ) / len(anchors)

    # ── Drop unreliable scan ──────────────────────────────────────────────────
    if avg_error > 10.0:
        return None

    # ── Fast bootstrap: snap when clearly next to one AP (dist < 2 m) ────────
    strongest = max(anchors, key=lambda a: scan_by_prefix[_prefix(a[0]["bssid"])])
    if strongest[1] < 2.0:
        ap = strongest[0]
        x, y = ap["x"], ap["y"]
        last = kalman_states.get("__pos__")
        if last is not None:
            x = 0.85 * x + 0.15 * last[0]
            y = 0.85 * y + 0.15 * last[1]
        kalman_states["__pos__"] = (x, y)
        return {"x": round(x, 3), "y": round(y, 3),
                "anchor_count": len(anchors), "avg_rssi_error": round(avg_error, 2)}

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

    # ── Adaptive temporal smoothing ───────────────────────────────────────────
    last = kalman_states.get("__pos__")
    if last is not None:
        movement = math.sqrt((x - last[0]) ** 2 + (y - last[1]) ** 2)
        alpha = 0.85 if movement > 2.0 else 0.5
        x = alpha * x + (1.0 - alpha) * last[0]
        y = alpha * y + (1.0 - alpha) * last[1]
    kalman_states["__pos__"] = (x, y)

    return {
        "x":              round(x, 3),
        "y":              round(y, 3),
        "anchor_count":   len(anchors),
        "avg_rssi_error": round(avg_error, 2),
    }
