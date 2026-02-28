# Child Indoor Localization System

Real-time child tracking system for **Qatar University Building H07, C Corridor**.
A BW16 wearable device streams IMU and Wi-Fi RTT data over BLE → AP gateway → cloud FastAPI server → Flutter parent app, using EKF + Bayesian grid fusion to estimate position.

---

## Live Deployment

| Component | Platform | URL / Details |
|---|---|---|
| **Database** | Supabase (PostgreSQL 16) | `krfmibtoeffqlumhthyv.supabase.co` — Singapore region |
| **API Server** | Fly.io | `https://child-localization-api.fly.dev` _(live after first deploy)_ |

> The server is cloud-hosted with a public IP and **always-on** (no spin-down). University APs POST BLE data directly over HTTPS — no university LAN access required.

---

## Architecture

```
BW16 Device (IMU + RTT)
        │ BLE
        ▼
   QU Access Point
        │ HTTPS POST (X-API-Key)
        ▼
  Fly.io — FastAPI Server (Singapore, always-on)
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
├── fly.toml              # Fly.io deploy config (always-on, Singapore)
├── .github/workflows/    # GitHub Actions — auto-deploy to Fly.io on push
├── docker-compose.yml    # Local development only
├── .env                  # Local dev secrets (not committed)
├── PRD.md                # Full product requirements document
├── tasks.json            # Single source of truth for task progress
└── progress.txt          # Append-only session log
```

---

## Fly.io Deployment (FastAPI Server)

### First-time setup (run once)

```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh      # macOS/Linux
# Windows: https://fly.io/install.ps1

# 2. Sign up / log in
fly auth signup     # or: fly auth login

# 3. Create the app (uses fly.toml config)
fly apps create child-localization-api

# 4. Set production secrets
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://postgres.krfmibtoeffqlumhthyv:[DB-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres" \
  SECRET_KEY="<strong-random-string>" \
  GATEWAY_API_KEY="<shared-secret-with-ap-team>" \
  ALLOWED_ORIGINS="*"

# 5. Deploy
fly deploy
```

> **Supabase DB password:** Supabase dashboard → Project Settings → Database → Connection string

### Health check

```
GET https://child-localization-api.fly.dev/api/v1/health
```

### Auto-deploy on push

Add `FLY_API_TOKEN` to your GitHub repo secrets (Settings → Secrets → Actions):

```bash
fly tokens create deploy -x 999999h   # generate token
```

Then every `git push` to `main` auto-deploys via `.github/workflows/fly-deploy.yml`.

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
| Server | Fly.io (Docker, always-on, Singapore, auto-deploy via GitHub Actions) |

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
