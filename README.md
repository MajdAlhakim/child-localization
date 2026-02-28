# Child Indoor Localization System

Real-time child tracking system for **Qatar University Building H07, C Corridor**.
A BW16 wearable device streams IMU and Wi-Fi RTT data over BLE → AP gateway → cloud FastAPI server → Flutter parent app, using EKF + Bayesian grid fusion to estimate position.

---

## Live Deployment

| Component | Platform | URL / Details |
|---|---|---|
| **Database** | Supabase (PostgreSQL 16) | `krfmibtoeffqlumhthyv.supabase.co` — Singapore region |
| **API Server** | Render.com | _Set after first Render deploy — see setup below_ |

> The server is cloud-hosted with a public IP. The university APs POST BLE data directly to the Render URL over HTTPS. No university LAN access is required.

---

## Architecture

```
BW16 Device (IMU + RTT)
        │ BLE
        ▼
   QU Access Point
        │ HTTPS POST (X-API-Key)
        ▼
  Render.com — FastAPI Server (cloud, public IP)
  ┌─────────────────────────────────────────┐
  │  EKF (4-state) + Bayesian Grid Fusion   │
  │  0.5 m × 0.5 m grid cells              │
  └─────────────────────────────────────────┘
        │ asyncpg (SSL)       │ WebSocket
        ▼                     ▼
  Supabase PostgreSQL 16   Flutter Parent App (Android 12)
  (Singapore, ap-southeast-1)
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
├── render.yaml           # Render one-click deploy config
├── docker-compose.yml    # Local development only
├── .env                  # Local dev secrets (not committed)
├── PRD.md                # Full product requirements document
├── tasks.json            # Single source of truth for task progress
└── progress.txt          # Append-only session log
```

---

## Render Deployment (FastAPI Server)

### First-time setup

1. Go to [render.com](https://render.com) → **New → Blueprint**
2. Connect your GitHub repo (`MajdAlhakim/child-localization`)
3. Render detects `render.yaml` automatically
4. In Render dashboard → **Environment**, add these secrets:

| Key | Value |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres.krfmibtoeffqlumhthyv:[DB-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres` |
| `SECRET_KEY` | _(generate a strong random string)_ |
| `GATEWAY_API_KEY` | _(shared secret with the AP gateway team)_ |
| `ALLOWED_ORIGINS` | `*` or your Flutter app origin |

1. Click **Deploy** — Render builds the Docker image and starts the server
2. Health check: `GET https://child-localization.onrender.com/api/v1/health`

> **Supabase DB password:** Supabase dashboard → Project Settings → Database → Connection string section

### Auto-deploy

Every `git push` to `main` triggers a Render redeploy automatically (`autoDeploy: true` in `render.yaml`).

---

## Local Development

```bash
git clone https://github.com/MajdAlhakim/child-localization.git
cd child-localization
# Edit .env — fill in DB password from Supabase dashboard
docker compose up --build   # uses local postgres (for offline dev only)
```

### Run tests (no Docker, no live DB needed)

```bash
python -m pip install -r backend/requirements.txt pytest pytest-asyncio httpx aiosqlite
python -m pytest tests/ --tb=short -q
```

> Tests use SQLite in-memory — fully offline. Supabase is production only.

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
| Server | Render.com (Docker, auto-deploy from GitHub) |

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
