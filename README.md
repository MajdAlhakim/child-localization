# Child Indoor Localization System

Real-time child tracking system for **Qatar University Building H07, C Corridor**.
A BW16 wearable device streams IMU and Wi-Fi RTT data over BLE → AP gateway → cloud FastAPI server → Flutter parent app, using EKF + Bayesian grid fusion to estimate position.

---

## Architecture

```
BW16 Device (IMU + RTT)
        │ BLE
        ▼
   QU Access Point
        │ HTTP POST (X-API-Key)
        ▼
  Cloud FastAPI Server
  ┌─────────────────────────────┐
  │  EKF (4-state) + Bayesian   │
  │  Grid Fusion (0.5 m cells)  │
  │  PostgreSQL 16 (asyncpg)    │
  └─────────────────────────────┘
        │ WebSocket
        ▼
  Flutter Parent App (Android 12)
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
├── docker-compose.yml
├── .env                  # local dev secrets (not committed)
├── PRD.md                # Full product requirements document
├── tasks.json            # Single source of truth for task progress
└── progress.txt          # Append-only session log
```

---

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+ (3.13 supported with caveats — see below)
- Docker Desktop (running)
- Flutter SDK

### 1. Clone and configure

```bash
git clone https://github.com/MajdAlhakim/child-localization.git
cd child-localization
cp .env.example .env      # edit secrets as needed
```

### 2. Start the database and backend

```bash
docker compose up --build
```

Server available at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### 3. Run tests locally (no Docker required)

```bash
python -m pip install -r backend/requirements.txt pytest pytest-asyncio httpx aiosqlite
python -m pytest tests/ --tb=short -q
```

> **Python 3.13 note:** `passlib`'s bcrypt backend is incompatible with Python 3.13. The codebase uses the `bcrypt` package directly. The Docker container (python:3.11-slim) is unaffected.

---

## API Overview

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/v1/health` | GET | None | Server + DB status |
| `/api/v1/auth/login` | POST | None | Parent JWT login |
| `/api/v1/devices` | GET | JWT | List active devices |
| `/api/v1/devices/{id}/position` | GET | JWT | Latest position |
| `/api/v1/admin/calibration` | POST/GET | JWT | Manage AP calibration |
| `/api/v1/admin/calibration/{bssid}` | GET/DELETE | JWT | Per-AP calibration |
| `/api/v1/gateway` | POST | X-API-Key | BLE packet ingestion |
| `/ws/{device_id}` | WebSocket | JWT | Live position stream |

---

## Task Ownership

| Agent | Identity | Tasks | Scope |
|---|---|---|---|
| Laptop A | `person-a` | 02,03,04,07,08,19 | DB, config, security, Docker |
| Laptop B | `person-b` | 05,05B,06,18 | BLE parser, gateway API, firmware |
| Laptop C | `person-c` | 09–13 | EKF, Bayesian fusion, PDR |
| Laptop D | `person-d` | 14–17,20 | WebSocket, parent API, Flutter app |

See `tasks.json` for live status of every task.

---

## Key Design Decisions

| Decision | Choice |
|---|---|
| RTT method | One-sided RTT (BW16 Wi-Fi FTM) |
| Fusion | EKF 4-state `[px, py, vx, vy]` + Bayesian grid 0.5 m cells |
| Database | PostgreSQL 16 + asyncpg + SQLAlchemy 2.0 async |
| Auth | JWT (python-jose) for parents; X-API-Key for gateways |
| Mobile | Flutter (Android 12 primary) |
| Hosting | Cloud VM with public IP |

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

Each agent session must follow this protocol before writing any code:

```bash
git pull --rebase origin main
cat tasks.json      # identify your pending tasks
cat progress.txt    # see what's been done
git log --oneline -10
```

After completing a task:

```bash
# 1. Update tasks.json — your entry only (status, completed_at, notes)
# 2. Append to progress.txt
# 3. git add tasks.json progress.txt <your files>
# 4. git commit -m "[TASK-XX] done: <description>"
# 5. git push origin main
```

Full rules in `.agent/rules/child-localization.md`.

---

## License

Qatar University Senior Design Project 2025 — All rights reserved.
