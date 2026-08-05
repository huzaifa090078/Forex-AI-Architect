# Project Rules

These are the non-negotiable project-level rules for the AI Forex Trading Bot.  
All contributors and all future implementation work must follow them.

---

## 1. Real MT5/Exness Data Only

**No demo, fake, mock, stub, or simulated data — ever.**

- All trading data (prices, positions, orders, account info, OHLCV history) must come from a **live or real MetaTrader 5 account via the MT5/Exness API**.
- `SimulatedMT5Connector` must **not** be used in any environment where real logic is being tested or run.
- `RealMT5Connector` is the only permitted connector for any feature work.
- Dev stubs in `artifacts/api-server/src/routes/stubs.ts` are a temporary frontend scaffolding tool only — they must be replaced by the Python FastAPI backend before any feature is considered done.
- Hardcoded sample values, placeholder responses, and fake market data are not permitted in backend logic.

## 2. Frontend Stack — React + TypeScript + Tailwind

- All UI code lives in `artifacts/forex-dashboard/src/`.
- **React 19** with functional components and hooks only — no class components.
- **TypeScript** throughout — no `any` types, no untyped JS files in the frontend.
- **Tailwind CSS** for all styling — no plain CSS files, no CSS-in-JS libraries, no inline `style` props except for dynamic computed values.
- Component structure follows the existing page/component split in `artifacts/forex-dashboard/src/`.

## 3. Backend Stack — FastAPI + PostgreSQL

- All backend logic lives in `backend/`.
- **Python 3.12 + FastAPI + Uvicorn** — the Node.js server (`artifacts/api-server`) is dev-scaffolding only.
- **PostgreSQL** is the only permitted database — no SQLite, no in-memory stores, no other databases.
- **SQLAlchemy 2.0 async** for all DB access; **Alembic** for all schema migrations.
- Every schema change requires a new Alembic migration file — no ad-hoc DDL.

## 4. Modular Architecture

- Every trading concern is a separate module under `backend/app/modules/`:
  - `ai_engine/`, `smc/`, `indicators/`, `risk_manager/`, `trade_manager/`, `news_filter/`, `backtesting/`, `mt5_integration/`, `scheduler/`
- Each module exposes an **Abstract Base Class** (`IXxx`) in its `base.py` — callers depend only on the interface, never the implementation.
- Modules do **not** import from each other directly — all cross-module data flows through the service layer or FastAPI route handlers.
- New concerns get a new module folder, not an addition to an existing one.

## 5. Environment Variables for All Secrets and Configuration

- **No secrets or credentials in source code** — ever.
- All sensitive values (`APP_SECRET_KEY`, `JWT_SECRET_KEY`, `MT5_ACCOUNT`, `MT5_PASSWORD`, `MT5_SERVER`, `DATABASE_URL`, API keys) are read exclusively from environment variables via `backend/app/core/config.py` (Pydantic Settings).
- `backend/.env.example` is the canonical reference for every variable the app reads — keep it up to date.
- `backend/.env` is gitignored and must never be committed.
- Adding a new config value requires: adding it to `Settings` in `config.py` **and** documenting it in `.env.example`.
