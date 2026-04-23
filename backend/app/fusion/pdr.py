import statistics
from math import sqrt, exp, pi, cos, sin, degrees


class PDREngine:
    """Pedestrian Dead Reckoning engine — in-memory, per-device."""

    # ── EMA filter ────────────────────────────────────────────────────────────
    FC: float = 3.2

    # ── Gyro bias calibration ─────────────────────────────────────────────────
    BIAS_WINDOW: int = 200

    # ── Gyro dead zone — prevents heading drift from noise ────────────────────
    GYRO_DEAD_ZONE: float = 0.02        # rad/s — below this, treat as zero

    # ── Step detection ────────────────────────────────────────────────────────
    # INVARIANT: MIN_STEP_DT_MS must be > STEP_BUFFER_MS so the old step peak
    # expires from the buffer before the cooldown ends, preventing the lingering
    # peak from triggering a false detection immediately after the cooldown.
    MIN_STEP_DT_MS: float = 400.0       # cooldown — must exceed STEP_BUFFER_MS (was 600)
    STD_FACTOR: float = 0.8             # retuned for belt-clip deployment (was 2.0, SDP1)
    SWING_FACTOR: float = 0.7
    MIN_STD: float = 0.3                # retuned for weaker coupling (was 0.5, SDP1)
    MIN_MEAN_DELTA: float = 0.05        # relaxed — 500ms buffer averages mean close to 9.8
    STEP_BUFFER_MS: float = 300.0       # 300ms = half-step → mean deviates from 9.8 (was 500)

    # ── Weinberg stride ───────────────────────────────────────────────────────
    K_WEIN: float = 0.47
    P_WEIN: float = 0.25
    MIN_STRIDE: float = 0.25
    MAX_STRIDE: float = 1.40

    def __init__(self):
        self.x: float = 0.0
        self.y: float = 0.0
        self.heading: float = 0.0

        self.last_ts_ms: int | None = None

        self.a_mag_filt: float = 9.8
        self.gy_filt: float = 0.0   # yaw-axis EMA (Y=up mounting: gy is yaw, not gz)

        # Diagnostic: last corrected (bias-removed) value for all three axes.
        # Included in every broadcast so the correct yaw axis can be identified
        # by watching which one changes while physically turning the tag.
        self.dbg_gx: float = 0.0
        self.dbg_gy: float = 0.0
        self.dbg_gz: float = 0.0

        self.bias_gz: float = 0.0   # kept as gz name for compatibility but collects gy
        self.bias_samples: list[float] = []
        self.bias_calibrated: bool = False

        self.step_buffer: list[float] = []
        self.step_buffer_ts: list[int] = []
        self.last_step_ts_ms: int = 0
        self.step_count: int = 0

    def reset(self) -> None:
        """
        Reset position and heading to origin. Call when child is placed at the
        known start position facing the +X direction of the floor plan.
        Hardware gyro bias is preserved — only navigation state is cleared.
        """
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.step_buffer.clear()
        self.step_buffer_ts.clear()
        self.last_step_ts_ms = 0
        self.step_count = 0

    def ingest_sample(
        self,
        ts_ms: int,
        ax: float, ay: float, az: float,
        gx: float, gy: float, gz: float,
    ) -> dict:
        # Step 1 — dt
        if self.last_ts_ms is None:
            dt = 0.01
        else:
            dt = (ts_ms - self.last_ts_ms) / 1000.0
            dt = max(0.001, min(dt, 1.0))
        self.last_ts_ms = ts_ms

        # Step 2 — acceleration magnitude
        a_mag = sqrt(ax ** 2 + ay ** 2 + az ** 2)

        # Step 3 — EMA filter
        # Mounting: X=forward, Y=up, Z=right (right-handed).
        # Yaw = rotation around Y → use gy, not gz.
        alpha = 1.0 - exp(-2.0 * pi * self.FC * dt)
        self.a_mag_filt = self.a_mag_filt + alpha * (a_mag - self.a_mag_filt)
        gy_corrected = gy - self.bias_gz
        self.gy_filt = self.gy_filt + alpha * (gy_corrected - self.gy_filt)

        # Store bias-corrected gyro values for all axes (diagnostic only).
        self.dbg_gx = round(gx - self.bias_gz, 4)   # bias_gz is gy-based; gx has no bias removal
        self.dbg_gy = round(gy_corrected, 4)
        self.dbg_gz = round(gz, 4)

        # Step 4 — gyro bias calibration (collect gy samples; do NOT return early
        # so the step buffer keeps filling and steps can be counted immediately)
        if not self.bias_calibrated:
            self.bias_samples.append(gy)
            if len(self.bias_samples) >= self.BIAS_WINDOW:
                self.bias_gz = sum(self.bias_samples) / len(self.bias_samples)
                self.bias_calibrated = True
            # Continue — heading updates with bias_gz=0 until calibration
            # completes (slightly wrong heading for first ~2 s, acceptable)

        # Step 5 — heading integration with dead zone.
        # Sign: positive gy = turning LEFT (right-hand rule, Y up).
        # In floor-plan coords (y-down screen), turning RIGHT → heading increases.
        # So negate gy: heading -= gy_filtered * dt.
        gy_to_int = self.gy_filt if abs(self.gy_filt) > self.GYRO_DEAD_ZONE else 0.0
        self.heading -= gy_to_int * dt

        # Step 6 — rolling step buffer (use EMA-filtered magnitude, not raw,
        # to eliminate high-frequency noise spikes that cause false detections)
        self.step_buffer.append(self.a_mag_filt)
        self.step_buffer_ts.append(ts_ms)
        while (self.step_buffer_ts and
               ts_ms - self.step_buffer_ts[0] > self.STEP_BUFFER_MS):
            self.step_buffer.pop(0)
            self.step_buffer_ts.pop(0)

        # Step 7 — step detection
        if len(self.step_buffer) >= 5:
            buf = self.step_buffer
            buf_std    = statistics.stdev(buf)
            buf_mean   = statistics.mean(buf)
            buf_median = statistics.median(buf)
            buf_max    = max(buf)
            buf_min    = min(buf)

            dt_since_last = ts_ms - self.last_step_ts_ms

            cond1 = dt_since_last > self.MIN_STEP_DT_MS
            cond2 = buf_max > buf_median + self.STD_FACTOR * buf_std
            cond3 = (buf_max - buf_min) > self.SWING_FACTOR * buf_std
            cond4 = buf_std > self.MIN_STD
            cond5 = abs(buf_mean - 9.8) > self.MIN_MEAN_DELTA

            if cond1 and cond2 and cond3 and cond4 and cond5:
                swing = buf_max - buf_min
                stride = self.K_WEIN * (swing ** self.P_WEIN)
                stride = max(self.MIN_STRIDE, min(stride, self.MAX_STRIDE))
                self.x += stride * cos(self.heading)
                self.y += stride * sin(self.heading)
                self.step_count += 1
                self.last_step_ts_ms = ts_ms

        # Step 8 — return state
        return self._state()

    def _state(self) -> dict:
        return {
            "x":               round(self.x, 4),
            "y":               round(self.y, 4),
            "heading":         round(self.heading, 4),
            "heading_deg":     round(degrees(self.heading) % 360, 2),
            "step_count":      self.step_count,
            "bias_calibrated": self.bias_calibrated,
            # Diagnostic: watch these in the WebSocket stream while physically
            # turning the tag. The axis that swings large (±0.5–2.0 rad/s)
            # during a turn is the correct yaw axis.
            "dbg_gx":          self.dbg_gx,
            "dbg_gy":          self.dbg_gy,
            "dbg_gz":          self.dbg_gz,
        }
