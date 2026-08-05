# AI Forex Trading Bot

A production-grade AI-driven Forex trading platform with a React dashboard, Python FastAPI backend, and modular independently-testable components.

## Run & Operate

```bash
# Frontend (managed by Replit workflow)
pnpm --filter @workspace/forex-dashboard run dev

# API dev stubs (managed by Replit workflow)
pnpm --filter @workspace/api-server run dev

# Python FastAPI backend (run manually for now)
cd backend && pip install -r requirements.txt
cd backend && python main.py

# Push DB schema changes (Drizzle — dev only)
pnpm --filter @workspace/db run push

# Run Alembic migrations (Python)
cd backend && alembic upgrade head

# Regenerate API hooks after OpenAPI spec changes
pnpm --filter @workspace/api-spec run codegen
```

## Stack

- **Frontend:** React 19 + TypeScript + Tailwind CSS + Vite (artifacts/forex-dashboard)
- **Backend:** Python 3.12 + FastAPI + Uvicorn (backend/)
- **Dev stubs:** Node.js Express (artifacts/api-server) — matches OpenAPI spec for frontend dev
- **Database:** PostgreSQL + SQLAlchemy (Python) + Drizzle ORM (Node.js stubs)
- **Auth:** JWT access + refresh tokens via python-jose + bcrypt
- **AI/ML:** scikit-learn, numpy, pandas (interfaces defined, logic not yet implemented)
- **Broker:** MetaTrader 5 via Python MetaTrader5 package
- **API Contract:** OpenAPI 3.1 (lib/api-spec/openapi.yaml) → Orval codegen

## Where Things Live

- `lib/api-spec/openapi.yaml` — **Source of truth** for all API contracts
- `backend/app/modules/` — All trading logic modules (AI Engine, SMC, Indicators, etc.)
- `backend/app/db/models.py` — SQLAlchemy ORM models
- `backend/app/db/schemas.py` — Pydantic v2 request/response schemas
- `artifacts/api-server/src/routes/stubs.ts` — Dev stub responses (replace with Python in production)
- `lib/db/src/schema/trading.ts` — Drizzle schema (mirrors Python models)
- `lib/api-client-react/src/generated/` — Auto-generated React Query hooks (do not edit)
- `lib/api-zod/src/generated/` — Auto-generated Zod schemas (do not edit)

## Architecture Decisions

- **Interface-first** — every module (`ai_engine`, `smc`, `indicators`, `risk_manager`, etc.) exposes an ABC (`IXxx`) so implementations can be swapped without touching callers
- **Two backends in parallel** — Node.js stubs let the React frontend run immediately; Python FastAPI is the real production backend
- **OpenAPI as single contract** — `openapi.yaml` gates codegen; hooks are never hand-written
- **SimulatedMT5Connector** — dev/test without a live Windows MT5 terminal; swap to RealMT5Connector in production
- **News Filter as kill-switch** — injected at Trade Manager level, not AI Engine, so it suppresses all execution regardless of signal source

## Product

A professional AI Forex trading bot platform. The dashboard displays live portfolio KPIs, equity curves, AI-generated signals, market scanner results, trade history, backtesting results, economic news, and full bot configuration. Trading logic is not yet implemented — the architecture scaffold is complete.

## User Preferences

- Python FastAPI for the backend (not Node.js)
- Full modular architecture with separate folders per concern
- No fake/demo code — real interfaces only
- Architecture-first, then implement logic module by module

## Replit Setup (completed)

- **Workflows:** `artifacts/forex-dashboard: web` (port 22059) and `artifacts/api-server: API Server` (port 8000) are configured and running
- **Secrets set:** `APP_SECRET_KEY`, `JWT_SECRET_KEY` (in Replit Secrets)
- **Env vars set:** `APP_ENV`, `ALLOWED_ORIGINS=["*"]`, `MARKET_DATA_PROVIDER=yfinance`, and all other non-secret defaults
- **Database:** Replit managed PostgreSQL — initial Alembic migration applied (`e4b12c5bf3ef_initial_schema`)
- **To re-run migrations:** `cd backend && python -m alembic upgrade head`
- **To generate a new migration after model changes:** `cd backend && python -m alembic revision --autogenerate -m "description"`

## Gotchas

- The Node.js API server (`artifacts/api-server`) **actually runs the Python FastAPI backend** on Replit — its artifact.toml `run` command is `cd backend && pip install -r requirements.txt -q && python main.py`
- `DATABASE_URL` from Replit is `postgresql://...` — `config.py` auto-converts it to `postgresql+asyncpg://` and strips `sslmode` (asyncpg doesn't accept that param)
- Same conversion applies in `app/db/migrations/env.py` for Alembic
- `MetaTrader5` Python package only works on Windows (or Linux + Wine); use `SimulatedMT5Connector` on Replit (already commented out in `requirements.txt`)
- After any `lib/api-spec/openapi.yaml` change, run `pnpm --filter @workspace/api-spec run codegen` before touching frontend code
- Alembic migration runner is async — `env.py` uses `asyncio.run()`; standard sync drivers won't work
- `type: integer` in OpenAPI generates `zod.int()` (Zod v4) which fails typecheck — use `type: number` instead
- `metadata` is a reserved SQLAlchemy attribute — the `SystemLog` model uses `log_metadata` as the Python attr mapped to the `metadata` DB column

## Pointers

- See `README.md` for the full architecture diagram and implementation order
- See `backend/.env.example` for all required environment variables
- See the `pnpm-workspace` skill for workspace structure
