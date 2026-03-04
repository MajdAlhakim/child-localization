# Child Indoor Localization System

Real-time child tracking system for **Qatar University Building H07, C Corridor**.
A BW16 wearable device streams IMU and Wi-Fi RTT data directly to a cloud FastAPI server over HTTPS, using EKF + Bayesian grid fusion to estimate position and push live updates to a Flutter parent app.

---

## Live Deployment

| Component | Platform | URL / Details |
|---|---|---|
| **API Server** | GCP e2-micro VM — Ubuntu 22.04 | `https://trakn.duckdns.org` ✅ **LIVE** |
| **Database** | PostgreSQL 16 (Docker on VM) | Local to GCP VM — internal only |
| **TLS / Reverse Proxy** | Nginx on port 443 | Terminates HTTPS, proxies to FastAPI on port 8000 |
| **Domain** | DuckDNS | `trakn.duckdns.org` → `35.238.189.188` |

---

## Architecture

```
BW16 Device (IMU + Wi-Fi RTT)
        │ HTTPS POST (QU-User Wi-Fi)
        ▼
  trakn.duckdns.org:443
  ┌──────────────────────────────────────────────┐
  │  Nginx (TLS termination)                     │
  │    ↓ proxy_pass to localhost:8000            │
  │  FastAPI — EKF + Bayesian Grid + PDR Fusion  │
  │  Docker Compose  ·  systemd auto-restart     │
  └──────────────────────────────────────────────┘
        │ asyncpg              │ WSS
        ▼                      ▼
  PostgreSQL 16 (local)   Flutter Parent App (Android 12)
```

**Device → Server path:**
The BW16 tag connects to the venue Wi-Fi network (QU-User) as a standard station.
Its MAC address (`24:42:E3:15:E5:72`) is pre-registered with QU IT.
On power-on it auto-connects and POSTs binary IMU + RTT packets directly to the server over HTTPS — no BLE gateway or GSM module required.

---

## Repository Structure

```
child-localization/
├── backend/
│   ├── app/
│   │   ├── api/          # gateway, parent, admin, websocket endpoints
│   │   ├── core/         # config, security (JWT + API key)
│   │   ├── db/           # SQLAlchemy 2.0 models, session, init
│   │   ├── fusion/       # EKF, Bayesian grid, PDR, offset corrector
│   │   └── schemas/      # Pydantic request/response models
│   ├── requirements.txt
│   └── Dockerfile
├── firmware/
│   └── bw16/             # Arduino sketches (IMU reader, RTT ranger, Wi-Fi sender)
├── app/
│   └── lib/              # Flutter app (screens, services, models)
├── nginx/
│   └── nginx.conf        # TLS termination + WebSocket proxy config
├── tests/                # pytest test suite
├── docker-compose.yml    # Full stack: db + backend + nginx
├── CLAUDE.md             # Workspace rules (session protocol, task ownership, locked constants)
├── PRD.md                # Full product requirements document
├── tasks.json            # Single source of truth for task progress
└── progress.txt          # Append-only session log
```

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/v1/health` | GET | None | Server + DB status |
| `/api/v1/gateway/packet` | POST | X-API-Key | Binary IMU/RTT packet ingestion from BW16 |
| `/api/v1/auth/login` | POST | None | Parent JWT login |
| `/api/v1/devices` | GET | JWT | List linked devices |
| `/api/v1/devices/{id}/position` | GET | JWT | Latest fused position |
| `/api/v1/admin/calibration` | POST/GET | JWT | Manage AP calibration data |
| `/api/v1/admin/calibration/{bssid}` | GET/DELETE | JWT | Per-AP calibration |
| `/ws/position/{device_id}` | WebSocket (WSS) | JWT | Live position stream |

---

## How to Run the Project (End to End)

### 1. GCP VM — Production Server

**Requirements:** GCP e2-micro VM, Ubuntu 22.04, Docker + Docker Compose installed, Let's Encrypt cert issued for `trakn.duckdns.org`.

```bash
# SSH into the VM
ssh user@35.238.189.188

# Pull latest code
cd ~/child-localization
git pull origin main

# Start the full stack (Nginx + FastAPI + PostgreSQL)
sudo docker compose up -d --build

# Verify health
curl https://trakn.duckdns.org/api/v1/health
# Expected: {"status":"healthy","database":"connected",...}
```

**Check logs:**
```bash
sudo docker compose ps
sudo docker compose logs backend --tail=50
sudo docker compose logs nginx --tail=20
```

The stack restarts automatically on VM reboot via systemd.

---

### 2. BW16 Firmware — Wearable Tag

**Requirements:** Arduino IDE or arduino-cli with Realtek AmebaD board support installed.

The firmware is a **single unified sketch** (`firmware/bw16/main/main.ino`) that runs all subsystems concurrently — IMU sampling, Wi-Fi RTT ranging, and HTTPS packet transmission. Each flash overwrites the entire device, so all functionality must be compiled and uploaded together.

**Flash the firmware:**
```bash
arduino-cli compile --fqbn realtek:AmebaD:rtl8720dn firmware/bw16/main/main.ino --upload -p <PORT>
```

Or open `firmware/bw16/main/main.ino` in Arduino IDE and click **Upload**.

The device will:
1. Connect to `QU-User` Wi-Fi automatically (MAC pre-registered with QU IT)
2. Sample IMU at ≥ 50 Hz and perform Wi-Fi RTT ranging at ≥ 2 Hz
3. POST binary packets to `https://trakn.duckdns.org/api/v1/gateway/packet` with `X-API-Key` header

> **Device MAC:** `24:42:E3:15:E5:72` — must be registered with venue IT before first use.

---

### 3. Flutter App — Parent Mobile App

**Requirements:** Flutter SDK, Android device (Android 12+) or emulator.

```bash
cd app
flutter pub get
flutter run
```

**Build release APK:**
```bash
flutter build apk --release
```

The app will:
1. Prompt parent to scan the QR code on the BW16 tag to link the device
2. Log in with parent credentials (`POST /api/v1/auth/login`)
3. Open a WebSocket connection to `wss://trakn.duckdns.org/ws/position/{device_id}`
4. Display the child's live position on the H07-C corridor floor plan

---

### 4. Local Development & Testing

**Run tests (no Docker or database needed — uses SQLite in-memory):**
```bash
pip install -r backend/requirements.txt pytest pytest-asyncio httpx aiosqlite
pytest tests/ --tb=short -q
```

**Run full stack locally:**
```bash
# Copy and edit environment variables
cp .env.example .env   # set DATABASE_URL, SECRET_KEY, GATEWAY_API_KEY

docker compose up --build
# API available at http://localhost:8000
# Health check: curl http://localhost:8000/api/v1/health
```

---

## Task Ownership

| Laptop | Identity | Tasks | Scope |
|---|---|---|---|
| A | `person-a` | 02, 03, 04, 07, 08, 19 | DB, config, security, Docker |
| B | `person-b` | 05, 05B, 05C, 06, 18 | Packet parser, gateway API, firmware |
| C | `person-c` | 09–13 | EKF, Bayesian fusion, PDR, coordinator |
| D | `person-d` | 14–17, 20 | WebSocket, parent API, Flutter app |

See `tasks.json` for live status.

---

## Key Design Decisions

| Decision | Choice |
|---|---|
| Device → Server transport | Direct Wi-Fi HTTPS POST from BW16 (QU-User network) |
| RTT method | One-sided RTT (BW16 Wi-Fi FTM) |
| Fusion | EKF 4-state `[px, py, vx, vy]` + Bayesian grid (0.5 m cells) + PDR |
| TLS | Nginx reverse proxy on port 443, Let's Encrypt cert |
| Database | PostgreSQL 16 (asyncpg + SQLAlchemy 2.0 async) |
| Auth | JWT (python-jose) for parents; X-API-Key for device gateway |
| Mobile | Flutter, Android 12 primary |

---

## Performance Targets

| Metric | Target | Minimum |
|---|---|---|
| IMU sampling rate | ≥ 50 Hz | ≥ 25 Hz |
| RTT cycle rate | ≥ 2 Hz | ≥ 1 Hz |
| WebSocket update rate | ≥ 4 Hz | ≥ 2 Hz |
| Bayesian grid update | ≤ 50 ms | ≤ 100 ms |
| End-to-end latency | ≤ 2.0 s | ≤ 2.5 s |
| Fused position RMS error | ≤ 2.5 m | ≤ 4.0 m |

---

## License

Qatar University Senior Design Project 2026 — All rights reserved.
