"""
backend/app/fusion/rssi_localizer.py

RSSI-based position estimator — Python port of LocalizationEngine.kt.

Pipeline:
  1. Kalman-smooth RSSI per AP (Q=2.0, R=9.0) to suppress measurement jitter.
  2. Log-distance path loss → distance estimate per AP, clamped [0.3, 80] m.
  3. Sort anchors by ascending distance (nearest first = best WRLS reference row).
  4. ≥3 anchors → WRLS multilateration; validate with bounds check;
       fall back to weighted centroid (top-3) if LS diverges.
     2 anchors  → weighted centroid.
     1 anchor   → return that AP's position directly.
  5. Returns {"x", "y", "anchor_count", "avg_rssi_error"} or None.
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


# ── Distance estimation ───────────────────────────────────────────────────────

def estimate_distance(rssi_ref: float, path_loss_n: float, rssi_smoothed: float) -> float:
    """
    Log-distance path loss: dist = 10^((rssi_ref − rssi) / (10·n)).
    Clamped to [0.3 m, 80 m] — below 0.3 is physically unrealistic indoors.
    """
    exponent = (rssi_ref - rssi_smoothed) / (10.0 * path_loss_n)
    return max(0.3, min(80.0, 10.0 ** exponent))


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _weighted_centroid(anchors: list) -> tuple[float, float]:
    """Weight = 1/(dist + 0.5) to avoid div/0. Linear (not squared) to avoid pull effect."""
    weights = [1.0 / (d + 0.5) for _, d in anchors]
    w_sum = sum(weights)
    x = sum(w * ap["x"] for (ap, _), w in zip(anchors, weights)) / w_sum
    y = sum(w * ap["y"] for (ap, _), w in zip(anchors, weights)) / w_sum
    return x, y


def _is_within_bounds(pos: tuple[float, float], anchors: list) -> bool:
    """Reject WRLS result if it falls more than 30% outside the AP cluster bounding box."""
    min_x = min(ap["x"] for ap, _ in anchors)
    max_x = max(ap["x"] for ap, _ in anchors)
    min_y = min(ap["y"] for ap, _ in anchors)
    max_y = max(ap["y"] for ap, _ in anchors)
    mx = max(max_x - min_x, 5.0) * 0.30 + 2.0   # 30% margin + 2m absolute minimum
    my = max(max_y - min_y, 5.0) * 0.30 + 2.0
    return ((min_x - mx) <= pos[0] <= (max_x + mx) and
            (min_y - my) <= pos[1] <= (max_y + my))


def _multilateral_ls(anchors: list) -> tuple[float, float] | None:
    """
    Weighted least-squares multilateration (WRLS).

    Classic linearisation: subtract anchor-0 from all rows to eliminate X²+Y² terms,
    giving a linear system Ax = b. Rows are weighted by w_i = 1/(dist_i + 0.5)
    so closer APs have more influence.

    Solves the 2×2 normal equations: (WA)ᵀ(WA) x = (WA)ᵀ(Wb).
    Returns None if the matrix is (near-)singular.
    """
    ap0, d0 = anchors[0]
    x0, y0 = ap0["x"], ap0["y"]

    rows: list[tuple[float, float, float]] = []
    for ap, di in anchors[1:]:
        w  = 1.0 / (di + 0.5)
        a  = 2.0 * (ap["x"] - x0)
        b  = 2.0 * (ap["y"] - y0)
        c  = di*di - d0*d0 - ap["x"]**2 + x0**2 - ap["y"]**2 + y0**2
        rows.append((w * a, w * b, w * c))

    ata00 = ata01 = ata11 = atb0 = atb1 = 0.0
    for wa, wb, wc in rows:
        ata00 += wa * wa
        ata01 += wa * wb
        ata11 += wb * wb
        atb0  += wa * wc
        atb1  += wb * wc

    det = ata00 * ata11 - ata01 * ata01
    if abs(det) < 1e-8:
        return None   # singular — collinear APs or duplicates

    x = (ata11 * atb0 - ata01 * atb1) / det
    y = (ata00 * atb1 - ata01 * atb0) / det
    return x, y


# ── Main entry point ──────────────────────────────────────────────────────────

def localize(
    scan: list[dict],       # [{"bssid": str, "rssi": int|float}, ...]
    known_aps: list[dict],  # [{"bssid", "rssi_ref", "path_loss_n", "x", "y"}, ...]
    kalman_states: dict,    # {bssid_lower → KalmanState}; mutated in place
) -> dict | None:
    """
    Estimate device position from a Wi-Fi scan.

    Returns {"x", "y", "anchor_count", "avg_rssi_error"} or None if no APs match.
    The caller is responsible for persisting kalman_states between calls.
    """
    scan_map: dict[str, float] = {
        entry["bssid"].lower(): float(entry["rssi"]) for entry in scan
    }

    # Step 1: match scan to known APs, apply Kalman smoothing, estimate distances
    anchors: list[tuple[dict, float]] = []
    for ap in known_aps:
        bssid = ap["bssid"].lower()
        if bssid not in scan_map:
            continue
        raw_rssi = scan_map[bssid]
        if bssid not in kalman_states:
            kalman_states[bssid] = KalmanState(x=raw_rssi)
        smoothed = kalman_states[bssid].update(raw_rssi)
        dist = estimate_distance(ap["rssi_ref"], ap["path_loss_n"], smoothed)
        anchors.append((ap, dist))

    if not anchors:
        return None

    # Step 2: sort nearest-first (best WRLS linearisation row first)
    anchors.sort(key=lambda t: t[1])

    # Step 3: average |observed − model| RSSI as a quality metric
    avg_error = sum(
        abs(scan_map[ap["bssid"].lower()] -
            (ap["rssi_ref"] - 10.0 * ap["path_loss_n"] * math.log10(max(dist, 0.001))))
        for ap, dist in anchors
    ) / len(anchors)

    # Step 4: position estimate
    if len(anchors) == 1:
        ap, _ = anchors[0]
        x, y = ap["x"], ap["y"]
    elif len(anchors) == 2:
        x, y = _weighted_centroid(anchors)
    else:
        ls = _multilateral_ls(anchors)
        if ls is not None and _is_within_bounds(ls, anchors):
            x, y = ls
        else:
            # LS diverged — fall back to centroid using top-3 nearest anchors
            x, y = _weighted_centroid(anchors[:3])

    return {
        "x":              round(x, 3),
        "y":              round(y, 3),
        "anchor_count":   len(anchors),
        "avg_rssi_error": round(avg_error, 2),
    }
