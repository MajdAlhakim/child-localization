# Deployment and Test Guide

Hardware: XIAO ESP32-C5 + MPU6050 → trakn.duckdns.org (GCP e2-micro, Ubuntu 22.04)

Each stage must pass in full before advancing to the next.

---

## Stage 1 — Server Health Check

**Goal:** Confirm the backend container is running, the database is reachable, and the HTTPS endpoint is serving.

**Prerequisites:**
- GCP VM running (`35.238.189.188`)
- Docker Compose stack deployed (`docker compose up -d --build`)
- Let's Encrypt certificate valid for `trakn.duckdns.org`

**Commands (run from any machine with internet access):**

```bash
curl -s https://trakn.duckdns.org/api/v1/health | python3 -m json.tool
```

**Expected output:**

```json
{
  "status": "healthy",
  "database": "connected",
  "active_devices": 0,
  "uptime_s": <number>
}
```

HTTP 200. The `database` field must be `"connected"` — any other value means the `db` container is not ready.

**Diagnose failure:**

```bash
# On the GCP VM:
sudo docker compose ps                          # all three services should show "Up"
sudo docker compose logs backend --tail=50      # look for DB connection or import errors
sudo docker compose logs nginx --tail=20        # look for upstream connect failures
sudo docker compose logs db --tail=20           # look for postgres startup errors

# If nginx reports "no live upstreams":
sudo docker compose restart backend

# If cert is expired:
sudo certbot certificates
sudo certbot renew
```

---

## Stage 2 — Firmware Connection Test

**Goal:** Confirm the XIAO ESP32-C5 connects to QU-User Wi-Fi, completes the TLS handshake with the server, and receives HTTP 202.

**Prerequisites:**
- Stage 1 passed
- XIAO ESP32-C5 flashed with `firmware/esp32c5/trakn_tag/trakn_tag.ino`
- Board powered on and connected via USB-C
- Arduino IDE Serial Monitor open at **115200 baud**, or `arduino-cli monitor -p <PORT> -c baudrate=115200`
- Device MAC `24:42:E3:15:E5:72` registered with QU IT

**Commands:** Power-cycle the board and watch the Serial Monitor.

**Expected serial output (within 30 s of power-on):**

```
[TRAKN] starting...
[IMU] ready
[WIFI] connecting to QU User
[WIFI] connected, IP: 10.x.x.x
[POST] task started
[POST] 202 — <N> bytes, wifi=no
[POST] 202 — <N> bytes, wifi=no
```

The HTTP response code must be `202`. Any other code:

| Code | Cause |
|---|---|
| `401` | `X-API-Key` header missing or wrong — check `#define API_KEY` in firmware matches `GATEWAY_API_KEY` in `.env` |
| `422` | JSON body format mismatch — compare firmware JSON builder with `GatewayPacketRequest` in `backend/app/schemas/gateway.py` |
| `0` / connect failed | TLS failure — `client.setInsecure()` should bypass cert check; confirm `SERVER_URL` IP is correct |
| `-1` | Wi-Fi not connected — confirm QU-User MAC registration |

**Diagnose failure:**

```bash
# Check backend received anything:
sudo docker compose logs backend --tail=30

# Confirm the API key in .env matches the firmware constant:
grep GATEWAY_API_KEY ~/child-localization/.env
# Must match: 580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990
```

---

## Stage 3 — Packet Reception Test

**Goal:** Confirm the server correctly receives, parses, and persists a packet from the board — IMU rows appear in the database and WiFi scan rows appear after the first scan cycle.

**Prerequisites:**
- Stage 2 passed (board sending 202 responses)
- `psql` access via `sudo docker compose exec db psql -U admin -d localization`

**Commands:** Let the board run for ~15 seconds, then:

```bash
# Check device was auto-registered:
sudo docker compose exec db psql -U admin -d localization -c \
  "SELECT mac_address, label, is_active FROM devices;"

# Check IMU rows are accumulating:
sudo docker compose exec db psql -U admin -d localization -c \
  "SELECT COUNT(*) AS imu_rows FROM imu_samples;"

# Inspect the most recent 5 IMU samples:
sudo docker compose exec db psql -U admin -d localization -c \
  "SELECT ts_device_ms, ROUND(ax_ms2::numeric,4) AS ax,
          ROUND(ay_ms2::numeric,4) AS ay, ROUND(az_ms2::numeric,4) AS az
   FROM imu_samples ORDER BY ts_server DESC LIMIT 5;"

# After ~11 s, check WiFi APs were recorded:
sudo docker compose exec db psql -U admin -d localization -c \
  "SELECT bssid, ssid, band FROM access_points;"
```

**Expected output:**

- `devices`: one row with `mac_address = '24:42:E3:15:E5:72'`, `label = 'ESP32C5-24:42:E3:15:E5:72'`, `is_active = true`
- `imu_samples` count: growing — at least 200 rows after 10 seconds (100 Hz board rate)
- IMU values with board lying flat: `az_ms2` ≈ 9.81, `ax_ms2` ≈ 0.0, `ay_ms2` ≈ 0.0
- `access_points`: rows for every unique BSSID seen in the first Wi-Fi scan

**Diagnose failure:**

```bash
# If IMU count stays at 0 but Stage 2 passed:
sudo docker compose logs backend --tail=50 | grep -E "(ERROR|422|400)"

# Confirm gateway router is registered in the app:
curl -s https://trakn.duckdns.org/openapi.json | \
  python3 -c "import sys,json; [print(p) for p in json.load(sys.stdin)['paths']]"
# Must include: /api/v1/gateway/packet
```

---

## Stage 4 — PDR Validation Test

**Goal:** Walk with the device for 20 steps and confirm step count increments and position updates appear in server logs.

**Prerequisites:**
- Stage 3 passed
- Fusion coordinator registered in `app.state` (TASK-13 done)
- PDR module initialised with locked constants from `CLAUDE.md §7`

**Procedure:**

1. Strap the device to the wrist or carry at waist height, board face roughly horizontal.
2. Tail the backend log in real time:

```bash
sudo docker compose logs -f backend | grep -Ei "(pdr|step|position|imu_only)"
```

3. Walk 20 clear steps in a straight line, then stop completely for 3 s.

**Expected log output:**

```
[fusion] step detected — count=1
[fusion] step detected — count=2
...
[fusion] step detected — count=20
[fusion] position updated — mode=imu_only  x=<N>  y=<N>
```

**Quantitative check:** After 20 steps the position offset from origin must be between **10 m and 18 m** (0.5–0.9 m per stride). Outside that range:

| Symptom | Cause |
|---|---|
| offset < 1 m after 20 steps | Step detection not triggering — check `az_ms2` oscillates ≥ ±1 m/s² during walking |
| offset > 25 m | False-step loop — check `std(window)` guard in `pdr.py` |
| ZUPT not clearing velocity | Board not held still after walking; hold motionless for ≥ 3 s |

**Diagnose failure:**

```bash
# Verify raw IMU shows clear step impulses (az should swing 8–12 m/s² during walking):
sudo docker compose exec db psql -U admin -d localization -c \
  "SELECT ts_device_ms, ROUND(az_ms2::numeric,3) AS az
   FROM imu_samples ORDER BY ts_server DESC LIMIT 100;"
```

---

## Stage 5 — End-to-End Latency Check

**Goal:** Confirm round-trip time from board POST to server `202` response is within the ≤ 2.0 s target (≤ 2.5 s minimum).

**Prerequisites:**
- Stage 3 passed

**Commands:**

Measure the difference between board clock and server receive timestamp across 10 consecutive rows:

```bash
sudo docker compose exec db psql -U admin -d localization -c \
  "SELECT
     ts_device_ms,
     ROUND(EXTRACT(EPOCH FROM ts_server)::numeric * 1000) AS ts_server_ms,
     ROUND(EXTRACT(EPOCH FROM ts_server)::numeric * 1000) - ts_device_ms AS delta_ms
   FROM imu_samples
   ORDER BY ts_server DESC LIMIT 10;"
```

**Expected output:**

- `delta_ms` is a roughly stable offset (device clock is not synchronised to UTC, so absolute value is not meaningful)
- **Variance** of `delta_ms` across 10 rows < 200 ms — this represents actual network + processing jitter
- No `[POST] failed` lines in the Serial Monitor during the measurement window
- No `5xx` errors in `sudo docker compose logs backend`

**Diagnose failure:**

```bash
# Inspect nginx for dropped keep-alive or upstream timeout:
sudo docker compose logs nginx --tail=50 | grep -v " 202 "

# Check backend processing time per request:
sudo docker compose logs backend --tail=100 | grep "gateway"

# If delta_ms variance > 500 ms, check GCP VM load:
# (SSH into VM)
top     # backend should be < 20% CPU at 20 packets/sec steady state
free -h # confirm no OOM pressure
```

If POST failures appear every ~60 s, the server is closing the keep-alive connection and the board must re-handshake. Check nginx `keepalive_timeout` in `nginx/nginx.conf` and confirm it is set to at least 65 s.
