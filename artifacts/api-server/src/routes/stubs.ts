/**
 * Development stubs — return minimal valid responses that match the OpenAPI spec.
 * These let the React frontend render with real shape data while the Python
 * FastAPI backend is being implemented.
 *
 * PRODUCTION: Remove these routes once the Python backend is live at /api.
 */

import { Router } from "express";

const router = Router();

// ── Auth ────────────────────────────────────────────────────────────────────

router.post("/v1/auth/login", (_req, res) => {
  res.json({
    access_token: "dev-access-token",
    refresh_token: "dev-refresh-token",
    token_type: "bearer",
    expires_in: 1800,
  });
});

router.post("/v1/auth/register", (_req, res) => {
  res.status(201).json({
    id: "user-001",
    email: "trader@example.com",
    name: "Demo Trader",
    role: "admin",
    created_at: new Date().toISOString(),
  });
});

router.post("/v1/auth/refresh", (_req, res) => {
  res.json({
    access_token: "dev-access-token-refreshed",
    refresh_token: "dev-refresh-token-refreshed",
    token_type: "bearer",
    expires_in: 1800,
  });
});

router.get("/v1/auth/me", (_req, res) => {
  res.json({
    id: "user-001",
    email: "trader@example.com",
    name: "Demo Trader",
    role: "admin",
    created_at: new Date().toISOString(),
  });
});

// ── Dashboard ───────────────────────────────────────────────────────────────

router.get("/v1/dashboard/summary", (_req, res) => {
  res.json({
    balance: 10000.0,
    equity: 10247.5,
    total_pnl: 247.5,
    today_pnl: 62.3,
    open_trades: 2,
    total_trades: 48,
    win_rate: 62.5,
    bot_status: "paused",
  });
});

router.get("/v1/dashboard/performance", (_req, res) => {
  const today = new Date();
  const points = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (29 - i));
    return {
      date: d.toISOString().split("T")[0],
      equity: 10000 + Math.round(Math.random() * 400 - 100 + i * 8),
      pnl: Math.round((Math.random() * 200 - 80) * 10) / 10,
      trades: Math.floor(Math.random() * 4),
    };
  });
  res.json(points);
});

// ── Trades ──────────────────────────────────────────────────────────────────

const STUB_TRADES = [
  {
    id: "trade-001",
    pair: "EURUSD",
    direction: "buy",
    entry_price: 1.0842,
    stop_loss: 1.0812,
    take_profit: 1.0902,
    lot_size: 0.1,
    status: "open",
    pnl: null,
    risk_reward_ratio: 2.0,
    notes: "SMC Order Block confluence",
    signal_id: "sig-001",
    opened_at: new Date(Date.now() - 3600000).toISOString(),
    closed_at: null,
    created_at: new Date(Date.now() - 3600000).toISOString(),
  },
  {
    id: "trade-002",
    pair: "GBPJPY",
    direction: "sell",
    entry_price: 196.42,
    stop_loss: 196.92,
    take_profit: 195.42,
    lot_size: 0.05,
    status: "closed",
    pnl: 87.5,
    risk_reward_ratio: 2.0,
    notes: "FVG fill on H4",
    signal_id: "sig-002",
    opened_at: new Date(Date.now() - 86400000).toISOString(),
    closed_at: new Date(Date.now() - 3600000).toISOString(),
    created_at: new Date(Date.now() - 86400000).toISOString(),
  },
];

router.get("/v1/trades", (_req, res) => {
  res.json({ items: STUB_TRADES, total: STUB_TRADES.length, page: 1, limit: 50 });
});

router.get("/v1/trades/stats", (_req, res) => {
  res.json({
    total_trades: 48,
    winning_trades: 30,
    losing_trades: 18,
    win_rate: 62.5,
    total_pnl: 247.5,
    avg_win: 85.3,
    avg_loss: 42.1,
    profit_factor: 1.85,
    max_drawdown: 3.2,
    avg_rr: 1.87,
  });
});

router.get("/v1/trades/:id", (req, res) => {
  const trade = STUB_TRADES.find((t) => t.id === req.params.id) ?? STUB_TRADES[0];
  res.json(trade);
});

router.post("/v1/trades", (req, res) => {
  res.status(201).json({ id: "trade-new", ...req.body, status: "open", created_at: new Date().toISOString() });
});

router.patch("/v1/trades/:id", (req, res) => {
  res.json({ id: req.params.id, ...req.body });
});

router.delete("/v1/trades/:id", (_req, res) => {
  res.status(204).send();
});

// ── Signals ─────────────────────────────────────────────────────────────────

const STUB_SIGNALS = [
  {
    id: "sig-001",
    pair: "EURUSD",
    direction: "buy",
    confidence: 0.87,
    entry_zone_low: 1.0838,
    entry_zone_high: 1.0845,
    stop_loss: 1.0810,
    take_profit: 1.0910,
    risk_reward_ratio: 2.5,
    smc_pattern: "OB+BOS",
    indicators: ["EMA_50", "RSI_14", "ATR"],
    status: "pending",
    created_at: new Date(Date.now() - 900000).toISOString(),
    expires_at: new Date(Date.now() + 3600000).toISOString(),
  },
  {
    id: "sig-002",
    pair: "GBPJPY",
    direction: "sell",
    confidence: 0.79,
    entry_zone_low: 196.38,
    entry_zone_high: 196.52,
    stop_loss: 196.90,
    take_profit: 195.40,
    risk_reward_ratio: 1.88,
    smc_pattern: "FVG+CHoCH",
    indicators: ["MACD", "ATR"],
    status: "executed",
    created_at: new Date(Date.now() - 90000000).toISOString(),
    expires_at: null,
  },
];

router.get("/v1/signals", (_req, res) => {
  res.json({ items: STUB_SIGNALS, total: STUB_SIGNALS.length, page: 1, limit: 50 });
});

router.get("/v1/signals/active", (_req, res) => {
  res.json(STUB_SIGNALS.filter((s) => s.status === "pending"));
});

router.get("/v1/signals/:id", (req, res) => {
  const sig = STUB_SIGNALS.find((s) => s.id === req.params.id) ?? STUB_SIGNALS[0];
  res.json(sig);
});

// ── Market ──────────────────────────────────────────────────────────────────

const MARKET_PAIRS = [
  { symbol: "EURUSD", bid: 1.0841, ask: 1.0843, spread: 0.2, change_24h: 0.12, volatility: 0.42, trend: "bullish", updated_at: new Date().toISOString() },
  { symbol: "GBPUSD", bid: 1.2734, ask: 1.2736, spread: 0.2, change_24h: -0.08, volatility: 0.58, trend: "bearish", updated_at: new Date().toISOString() },
  { symbol: "USDJPY", bid: 149.82, ask: 149.84, spread: 0.2, change_24h: 0.31, volatility: 0.61, trend: "bullish", updated_at: new Date().toISOString() },
  { symbol: "GBPJPY", bid: 196.38, ask: 196.42, spread: 0.4, change_24h: 0.21, volatility: 0.87, trend: "ranging", updated_at: new Date().toISOString() },
  { symbol: "AUDUSD", bid: 0.6421, ask: 0.6423, spread: 0.2, change_24h: -0.15, volatility: 0.39, trend: "bearish", updated_at: new Date().toISOString() },
];

router.get("/v1/market/pairs", (_req, res) => {
  res.json(MARKET_PAIRS);
});

router.get("/v1/market/scan", (_req, res) => {
  res.json([
    { pair: "EURUSD", direction: "buy", score: 0.87, smc_pattern: "OB+BOS", timeframe: "H4", confluence_factors: ["Order Block", "Break of Structure", "EMA 50 support"], detected_at: new Date().toISOString() },
    { pair: "GBPJPY", direction: "sell", score: 0.74, smc_pattern: "FVG", timeframe: "H1", confluence_factors: ["Fair Value Gap", "RSI overbought"], detected_at: new Date().toISOString() },
  ]);
});

// ── Backtests ───────────────────────────────────────────────────────────────

router.get("/v1/backtests", (_req, res) => {
  res.json([
    {
      id: "bt-001",
      strategy_id: "smc-v1",
      pair: "EURUSD",
      from_date: "2024-01-01",
      to_date: "2024-06-30",
      status: "completed",
      initial_balance: 10000,
      final_balance: 11342,
      total_trades: 124,
      winning_trades: 77,
      losing_trades: 47,
      win_rate: 62.1,
      profit_factor: 1.78,
      max_drawdown: 4.2,
      net_pnl: 1342,
      sharpe_ratio: 1.24,
      created_at: new Date(Date.now() - 86400000 * 7).toISOString(),
      completed_at: new Date(Date.now() - 86400000 * 6).toISOString(),
    },
  ]);
});

router.post("/v1/backtests", (req, res) => {
  res.status(202).json({ id: "bt-new", ...req.body, status: "queued", created_at: new Date().toISOString() });
});

router.get("/v1/backtests/:id", (req, res) => {
  res.json({ id: req.params.id, strategy_id: "smc-v1", pair: "EURUSD", from_date: "2024-01-01", to_date: "2024-06-30", status: "queued", created_at: new Date().toISOString() });
});

// ── News ────────────────────────────────────────────────────────────────────

const STUB_NEWS = [
  { id: "news-001", headline: "US Non-Farm Payrolls", source: "ForexFactory", impact: "high", currency: "USD", actual: "227K", forecast: "200K", previous: "183K", published_at: new Date(Date.now() + 3600000 * 6).toISOString() },
  { id: "news-002", headline: "ECB Interest Rate Decision", source: "Investing.com", impact: "high", currency: "EUR", actual: null, forecast: "4.25%", previous: "4.50%", published_at: new Date(Date.now() + 3600000 * 24).toISOString() },
  { id: "news-003", headline: "UK CPI y/y", source: "ForexFactory", impact: "medium", currency: "GBP", actual: "3.2%", forecast: "3.1%", previous: "3.4%", published_at: new Date(Date.now() - 3600000 * 2).toISOString() },
];

router.get("/v1/news", (_req, res) => {
  res.json(STUB_NEWS);
});

router.get("/v1/news/upcoming", (_req, res) => {
  res.json(STUB_NEWS.filter((n) => n.impact === "high" && new Date(n.published_at) > new Date()));
});

// ── Settings ────────────────────────────────────────────────────────────────

router.get("/v1/settings", (_req, res) => {
  res.json({
    risk_per_trade: 1.0,
    max_open_trades: 5,
    max_daily_loss: 5.0,
    allowed_pairs: ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "AUDUSD"],
    trading_enabled: false,
    news_filter_enabled: true,
    mt5_connected: false,
    mt5_account: null,
    mt5_server: null,
    min_confidence: 0.75,
    default_lot_size: 0.01,
  });
});

router.patch("/v1/settings", (req, res) => {
  res.json({ risk_per_trade: 1.0, max_open_trades: 5, max_daily_loss: 5.0, allowed_pairs: ["EURUSD"], trading_enabled: false, news_filter_enabled: true, mt5_connected: false, mt5_account: null, mt5_server: null, min_confidence: 0.75, default_lot_size: 0.01, ...req.body });
});

// ── Logs ────────────────────────────────────────────────────────────────────

const STUB_LOGS = [
  { id: "log-001", level: "info", module: "MarketScanner", message: "Scan complete — 2 opportunities found on EURUSD, GBPJPY", metadata: null, created_at: new Date(Date.now() - 60000).toISOString() },
  { id: "log-002", level: "info", module: "AIEngine", message: "Signal generated: EURUSD BUY confidence=0.87", metadata: { pair: "EURUSD", confidence: 0.87 }, created_at: new Date(Date.now() - 120000).toISOString() },
  { id: "log-003", level: "warning", module: "NewsFilter", message: "Trading suppressed — NFP release in 6 hours", metadata: { event: "NFP", currency: "USD" }, created_at: new Date(Date.now() - 600000).toISOString() },
  { id: "log-004", level: "info", module: "RiskManager", message: "Trade validated: EURUSD BUY 0.1 lots", metadata: null, created_at: new Date(Date.now() - 3600000).toISOString() },
  { id: "log-005", level: "error", module: "MT5Integration", message: "Connection to broker lost — reconnecting", metadata: { attempt: 1 }, created_at: new Date(Date.now() - 7200000).toISOString() },
];

router.get("/v1/logs", (_req, res) => {
  res.json({ items: STUB_LOGS, total: STUB_LOGS.length, page: 1, limit: 100 });
});

router.get("/v1/logs/errors", (_req, res) => {
  res.json(STUB_LOGS.filter((l) => l.level === "error" || l.level === "critical"));
});

export default router;
