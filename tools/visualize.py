"""
tools/visualize.py  —  TRAKN real-time PDR visualizer
======================================================
Python equivalent of pdr_stride_histogram_2d_train_logbins_final.m

Instead of reading from a COM port, raw IMU samples are fetched from:
    GET /api/v1/imu/{mac}?since={seq}

Structure mirrors the MATLAB exactly:
  while window_open:
      fetch new IMU samples from server     ← readline(s) in MATLAB
      feed each sample through local PDR    ← same math, same constants
      update plot                           ← drawnow limitrate in MATLAB

Usage
-----
    pip install requests matplotlib
    python tools/visualize.py

Keyboard shortcuts
------------------
    r   reset trail (new walk from origin)
    q   quit
"""

import math
import statistics
import sys
import time

import requests
import urllib3
import matplotlib
import matplotlib.pyplot as plt

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ────────────────────────────────────────────────────────────────────
SERVER_URL = "https://35.238.189.188"
MAC        = "24:42:E3:15:E5:72"
API_KEY    = "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990"
POLL_HZ    = 10     # server polls per second

# ── PDR parameters (LOCKED — same as server and MATLAB) ──────────────────────
FC              = 3.2
CAL_SAMPLES     = 200
WIN_STEP_MS     = 400.0
MIN_STEP_DT_MS  = 350.0
STD_FACTOR      = 1.5
SWING_FACTOR    = 0.9
MIN_STD         = 0.5
MIN_MEAN_DELTA  = 0.1
GYRO_DEAD_ZONE  = 0.02  # rad/s — zero below this to prevent heading drift
K_WEIN          = 0.47
P_WEIN          = 0.25
MIN_STRIDE      = 0.25
MAX_STRIDE      = 1.40

# ── Local PDR (same algorithm as MATLAB and server) ──────────────────────────
class LocalPDR:
    def reset(self):
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.last_ts_ms = None
        self.a_mag_filt = 9.8
        self.gz_filt    = 0.0
        self.bias_gz    = 0.0
        self.bias_samples: list[float] = []
        self.bias_calibrated = False
        self.buf_a:  list[float] = []
        self.buf_ts: list[int]   = []
        self.last_step_ts_ms = 0
        self.step_count  = 0
        self.total_dist  = 0.0
        self.path_x = [0.0]
        self.path_y = [0.0]

    def __init__(self):
        self.reset()

    def ingest(self, ts_ms: int,
               ax: float, ay: float, az: float,
               _gx: float, _gy: float, gz: float):
        # step 1 — dt
        if self.last_ts_ms is None:
            dt = 0.01
        else:
            dt = max(0.001, min((ts_ms - self.last_ts_ms) / 1000.0, 1.0))
        self.last_ts_ms = ts_ms

        # step 2 — a_mag
        a_mag = math.sqrt(ax**2 + ay**2 + az**2)

        # step 3 — EMA
        alpha = 1.0 - math.exp(-2.0 * math.pi * FC * dt)
        self.a_mag_filt += alpha * (a_mag - self.a_mag_filt)
        gz_corrected = gz - self.bias_gz
        self.gz_filt += alpha * (gz_corrected - self.gz_filt)

        # step 4 — gyro bias calibration
        if not self.bias_calibrated:
            self.bias_samples.append(gz)
            if len(self.bias_samples) >= CAL_SAMPLES:
                self.bias_gz = sum(self.bias_samples) / len(self.bias_samples)
                self.bias_calibrated = True
            return

        # step 5 — heading (dead zone suppresses noise drift)
        gz_to_int = self.gz_filt if abs(self.gz_filt) > GYRO_DEAD_ZONE else 0.0
        self.heading += gz_to_int * dt

        # step 6 — rolling buffer
        self.buf_a.append(a_mag)
        self.buf_ts.append(ts_ms)
        while self.buf_ts and ts_ms - self.buf_ts[0] > WIN_STEP_MS:
            self.buf_a.pop(0)
            self.buf_ts.pop(0)

        # step 7 — step detection
        if len(self.buf_a) < 5:
            return

        buf_std    = statistics.stdev(self.buf_a)
        buf_mean   = statistics.mean(self.buf_a)
        buf_median = statistics.median(self.buf_a)
        buf_max    = max(self.buf_a)
        buf_min    = min(self.buf_a)

        if (ts_ms - self.last_step_ts_ms  > MIN_STEP_DT_MS and
                buf_max > buf_median + STD_FACTOR * buf_std and
                (buf_max - buf_min)  > SWING_FACTOR * buf_std and
                buf_std              > MIN_STD and
                abs(buf_mean - 9.8)  > MIN_MEAN_DELTA):

            swing  = buf_max - buf_min
            stride = max(MIN_STRIDE, min(MAX_STRIDE, K_WEIN * swing**P_WEIN))

            self.x += stride * math.cos(self.heading)
            self.y += stride * math.sin(self.heading)
            self.step_count      += 1
            self.total_dist      += stride
            self.last_step_ts_ms  = ts_ms
            self.path_x.append(self.x)
            self.path_y.append(self.y)


def main():
    matplotlib.use("TkAgg")   # explicit backend — avoids silent fallbacks

    pdr    = LocalPDR()
    cursor = 0          # last seq number received from server
    flags  = {"reset": False}   # mutable container — avoids nonlocal lint issues

    url     = f"{SERVER_URL}/api/v1/imu/{MAC}"
    headers = {"X-API-Key": API_KEY}

    # ── Figure setup (dark theme matching MATLAB) ─────────────────────────────
    plt.ion()
    fig, ax = plt.subplots(figsize=(8, 8))
    fig.patch.set_facecolor("k")
    ax.set_facecolor("k")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")
    ax.tick_params(colors="#888888")
    ax.xaxis.label.set_color("#888888")
    ax.yaxis.label.set_color("#888888")
    ax.grid(True, color="#222222", linewidth=0.8, linestyle="--")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title("TRAKN — Real-Time PDR Trail", color="white", fontsize=13, pad=12)
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)

    # origin dot
    ax.plot(0, 0, "o", color="#00cc44", markersize=7, zorder=5)
    ax.annotate("origin", (0, 0), textcoords="offset points",
                xytext=(6, 5), color="#00cc44", fontsize=8)

    (path_line,) = ax.plot([], [], "w-", linewidth=2, zorder=3)
    (pos_dot,)   = ax.plot([0], [0], "ro", markersize=11, zorder=6)

    # heading arrow
    arrow = ax.annotate("", xy=(0.3, 0), xytext=(0, 0),
                        arrowprops=dict(arrowstyle="->",
                                        color="#f0c040", lw=2.2),
                        zorder=7)

    status_txt = ax.text(
        0.02, 0.97, "Waiting for device...",
        transform=ax.transAxes,
        color="#ffff00", fontsize=10, va="top", family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#111111",
                  edgecolor="#444444", alpha=0.88),
    )
    fig.text(0.5, 0.005,
             "r = reset trail    q = quit",
             ha="center", color="#555555", fontsize=8)

    def on_key(event):
        if event.key == "r":
            flags["reset"] = True
        elif event.key == "q":
            plt.close("all")
            sys.exit(0)

    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.tight_layout()
    plt.pause(0.05)

    interval = 1.0 / POLL_HZ
    server_ok = True

    # ── Main loop — mirrors MATLAB while ishghandle(f) ────────────────────────
    while plt.fignum_exists(fig.number):
        t0 = time.perf_counter()

        # reset trail
        if flags["reset"]:
            flags["reset"] = False
            pdr.reset()
            cursor = 0

        # fetch new raw IMU samples from server
        try:
            r = requests.get(url, params={"since": cursor},
                             headers=headers, verify=False, timeout=1.5)
            if r.status_code == 200:
                data     = r.json()
                samples  = data.get("samples", [])
                cursor   = data.get("next_seq", cursor)
                server_ok = True

                for s in samples:
                    pdr.ingest(s["ts"],
                               s["ax"], s["ay"], s["az"],
                               s["gx"], s["gy"], s["gz"])
            else:
                server_ok = False
        except Exception:
            server_ok = False

        # ── Update plot ───────────────────────────────────────────────────────
        px, py = pdr.path_x, pdr.path_y
        cx, cy = pdr.x, pdr.y

        path_line.set_data(px, py)
        pos_dot.set_data([cx], [cy])

        # heading arrow
        hdeg = math.degrees(pdr.heading) % 360
        span = max(max(px) - min(px), max(py) - min(py), 1.0)
        alen = span * 0.07
        hr   = math.radians(hdeg)
        arrow.set_position((cx, cy))
        arrow.xy = (cx + alen * math.cos(hr), cy + alen * math.sin(hr))

        # auto-scale — expand axes to fit path, never shrink below ±3 m
        if len(px) > 1:
            xpad = max(1.5, (max(px) - min(px)) * 0.20)
            ypad = max(1.5, (max(py) - min(py)) * 0.20)
            xlo = min(min(px) - xpad, -3)
            xhi = max(max(px) + xpad,  3)
            ylo = min(min(py) - ypad, -3)
            yhi = max(max(py) + ypad,  3)
            # equal visual scale
            xspan, yspan = xhi - xlo, yhi - ylo
            if xspan > yspan:
                mid = (ylo + yhi) / 2
                ylo, yhi = mid - xspan/2, mid + xspan/2
            else:
                mid = (xlo + xhi) / 2
                xlo, xhi = mid - yspan/2, mid + yspan/2
            ax.set_xlim(xlo, xhi)
            ax.set_ylim(ylo, yhi)

        # status text
        cal_str   = "YES" if pdr.bias_calibrated else "calibrating... (~2 s)"
        srv_str   = "" if server_ok else "  ⚠ SERVER UNREACHABLE"
        status_txt.set_text(
            f"Steps:    {pdr.step_count}\n"
            f"Distance: {pdr.total_dist:.2f} m\n"
            f"Heading:  {hdeg:.1f}°\n"
            f"Bias cal: {cal_str}{srv_str}"
        )
        status_txt.set_color("#ff4444" if not server_ok else "#ffff00")

        # drawnow equivalent
        fig.canvas.draw()
        fig.canvas.flush_events()

        elapsed = time.perf_counter() - t0
        time.sleep(max(0.0, interval - elapsed))


if __name__ == "__main__":
    main()
