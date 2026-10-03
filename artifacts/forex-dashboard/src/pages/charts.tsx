/**
 * Charts page — Live TradingView Pro Chart & MT5 SMC Algorithmic Analyzer.
 *
 * Mode 1: TradingView Pro Chart — Complete TradingView Advanced Charting Platform
 *         with full left drawing tools, right price scale, indicators, timeframes,
 *         and bottom date range selectors (matches user specification).
 * Mode 2: MT5 Bot SMC Analyzer — Direct MetaTrader 5 broker candles with
 *         EMA 20, EMA 50, and Smart Money Concepts (SMC) order block overlays.
 */

import { useEffect, useRef, useState, useCallback, memo } from "react";
import { createChart, ColorType, CandlestickSeries, LineSeries } from "lightweight-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  RefreshCw,
  TrendingUp,
  Layers,
  AlertTriangle,
  Maximize2,
  BarChart2,
  Activity,
  Sliders,
} from "lucide-react";
import { useTheme } from "@/components/theme-provider";

const PAIRS = [
  "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
  "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
  "XAUUSD", "BTCUSD",
];

const TIMEFRAMES = [
  { label: "1m", value: "M1", tv: "1" },
  { label: "5m", value: "M5", tv: "5" },
  { label: "15m", value: "M15", tv: "15" },
  { label: "30m", value: "M30", tv: "30" },
  { label: "1h", value: "H1", tv: "60" },
  { label: "4h", value: "H4", tv: "240" },
  { label: "1D", value: "D1", tv: "D" },
];

function getTradingViewSymbol(pair: string): string {
  if (pair === "BTCUSD") return "BINANCE:BTCUSDT";
  if (pair === "XAUUSD") return "OANDA:XAUUSD";
  return `FX:${pair}`;
}

type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

type SMCStructure = {
  pattern: string;
  pair: string;
  timeframe: string;
  zone: string;
  price_low: number;
  price_high: number;
  direction: string;
  strength: number;
};

function buildUrl(pair: string, tf: string): string {
  const base = import.meta.env.BASE_URL?.replace(/\/$/, "") ?? "";
  return `${base}/api/v1/candles?pair=${pair}&timeframe=${tf}&count=300`;
}

function buildSmcUrl(pair: string, tf: string): string {
  const base = import.meta.env.BASE_URL?.replace(/\/$/, "") ?? "";
  return `${base}/api/v1/smc/structures?pair=${pair}&timeframe=${tf}`;
}

function computeEMA(candles: Candle[], period: number) {
  if (!candles || candles.length < period) return [];
  const k = 2 / (period + 1);
  let ema = candles.slice(0, period).reduce((acc, c) => acc + c.close, 0) / period;
  const result = [{ time: candles[period - 1].time as any, value: Number(ema.toFixed(5)) }];
  for (let i = period; i < candles.length; i++) {
    ema = candles[i].close * k + ema * (1 - k);
    result.push({ time: candles[i].time as any, value: Number(ema.toFixed(5)) });
  }
  return result;
}

/**
 * Official TradingView Advanced Real-Time Chart Widget
 * Includes full side price scale, left drawing tools, indicators, and time range bar.
 */
const TradingViewAdvancedWidget = memo(function TradingViewAdvancedWidget({
  symbol,
  interval,
  isDark,
}: {
  symbol: string;
  interval: string;
  isDark: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.innerHTML = "";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    widgetDiv.style.height = "100%";
    widgetDiv.style.width = "100%";
    container.appendChild(widgetDiv);

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: symbol,
      interval: interval,
      timezone: "Etc/UTC",
      theme: isDark ? "dark" : "light",
      style: "1",
      locale: "en",
      enable_publishing: false,
      allow_symbol_change: true,
      hide_side_toolbar: false,
      withdateranges: true,
      details: true,
      hotlist: false,
      calendar: false,
      show_popup_button: true,
      popup_width: "1000",
      popup_height: "650",
      support_host: "https://www.tradingview.com",
    });

    container.appendChild(script);

    return () => {
      if (container) {
        container.innerHTML = "";
      }
    };
  }, [symbol, interval, isDark]);

  return (
    <div
      ref={containerRef}
      className="tradingview-widget-container w-full h-full"
      style={{ height: "100%", width: "100%", minHeight: "620px" }}
    />
  );
});

export default function ChartsPage() {
  const { theme } = useTheme();
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  const [activeTab, setActiveTab] = useState<"tradingview" | "mt5">("tradingview");
  const [pair, setPair] = useState("EURUSD");
  const [tf, setTf] = useState("H1");

  // MT5 state
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<any>(null);
  const ema20SeriesRef = useRef<any>(null);
  const ema50SeriesRef = useRef<any>(null);
  const priceLinesRef = useRef<any[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);

  // Overlays state for MT5 mode
  const [showEma20, setShowEma20] = useState(true);
  const [showEma50, setShowEma50] = useState(true);
  const [showSmc, setShowSmc] = useState(true);
  const [smcStructures, setSmcStructures] = useState<SMCStructure[]>([]);

  // Chart colours driven by theme
  const bg = isDark ? "#0f0f0f" : "#ffffff";
  const textClr = isDark ? "#94a3b8" : "#64748b";
  const gridClr = isDark ? "#1e293b" : "#f1f5f9";
  const upClr = "#10b981";
  const downClr = "#ef4444";

  // TradingView interval lookup
  const currentTfObj = TIMEFRAMES.find((t) => t.value === tf) || TIMEFRAMES[4];
  const tvInterval = currentTfObj.tv;
  const tvSymbol = getTradingViewSymbol(pair);

  // Fetch candles for MT5 mode
  const fetchCandles = useCallback(async () => {
    if (activeTab !== "mt5") return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(buildUrl(pair, tf), {
        headers: { Authorization: `Bearer ${localStorage.getItem("nexus_access_token") ?? ""}` },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data: Candle[] = await res.json();
      setCandles(data);

      try {
        const smcRes = await fetch(buildSmcUrl(pair, tf), {
          headers: { Authorization: `Bearer ${localStorage.getItem("nexus_access_token") ?? ""}` },
        });
        if (smcRes.ok) {
          const smcData = await smcRes.json();
          setSmcStructures(smcData || []);
        }
      } catch {
        // SMC non-blocking
      }
    } catch (e: any) {
      setError(e.message ?? "Failed to load candles");
      setCandles([]);
    } finally {
      setLoading(false);
    }
  }, [pair, tf, activeTab]);

  useEffect(() => {
    if (activeTab === "mt5") {
      fetchCandles();
    }
  }, [fetchCandles, activeTab]);

  // Create MT5 chart
  useEffect(() => {
    if (activeTab !== "mt5") return;
    const container = chartContainerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: bg },
        textColor: textClr,
        fontSize: 11,
      },
      grid: {
        vertLines: { color: gridClr },
        horzLines: { color: gridClr },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: gridClr },
      timeScale: {
        borderColor: gridClr,
        timeVisible: true,
        secondsVisible: false,
      },
      width: container.clientWidth,
      height: container.clientHeight,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: upClr,
      downColor: downClr,
      borderUpColor: upClr,
      borderDownColor: downClr,
      wickUpColor: upClr,
      wickDownColor: downClr,
    });

    const ema20Series = chart.addSeries(LineSeries, {
      color: "#38bdf8",
      lineWidth: 1.5,
      title: "EMA 20",
    });

    const ema50Series = chart.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 1.5,
      title: "EMA 50",
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    ema20SeriesRef.current = ema20Series;
    ema50SeriesRef.current = ema50Series;

    const observer = new ResizeObserver(() => {
      if (container)
        chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      ema20SeriesRef.current = null;
      ema50SeriesRef.current = null;
      priceLinesRef.current = [];
    };
  }, [bg, textClr, gridClr, activeTab]);

  // Push MT5 data & overlays
  useEffect(() => {
    if (activeTab !== "mt5") return;
    if (!seriesRef.current || candles.length === 0) return;
    seriesRef.current.setData(candles as any);

    if (ema20SeriesRef.current) {
      if (showEma20) {
        ema20SeriesRef.current.setData(computeEMA(candles, 20));
        ema20SeriesRef.current.applyOptions({ visible: true });
      } else {
        ema20SeriesRef.current.applyOptions({ visible: false });
      }
    }

    if (ema50SeriesRef.current) {
      if (showEma50) {
        ema50SeriesRef.current.setData(computeEMA(candles, 50));
        ema50SeriesRef.current.applyOptions({ visible: true });
      } else {
        ema50SeriesRef.current.applyOptions({ visible: false });
      }
    }

    if (seriesRef.current) {
      for (const line of priceLinesRef.current) {
        try {
          seriesRef.current.removePriceLine(line);
        } catch {}
      }
      priceLinesRef.current = [];

      if (showSmc && smcStructures.length > 0) {
        const topStructures = smcStructures.slice(0, 4);
        for (const s of topStructures) {
          try {
            const isBullish = s.direction === "bullish";
            const line = seriesRef.current.createPriceLine({
              price: s.price_low || s.price_high,
              color: isBullish ? "#10b981" : "#ef4444",
              lineWidth: 1,
              lineStyle: 2,
              axisLabelVisible: true,
              title: `${s.pattern.replace(/_/g, " ").toUpperCase()}`,
            });
            priceLinesRef.current.push(line);
          } catch {}
        }
      }
    }

    chartRef.current?.timeScale().fitContent();
  }, [candles, showEma20, showEma50, showSmc, smcStructures, activeTab]);

  return (
    <div className="space-y-3 animate-in fade-in duration-500 min-h-[calc(100vh-100px)] flex flex-col">
      {/* Top Header & Mode Switcher */}
      <div className="flex items-center justify-between flex-wrap gap-3 flex-shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight">TradingView Real-Time Chart</h1>
            <Badge variant="outline" className="text-[10px] bg-primary/10 border-primary/30 text-primary font-mono">
              Live Pro
            </Badge>
          </div>
          <p className="text-muted-foreground text-xs mt-0.5">
            Interactive chart with full drawing tools, indicators, side price scale, and date ranges
          </p>
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center bg-card/80 border border-border/60 rounded-lg p-1 shadow-sm">
          <button
            onClick={() => setActiveTab("tradingview")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all",
              activeTab === "tradingview"
                ? "bg-primary text-primary-foreground shadow"
                : "text-muted-foreground hover:bg-muted/60"
            )}
          >
            <BarChart2 className="w-3.5 h-3.5" />
            TradingView Pro
          </button>
          <button
            onClick={() => setActiveTab("mt5")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all",
              activeTab === "mt5"
                ? "bg-primary text-primary-foreground shadow"
                : "text-muted-foreground hover:bg-muted/60"
            )}
          >
            <Activity className="w-3.5 h-3.5" />
            MT5 SMC Bot Analyzer
          </button>
        </div>
      </div>

      {/* Symbol & Timeframe Selection Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3 bg-card/60 border border-border/50 rounded-lg p-2.5 shadow-sm flex-shrink-0">
        <div className="flex items-center gap-4 flex-wrap">
          {/* Pair selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mr-1">
              Symbol:
            </span>
            <div className="flex gap-1 flex-wrap">
              {PAIRS.map((p) => (
                <button
                  key={p}
                  onClick={() => setPair(p)}
                  className={cn(
                    "px-2.5 py-1 rounded text-xs font-mono font-bold tracking-wide transition-all",
                    pair === p
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "bg-muted/40 text-muted-foreground hover:bg-muted/80"
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Timeframe selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mr-1">
              TF:
            </span>
            <div className="flex gap-1">
              {TIMEFRAMES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setTf(t.value)}
                  className={cn(
                    "px-2.5 py-1 rounded text-xs font-mono font-bold tracking-wide transition-all",
                    tf === t.value
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "bg-muted/40 text-muted-foreground hover:bg-muted/80"
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right side controls */}
        {activeTab === "mt5" ? (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-muted/40 border border-border/40 rounded-md p-0.5">
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground px-2 flex items-center gap-1">
                <Layers className="w-3 h-3 text-primary" /> Overlays:
              </span>
              <button
                onClick={() => setShowEma20((v) => !v)}
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all",
                  showEma20
                    ? "bg-sky-500/20 text-sky-400 border border-sky-500/40"
                    : "text-muted-foreground hover:bg-muted/50"
                )}
              >
                EMA 20
              </button>
              <button
                onClick={() => setShowEma50((v) => !v)}
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all",
                  showEma50
                    ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
                    : "text-muted-foreground hover:bg-muted/50"
                )}
              >
                EMA 50
              </button>
              <button
                onClick={() => setShowSmc((v) => !v)}
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all",
                  showSmc
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                    : "text-muted-foreground hover:bg-muted/50"
                )}
              >
                SMC
              </button>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchCandles}
              disabled={loading}
              className="h-7 text-[10px] font-bold uppercase tracking-widest"
            >
              <RefreshCw className={cn("w-3 h-3 mr-1", loading && "animate-spin")} />
              Sync MT5
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1 text-[11px] font-mono bg-emerald-500/10 text-emerald-400 px-2.5 py-1 rounded-md border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Live Feed Connected
            </span>
          </div>
        )}
      </div>

      {/* Main Chart Card */}
      <Card className="flex-1 min-h-[640px] bg-card/60 border-border/50 shadow-xl overflow-hidden flex flex-col">
        <CardContent className="p-0 flex-1 w-full h-full min-h-[640px]">
          {activeTab === "tradingview" ? (
            <div className="w-full h-full min-h-[640px]">
              <TradingViewAdvancedWidget
                symbol={tvSymbol}
                interval={tvInterval}
                isDark={isDark}
              />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[500px] gap-4 p-8">
              <AlertTriangle className="w-10 h-10 text-amber-500" />
              <div className="text-center space-y-2">
                <p className="font-mono font-bold text-sm text-foreground">MT5 DATA UNAVAILABLE</p>
                <p className="text-xs text-muted-foreground max-w-sm">{error}</p>
                <p className="text-[10px] text-muted-foreground/60 font-mono">
                  Live charts require a Windows environment with MT5 terminal connected.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchCandles}
                className="text-[10px] font-bold uppercase tracking-widest"
              >
                Retry
              </Button>
            </div>
          ) : (
            <div
              ref={chartContainerRef}
              className="w-full h-full min-h-[640px]"
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
