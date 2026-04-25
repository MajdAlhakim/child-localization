"""
backend/app/fusion/rssi_localizer.py

RSSI-based position estimator.

Pipeline:
  1. Adaptive Kalman per AP: Q=3.0 on residual >10 dBm (moving), Q=1.0 stable.
     R raised to 12.0 for stronger noise suppression of stationary RSSI jitter.
  2. Drop anchors with raw RSSI < -80 dBm (too weak to be reliable).
  3. Log-distance path loss → distance, clamped [0.3, 80] m.
  4. Sort by (distance asc, rssi desc); reject outliers > 2σ; top-5 only.
  5. Drop scan when avg_rssi_error > 20 dBm (very unreliable).
  6. Snap to AP only when distance < 0.5 m (effectively disabled — prevents false snaps).
  7. ≥3 anchors → Gauss-Newton; fall back to centroid (top-3) if diverges.
     2 anchors → centroid.  1 anchor → None (distance only, no position).
  8. Three-zone adaptive EMA:
       movement < 1 m  → α=0.15  (stationary — very sticky)
       movement 1–4 m  → α=0.60  (walking)
       movement > 4 m  → α=0.80  (fast) + capped at 4 m/scan
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
        """Adaptive Q: 3.0 on residual > 10 dBm (real movement), 1.0 when stable."""
        residual = abs(z - self.x)
        q = 3.0 if residual > 10.0 else 1.0
        p_pred = self.p + q
        k = p_pred / (p_pred + self.R)
        self.x = self.x + k * (z - self.x)
        self.p = (1.0 - k) * p_pred
        return self.x


_MAX_JUMP_M     = 4.0   # hard cap on position change per scan (metres)
_MIN_RSSI_DBM   = -80.0 # drop anchors weaker than this — too noisy to help


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
    """Gauss-Newton nonlinear multilateration (up to 10 iterations, weighted)."""
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

    # ── Kalman-smooth RSSI; skip weak anchors ─────────────────────────────────
    anchors: list[tuple[dict, float]] = []
    for prefix, ap in known_by_prefix.items():
        raw_rssi = scan_by_prefix.get(prefix)
        if raw_rssi is None or raw_rssi < _MIN_RSSI_DBM:
            continue
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

    # Drop truly unreliable scans (20 dBm is generous — only rejects garbage)
    if avg_error > 20.0:
        return None

    # ── Fast bootstrap: snap only when unmistakably next to an AP (< 0.5 m) ──
    strongest = max(anchors, key=lambda a: scan_by_prefix[_prefix(a[0]["bssid"])])
    if strongest[1] < 0.5:
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
    elif len(anchors) == 2:
        x, y = _weighted_centroid(anchors)
    else:
        ls = _multilateral_ls(anchors)
        if ls is not None and _is_within_bounds(ls, anchors):
            x, y = ls
        else:
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
            alpha = 0.30   # stationary — absorbs jitter while staying responsive
        elif movement < 4.0:
            alpha = 0.75   # walking
        else:
            alpha = 0.95   # fast movement (after cap, this only fires at exactly 4 m)

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
