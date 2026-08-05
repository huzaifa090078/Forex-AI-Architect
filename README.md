# AI Forex Trading Bot — Architecture

> **Status:** Architecture scaffold — module interfaces defined, trading logic not yet implemented.

A production-grade AI-driven Forex trading platform with a React dashboard, Python FastAPI backend, and modular, independently testable components.

---

## Stack at a Glance

| Layer | Technology |
|---|---|
| **Frontend** | React 19 + TypeScript + Tailwind CSS + Vite |
| **Backend** | Python 3.12 + FastAPI + Uvicorn |
| **Database** | PostgreSQL 16 |
| **ORM (Python)** | SQLAlchemy 2.0 (async) + Alembic |
| **ORM (Node.js)** | Drizzle ORM (dev stubs) |
| **Auth** | JWT (access + refresh tokens) via python-jose + bcrypt |
| **AI/ML** | scikit-learn, numpy, pandas (model layer — not yet wired) |
| **Broker** | MetaTrader 5 via Python MetaTrader5 package |
| **API Contract** | OpenAPI 3.1 → Orval codegen (React Query hooks + Zod schemas) |
| **Scheduling** | APScheduler (periodic market scans, position sync) |

---

## Folder Structure

```
.
├── artifacts/
│   ├── forex-dashboard/          # React + TypeScript + Tailwind frontend
│   │   └── src/
│   │       ├── components/       # Shared UI primitives
│   │       ├── pages/            # Route-level page components
│   │       │   ├── dashboard/    # Portfolio summary + equity curve
│   │       │   ├── trades/       # Trade history + stats
│   │       │   ├── signals/      # AI signal feed
│   │       │   ├── market/       # Live market scanner
│   │       │   ├── backtests/    # Backtest runs + results
│   │       │   ├── news/         # Economic calendar
│   │       │   ├── settings/     # Bot configuration
│   │       │   └── logs/         # System event log
│   │       ├── hooks/            # Custom React hooks
│   │       └── store/            # Global state (Zustand / React Query)
│   │
│   └── api-server/               # Node.js Express (dev stubs only)
│       └── src/routes/stubs.ts   # ← Dev stub responses for all API endpoints
│
├── backend/                      # Python FastAPI — THE production backend
│   ├── main.py                   # App factory + Uvicorn entry point
│   ├── requirements.txt          # Python dependencies
│   ├── .env.example              # All environment variables documented
│   ├── alembic.ini               # Alembic migration config
│   └── app/
│       ├── core/
│       │   ├── config.py         # Pydantic Settings — all env vars typed
│       │   ├── security.py       # bcrypt + JWT helpers (stateless)
│       │   └── database.py       # Async SQLAlchemy engine + session dep
│       │
│       ├── api/
│       │   ├── router.py         # Top-level router — assembles all v1 routes
│       │   └── v1/
│       │       ├── auth.py       # POST /login /register /refresh, GET /me
│       │       ├── dashboard.py  # GET /summary /performance
│       │       ├── trades.py     # Full CRUD + /stats
│       │       ├── signals.py    # GET list /active /{id}
│       │       ├── market.py     # GET /pairs /scan
│       │       ├── backtests.py  # GET list, POST, GET /{id}
│       │       ├── news.py       # GET list /upcoming
│       │       ├── settings.py   # GET + PATCH
│       │       └── logs.py       # GET list /errors
│       │
│       ├── modules/              # ← The core business logic layer
│       │   │
│       │   ├── ai_engine/        # Signal generation pipeline
│       │   │   ├── interfaces.py # IAIEngine, IFeatureExtractor, ISignalFilter
│       │   │   ├── types.py      # OHLCV, FeatureVector, SignalCandidate, ModelMetadata
│       │   │   └── base.py       # BaseAIEngine, BaseFeatureExtractor, BaseSignalFilter
│       │   │
│       │   ├── market_scanner/   # Multi-pair opportunity detection
│       │   │   ├── interfaces.py # IMarketScanner, IMarketDataProvider, ScanResult
│       │   │   └── base.py       # BaseMarketScanner (scan_all + scan_pair)
│       │   │
│       │   ├── smc/              # Smart Money Concepts analysis
│       │   │   ├── interfaces.py # ISMCAnalyzer, SMCPattern, SMCStructure, Zone
│       │   │   └── base.py       # BaseSMCAnalyzer (all 5 detection methods)
│       │   │
│       │   ├── indicators/       # Technical indicators (stateless)
│       │   │   ├── interfaces.py # IIndicator, IIndicatorSuite, IndicatorResult
│       │   │   └── base.py       # IndicatorSuite registry + BaseIndicator
│       │   │
│       │   ├── risk_manager/     # Position sizing + drawdown control
│       │   │   ├── interfaces.py # IRiskManager, RiskCheckResult, PositionSize
│       │   │   └── base.py       # BaseRiskManager (check_trade, compute_position_size)
│       │   │
│       │   ├── trade_manager/    # Order lifecycle management
│       │   │   ├── interfaces.py # ITradeManager, OrderRequest, OrderResult
│       │   │   └── base.py       # BaseTradeManager (open, close, modify, sync)
│       │   │
│       │   ├── mt5_integration/  # MetaTrader 5 broker adapter
│       │   │   ├── interfaces.py # IMT5Connector, AccountInfo, BrokerPosition
│       │   │   └── base.py       # RealMT5Connector — live MT5/Exness terminal only
│       │   │
│       │   ├── backtesting/      # Historical strategy simulation
│       │   │   ├── interfaces.py # IBacktestEngine, IDataLoader, BacktestResult
│       │   │   └── base.py       # BaseBacktestEngine + CSVDataLoader
│       │   │
│       │   └── news_filter/      # Economic calendar + trading suppression
│       │       ├── interfaces.py # INewsFilter, INewsProvider, NewsEvent, ImpactLevel
│       │       └── base.py       # BaseNewsFilter (is_trading_allowed, upcoming)
│       │
│       ├── db/
│       │   ├── models.py         # SQLAlchemy ORM models (7 tables)
│       │   ├── schemas.py        # Pydantic v2 request/response schemas
│       │   └── migrations/       # Alembic — auto-generated migration files
│       │       └── env.py        # Async migration runner
│       │
│       └── auth/
│           ├── jwt.py            # HTTPBearer dependency → User
│           └── dependencies.py   # require_role() factory, RequireAdmin alias
│
├── lib/
│   ├── api-spec/
│   │   └── openapi.yaml          # OpenAPI 3.1 — single source of truth for all endpoints
│   ├── api-client-react/
│   │   └── src/generated/        # Auto-generated React Query hooks (do not edit)
│   ├── api-zod/
│   │   └── src/generated/        # Auto-generated Zod validation schemas (do not edit)
│   └── db/
│       └── src/schema/
│           └── trading.ts        # Drizzle ORM schema (mirrors Python models)
│
└── scripts/                      # Utility scripts
```

---

## Module Responsibilities

### AI Engine (`app/modules/ai_engine/`)
Orchestrates the signal generation pipeline: **Feature Extraction → Model Inference → Signal Filtering**.
- `IFeatureExtractor` — transforms OHLCV + SMC + indicator data into a flat feature vector
- `IModelInference` — runs the trained model (sklearn, PyTorch, or ONNX) and returns ranked candidates
- `ISignalFilter` — applies confidence threshold, news suppression, and deduplication
- `IAIEngine` — top-level facade called by the Market Scanner

### Market Scanner (`app/modules/market_scanner/`)
Monitors all configured pairs across multiple timeframes on a scheduled interval. Delegates structural analysis to the SMC module and indicator checks to the Indicators module. Hands top-scored opportunities to the AI Engine for signal generation.

### Smart Money Concepts (`app/modules/smc/`)
Detects institutional order-flow structures from raw OHLCV data:
- Order Blocks & Breaker Blocks
- Fair Value Gaps (FVG) and imbalances
- Break of Structure (BOS) and Change of Character (CHoCH)
- Liquidity sweeps and inducement levels
- Premium / Equilibrium / Discount zone classification

### Technical Indicators (`app/modules/indicators/`)
Stateless calculation layer. Each indicator implements `IIndicator.compute(ohlcv)` and returns an `IndicatorResult`. The `IndicatorSuite` registry runs any subset on demand. Planned indicators:
- **Trend:** EMA (20/50/200), SMA, VWAP, Ichimoku
- **Momentum:** RSI, MACD, Stochastic, CCI
- **Volume:** OBV, Volume Profile
- **Volatility:** ATR, Bollinger Bands, Keltner Channels

### Risk Manager (`app/modules/risk_manager/`)
Pre-flight gatekeeper for every trade. Enforces:
- Per-trade risk % (lot size calculation via ATR-based SL distance)
- Maximum open trade count
- Daily drawdown kill-switch
- Allowed pairs list

### Trade Manager (`app/modules/trade_manager/`)
Owns the full order lifecycle: **signal approved → broker order → database record → position monitoring → close**.
Composes Risk Manager (validation) and MT5 Integration (broker comms). Handles position reconciliation between local DB and live broker state.

### MT5 / Exness Integration (`app/modules/mt5_integration/`)
The **only** module that speaks to MetaTrader 5. Implements `RealMT5Connector` — the sole permitted connector — against a live MT5/Exness terminal. No simulated or demo connector is used. Abstracts: connect, account info, positions, orders, market execution, modification, OHLCV history.

### Backtesting Engine (`app/modules/backtesting/`)
Replays historical OHLCV data through the full signal pipeline in a controlled simulation. Runs in a worker pool for parallelism. Computes: win rate, profit factor, max drawdown, Sharpe ratio, equity curve.

### News Filter (`app/modules/news_filter/`)
Fetches economic calendar data (ForexFactory / custom RSS) and suppresses trading in the configured window around high-impact releases (NFP, FOMC, CPI, etc.). Injected into Trade Manager as a pre-flight guard.

---

## Database Schema

| Table | Purpose |
|---|---|
| `users` | Accounts + authentication |
| `signals` | AI-generated trade signals |
| `trades` | Full trade lifecycle records |
| `backtests` | Backtest run configs + result metrics |
| `news_items` | Cached economic calendar events |
| `bot_settings` | Per-user risk + configuration |
| `system_logs` | Structured event log from all modules |

---

## API Design

All endpoints are documented in `lib/api-spec/openapi.yaml` (OpenAPI 3.1).

Base path: `/api`
Versioned routes: `/api/v1/...`
Auth: `Authorization: Bearer <access_token>`

Key endpoints:
- `POST /api/v1/auth/login` — obtain JWT token pair
- `GET  /api/v1/dashboard/summary` — KPI snapshot
- `GET  /api/v1/dashboard/performance?period=30d` — equity curve
- `GET  /api/v1/trades` — paginated trade history
- `GET  /api/v1/signals/active` — live pending signals
- `GET  /api/v1/market/scan` — on-demand market scan
- `POST /api/v1/backtests` — queue a backtest run
- `GET  /api/v1/news/upcoming` — high-impact events in next 24h
- `PATCH /api/v1/settings` — update bot configuration

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in all values.
**Never commit `.env` to version control.**

Key secrets:
- `APP_SECRET_KEY` — application signing secret
- `JWT_SECRET_KEY` — JWT signing secret (separate from app secret)
- `DATABASE_URL` — PostgreSQL connection string
- `MT5_ACCOUNT` / `MT5_PASSWORD` / `MT5_SERVER` — broker credentials
- `AI_MODEL_PATH` — path to trained model artifacts

---

## Development Workflow

```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt

# 2. Copy and configure env
cp .env.example .env
# Edit .env with your DATABASE_URL, JWT secrets, etc.

# 3. Run database migrations
alembic upgrade head

# 4. Start the Python backend (port 8001 recommended in dev to avoid conflict)
python main.py

# 5. Start the React frontend (Replit manages this via workflow)
pnpm --filter @workspace/forex-dashboard run dev

# 6. Regenerate API hooks after OpenAPI spec changes
pnpm --filter @workspace/api-spec run codegen
```

---

## Implementation Order (Recommended)

> Follow this sequence to build the platform incrementally without breaking existing components.

1. **Auth service** — implement `auth.login` / `auth.register` / `get_current_user` dependency
2. **Database layer** — run Alembic migrations, verify all 7 tables
3. **Settings service** — basic CRUD; unblocks all other services that read risk params
4. **MT5 connector** — implement `RealMT5Connector` against a live MT5/Exness terminal
5. **Indicators module** — implement each `IIndicator.compute()` using TA-Lib or pandas
6. **SMC module** — implement each `ISMCAnalyzer` detection method
7. **AI Engine** — implement feature extractor + model inference (start with simple rules, add ML later)
8. **Market Scanner** — implement `scan_pair()` using SMC + Indicators + AI Engine
9. **Risk Manager** — implement `check_trade()` + `compute_position_size()`
10. **Trade Manager** — implement `open_trade()` + `close_trade()` + `sync_open_positions()`
11. **News Filter** — implement `INewsProvider` with ForexFactory RSS or Investing.com API
12. **Backtesting** — implement `CSVDataLoader.load()` + `BaseBacktestEngine.run()`
13. **Scheduler** — wire APScheduler: market scan, position sync, news refresh

---

## Architecture Decisions

- **Interface-first design** — every module exposes an ABC (`IXxx`) so implementations can be swapped (e.g. sklearn → PyTorch) without touching callers.
- **Separation of Python and Node.js** — Python FastAPI is the production backend; the Node.js server provides dev stubs matching the OpenAPI spec so the frontend can be developed independently.
- **OpenAPI as the single contract** — `lib/api-spec/openapi.yaml` is the source of truth. React hooks and Zod schemas are generated from it; never hand-written.
- **Async throughout** — all Python route handlers and module methods are `async`, enabling high-concurrency operation during live market hours.
- **News Filter as a kill-switch** — injected at the Trade Manager level, not the AI Engine level, so it suppresses all trade execution regardless of signal source.
