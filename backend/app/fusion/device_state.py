from collections import deque
from dataclasses import dataclass, field
from .pdr import PDREngine


@dataclass
class DeviceState:
    """
    Per-device in-memory state. One instance per MAC address.
    Held in gateway's module-level device_states dict.
    No database interaction — purely in-memory for the server process lifetime.
    """
    mac: str
    pdr: PDREngine = field(default_factory=PDREngine)
    last_seen_ts: float = 0.0   # server time.time() of last packet

    # Raw IMU ring buffer — last 2000 samples (~40 s at 50 Hz).
    # Each entry: {"seq": int, "ts": int, "ax": float, ...}
    imu_buffer: deque = field(default_factory=lambda: deque(maxlen=2000))
    imu_seq: int = 0              # monotonically increasing sample counter

    # Per-BSSID Kalman filter states for RSSI smoothing.
    # {bssid_lower → KalmanState} — populated by rssi_localizer.localize()
    kalman_states: dict = field(default_factory=dict)

    # Active floor resolved from the last Wi-Fi scan (majority BSSID vote).
    # None until the first scan with at least one known AP arrives.
    active_floor_plan_id: str | None = None
    active_floor_number: int | None = None
