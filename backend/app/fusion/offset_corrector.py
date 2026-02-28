"""Offset correction — subtracts per-AP, per-band calibrated offset from raw RTT.

PRD §8.2:
    d_corrected = d_raw − d_offset(AP, band)
    clamp minimum: 0.5 m

Expected offsets: 2400–2700 m (5 GHz), ~1500 m (2.4 GHz legacy).
"""

_CLAMP_MIN_M: float = 0.5


def correct(d_raw_m: float, offset_m: float) -> float:
    """Return the corrected RTT distance, clamped to a minimum of 0.5 m.

    Args:
        d_raw_m:  Raw RTT distance in metres (straight from BLE packet).
        offset_m: Calibrated per-AP, per-band offset in metres.

    Returns:
        Corrected distance ≥ 0.5 m.
    """
    return max(d_raw_m - offset_m, _CLAMP_MIN_M)
