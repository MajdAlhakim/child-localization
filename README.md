# Child Indoor Localization System

Real-time child tracking system for **Qatar University Building H07, C Corridor**.
A BW16 wearable device streams IMU and Wi-Fi RTT data over BLE → AP gateway → cloud FastAPI server → Flutter parent app, using EKF + Bayesian grid fusion to estimate position.

---

## Live Deployment

| Component | Platform | URL / Details |
|---|---|---|
| **Database** | PostgreSQL 16 (Docker on VM) | Local to GCP VM — accessed via `db:5432` |
| **API Server** | GCP e2-micro VM — Ubuntu 22.04 | `http://35.238.189.188:8000` ✅ **LIVE** |

> The server is cloud-hosted on a GCP VM with a static public IP and **always-on** (systemd auto-restart). University APs POST BLE data directly over HTTP — no university LAN required.

---

## Architecture

```
BW16 Device (IMU + RTT)
        │ BLE
        ▼
   QU Access Point
        │ HTTP POST  X-API-Key: <GATEWAY_API_KEY>
        ▼
  GCP e2-micro VM — 35.238.189.188:8000
  ┌─────────────────────────────────────────┐
  │  FastAPI + EKF + Bayesian Grid Fusion   │
  │  Docker Compose  systemd auto-restart   │
  └─────────────────────────────────────────┘
        │ asyncpg             │ WebSocket
        ▼                     ▼
  PostgreSQL 16 (local)   Flutter Parent App (Android 12)
```

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
│   └── bw16/             # Arduino sketches (IMU, RTT, BLE transmitter)
├── app/
│   └── lib/              # Flutter app (screens, services, models)
├── tests/                # pytest test suite (all agents)
├── fly.toml              # Fly.io config (unused — kept for reference)
├── .github/workflows/    # GitHub Actions
├── docker-compose.yml    # Docker Compose (production + local dev)
├── .env                  # Local dev secrets (not committed)
├── PRD.md                # Full product requirements document
├── tasks.json            # Single source of truth for task progress
└── progress.txt          # Append-only session log
```

---

## GCP VM Deployment (Production)

**Server:** `35.238.189.188` — GCP e2-micro, Ubuntu 22.04, us-central1, port 8000

### Endpoints (give these to QU IT team)

| Route | Method | Description |
|---|---|---|
| `http://35.238.189.188:8000/api/v1/health` | GET | Health check |
| `http://35.238.189.188:8000/api/v1/gateway/packet` | POST | AP gateway ingestion |
| `ws://35.238.189.188:8000/ws/{device_id}` | WebSocket | Live position stream |

### Update server after any git push

```bash
# In GCP browser SSH
cd ~/child-localization
git pull origin main
sudo docker compose up -d --build
```

### Check status

```bash
sudo docker compose ps
sudo docker compose logs backend --tail=50
```

### Auto-restart

Configured via systemd — stack restarts automatically on VM reboot.

---

## Local Development

```bash
git clone https://github.com/MajdAlhakim/child-localization.git
cd child-localization
# Edit .env with your local DB credentials
docker compose up --build
```

### Run tests (no Docker needed)

```bash
python -m pip install -r backend/requirements.txt pytest pytest-asyncio httpx aiosqlite
python -m pytest tests/ --tb=short -q
```

> Tests use SQLite in-memory — fully offline.

---

## API Overview

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/v1/health` | GET | None | Server + DB status |
| `/api/v1/auth/login` | POST | None | Parent JWT login |
| `/api/v1/devices` | GET | JWT | List active devices |
| `/api/v1/devices/{id}/position` | GET | JWT | Latest fused position |
| `/api/v1/admin/calibration` | POST/GET | JWT | Manage AP calibration |
| `/api/v1/admin/calibration/{bssid}` | GET/DELETE | JWT | Per-AP calibration |
| `/api/v1/gateway` | POST | X-API-Key | BLE packet ingestion from AP |
| `/ws/{device_id}` | WebSocket | JWT | Live position stream |

---

## Task Ownership

| Agent | Identity | Tasks | Scope |
|---|---|---|---|
| Laptop A | `person-a` | 02,03,04,07,08,19 | DB, config, security, Docker |
| Laptop B | `person-b` | 05,05B,06,18 | BLE parser, gateway API, firmware |
| Laptop C | `person-c` | 09–13 | EKF, Bayesian fusion, PDR |
| Laptop D | `person-d` | 14–17,20 | WebSocket, parent API, Flutter app |

See `tasks.json` for live status.

---

## Key Design Decisions

| Decision | Choice |
|---|---|
| RTT method | One-sided RTT (BW16 Wi-Fi FTM) |
| Fusion | EKF 4-state `[px, py, vx, vy]` + Bayesian grid 0.5 m cells |
| Database | PostgreSQL 16 on Supabase (asyncpg + SQLAlchemy 2.0 async) |
| Auth | JWT (python-jose) for parents; X-API-Key for AP gateways |
| Mobile | Flutter (Android 12 primary) |
| Server | GCP e2-micro VM, 35.238.189.188, Docker Compose, systemd auto-restart |

---

## Performance Targets

| Metric | Target |
|---|---|
| IMU sampling rate | ≥ 50 Hz |
| RTT cycle rate | ≥ 2 Hz |
| WebSocket update rate | ≥ 4 Hz |
| Bayesian grid update | ≤ 50 ms |
| End-to-end latency | ≤ 2.0 s |
| Fused position RMS error | ≤ 2.5 m |

---

## Agent Workflow

```bash
# Session start (mandatory)
git pull --rebase origin main
cat tasks.json
cat progress.txt
git log --oneline -10

# After completing a task
# 1. Update tasks.json (your entry only)
# 2. Append to progress.txt
git add tasks.json progress.txt <your files>
git commit -m "[TASK-XX] done: <description>"
git push origin main
```

Full rules: `.agent/rules/child-localization.md`

---

## License

Qatar University Senior Design Project 2025 — All rights reserved.
