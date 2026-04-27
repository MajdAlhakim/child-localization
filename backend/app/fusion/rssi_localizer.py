"""
backend/app/fusion/rssi_localizer.py

RSSI-based position estimator optimized for 2.4GHz.

Pipeline:
  1. Adaptive Kalman per AP: Asymmetric Q to handle body-shadowing vs real movement.
  2. Drop anchors with raw RSSI < -90 dBm.
  3. Log-distance path loss → distance, clamped [0.3, 80] m.
  4. Sort by (distance asc, rssi desc); reject outliers > 2σ; top-5 only.
  5. Drop scan when avg_rssi_error > 20 dBm (calculated via Kalman residual).
  6. Snap to AP only when RSSI > -40 dBm (unmistakably close).
  7. ≥3 anchors → Inverse-square weighted centroid; fallback to top-3 if out of bounds.
     2 anchors → centroid.  1 anchor → None (distance only, no position).
  8. Three-zone adaptive EMA:
       movement < 1 m  → α=0.15  (stationary — highly sticky)
       movement 1–4 m  → α=0.60  (walking)
       movement > 4 m  → α=0.80  (fast) + capped at 6 m/scan
     State stored in kalman_states["__pos__"].
  9. Returns {"x", "y", "anchor_count", "avg_rssi_error"} or None.
"""

import math
import time
from dataclasses import dataclass


# ── Per-AP adaptive Kalman smoother ──────────────────────────────────────────

@dataclass
class KalmanState:
    x: float          # estimated RSSI (dBm)
    p: float = 10.0   # error covariance (start uncertain)
    R: float = 12.0   # measurement noise — raised to suppress stationary jitter

    def update(self, z: float) -> float:
        """Asymmetric Q: trust signal increases (movement), distrust sudden drops (blockage)."""
        residual = z - self.x
        
        if residual > 5.0:
            q = 3.0   # Signal got stronger suddenly: tag likely moved towards AP
        elif residual < -10.0:
            q = 5.0   # Signal dropped suddenly: human blockage (stay sticky)
        else:
            q = 1.0   # Stable / minor noise
            
        p_pred = self.p + q
        k = p_pred / (p_pred + self.R)
        self.x = self.x + k * residual
        self.p = (1.0 - k) * p_pred
        return self.x


_MAX_JUMP_M     = 6.0   # hard cap on position change per scan (metres)
_MIN_RSSI_DBM   = -90.0 # drop anchors weaker than this — too noisy to help

# ── Calibrated 2.4 GHz path-loss constants (H07-C corridor, tested) ──────────
# Overrides per-AP DB values — all enterprise APs in H07-C are the same model
# and the corridor path-loss exponent is environment-wide, not per-AP.
_RSSI_REF_DBM = -38.0   # RSSI at 1 m for 2.4 GHz
_PATH_LOSS_N  =  2.1    # corridor path-loss exponent for 2.4 GHz


# ── Distance estimation ───────────────────────────────────────────────────────

def estimate_distance(rssi_smoothed: float) -> float:
    """Log-distance: dist = 10^((_RSSI_REF_DBM − rssi) / (10·_PATH_LOSS_N)), clamped [0.3, 80] m."""
    exponent = (_RSSI_REF_DBM - rssi_smoothed) / (10.0 * _PATH_LOSS_N)
    return max(0.3, min(80.0, 10.0 ** exponent))


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _weighted_centroid(anchors: list) -> tuple[float, float]:
    """Inverse-square weighting: w = 1 / (d^2). The +0.1 prevents division by zero."""
    weights = [1.0 / (t[1]**2 + 0.1) for t in anchors]
    w_sum = sum(weights)
    x = sum(w * t[0]["x"] for t, w in zip(anchors, weights)) / w_sum
    y = sum(w * t[0]["y"] for t, w in zip(anchors, weights)) / w_sum
    return x, y


def _is_within_bounds(pos: tuple[float, float], anchors: list) -> bool:
    """Reject result if it falls > 30% outside the AP cluster bounding box."""
    min_x = min(t[0]["x"] for t in anchors)
    max_x = max(t[0]["x"] for t in anchors)
    min_y = min(t[0]["y"] for t in anchors)
    max_y = max(t[0]["y"] for t in anchors)
    mx = max(max_x - min_x, 5.0) * 0.30 + 2.0
    my = max(max_y - min_y, 5.0) * 0.30 + 2.0
    return ((min_x - mx) <= pos[0] <= (max_x + mx) and
            (min_y - my) <= pos[1] <= (max_y + my))


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

    # NOTE: In a highly optimized system, known_by_prefix should be pre-computed 
    # outside this function at startup, but computing it here is safe.
    known_by_prefix: dict[str, dict] = {}
    for ap in known_aps:
        known_by_prefix.setdefault(_prefix(ap["bssid"]), ap)

    # ── Kalman-smooth RSSI; skip weak anchors ─────────────────────────────────
    # We now store a 4-tuple: (ap_dict, distance, raw_rssi, prefix) to eliminate re-lookups
    anchors: list[tuple[dict, float, float, str]] = []
    
    for prefix, ap in known_by_prefix.items():
        raw_rssi = scan_by_prefix.get(prefix)
        if raw_rssi is None or raw_rssi < _MIN_RSSI_DBM:
            continue
            
        if prefix not in kalman_states:
            kalman_states[prefix] = KalmanState(x=raw_rssi)
            
        smoothed = kalman_states[prefix].update(raw_rssi)
        dist = estimate_distance(smoothed)
        anchors.append((ap, dist, raw_rssi, prefix))

    if not anchors:
        return None

    # ── Sort: nearest first; break ties by strongest raw RSSI ────────────────
    # t[1] is distance, t[2] is raw_rssi
    anchors.sort(key=lambda t: (t[1], -t[2]))

    # ── Outlier rejection (> 2σ from mean distance) ───────────────────────────
    if len(anchors) > 3:
        mean = sum(t[1] for t in anchors) / len(anchors)
        std  = math.sqrt(sum((t[1] - mean) ** 2 for t in anchors) / len(anchors))
        filtered = [a for a in anchors if abs(a[1] - mean) <= 2.0 * std]
        if filtered:
            anchors = filtered

    # ── Limit to top-5 ───────────────────────────────────────────────────────
    anchors = anchors[:5]

    # ── Quality metric (Optimized) ────────────────────────────────────────────
    # Calculates the absolute difference between raw_rssi and Kalman smoothed x
    avg_error = sum(abs(t[2] - kalman_states[t[3]].x) for t in anchors) / len(anchors)

    # Drop truly unreliable scans
    if avg_error > 20.0:
        return None

    # ── Fast bootstrap: snap only when unmistakably next to an AP ─────────────
    strongest = max(anchors, key=lambda t: t[2])  # Find max raw_rssi
    if strongest[2] > -40.0:
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
        return None   # one AP gives only a distance, not a position
    else:
        x, y = _weighted_centroid(anchors)
        if not _is_within_bounds((x, y), anchors):
            x, y = _weighted_centroid(anchors[:3])

    # ── Three-zone adaptive EMA with hard jump cap ────────────────────────────
    last    = kalman_states.get("__pos__")
    last_ts = kalman_states.get("__pos_ts__", 0.0)
    now     = time.time()
    stale   = last is None or (now - last_ts) > 15.0

    if not stale:
        dx  = x - last[0]
        dy  = y - last[1]
        movement = math.sqrt(dx * dx + dy * dy)

        # Cap position jump to _MAX_JUMP_M per scan to prevent corridor snaps
        if movement > _MAX_JUMP_M:
            scale = _MAX_JUMP_M / movement
            x = last[0] + dx * scale
            y = last[1] + dy * scale
            movement = _MAX_JUMP_M

        if movement < 0.5:
            alpha = 0.50   # stationary
        elif movement < 4.0:
            alpha = 0.85   # walking
        else:
            alpha = 0.95   # fast movement

        x = alpha * x + (1.0 - alpha) * last[0]
        y = alpha * y + (1.0 - alpha) * last[1]
    # else: WiFi just reconnected — accept new position directly, no stale blend

    kalman_states["__pos__"]    = (x, y)
    kalman_states["__pos_ts__"] = now

    return {
        "x":              round(x, 3),
        "y":              round(y, 3),
        "anchor_count":   len(anchors),
        "avg_rssi_error": round(avg_error, 2),
    }