/**
 * Charts page — live candlestick chart using lightweight-charts (TradingView).
 *
 * Data comes from GET /api/v1/candles — the same backend pipeline used by the bot.
 * Chart overlays: EMA 20, EMA 50, SMC structures (Order Blocks, BOS, CHoCH, FVG).
 * No synthetic candles. MT5 unavailable → error state shown clearly.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, ColorType, CandlestickSeries, LineSeries } from "lightweight-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { RefreshCw, TrendingUp, Layers, AlertTriangle } from "lucide-react";
import { useTheme } from "@/components/theme-provider";

const PAIRS = [
  "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD",
  "USDCAD","NZDUSD","EURJPY","GBPJPY","EURGBP",
];
const TIMEFRAMES = ["M1","M5","M15","M30","H1","H4","D1"];

type Candle = {
  time:  number;
  open:  number;
  high:  number;
  low:   number;
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

export default function ChartsPage() {
  const { theme } = useTheme();
  const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef         = useRef<ReturnType<InstanceType<typeof CandlestickSeries>["applyOptions"]> | null>(null);
  const ema20SeriesRef    = useRef<any>(null);
  const ema50SeriesRef    = useRef<any>(null);
  const priceLinesRef     = useRef<any[]>([]);

  const [pair, setPair]       = useState("EURUSD");
  const [tf, setTf]           = useState("H1");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);

  // Overlays state (Section 11.4)
  const [showEma20, setShowEma20] = useState(true);
  const [showEma50, setShowEma50] = useState(true);
  const [showSmc, setShowSmc]     = useState(true);
  const [smcStructures, setSmcStructures] = useState<SMCStructure[]>([]);

  // Chart colours driven by theme
  const bg       = isDark ? "#0f0f0f" : "#ffffff";
  const textClr  = isDark ? "#94a3b8" : "#64748b";
  const gridClr  = isDark ? "#1e293b" : "#f1f5f9";
  const upClr    = "#10b981";
  const downClr  = "#ef4444";

  // Fetch candles from backend
  const fetchCandles = useCallback(async () => {
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

      // Also attempt to fetch SMC structures for this pair/timeframe
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
  }, [pair, tf]);

  useEffect(() => { fetchCandles(); }, [fetchCandles]);

  // Create chart
  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: bg },
        textColor:   textClr,
        fontSize:    11,
      },
      grid: {
        vertLines:   { color: gridClr },
        horzLines:   { color: gridClr },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: gridClr },
      timeScale: {
        borderColor:     gridClr,
        timeVisible:     true,
        secondsVisible:  false,
      },
      width:  container.clientWidth,
      height: container.clientHeight,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:          upClr,
      downColor:        downClr,
      borderUpColor:    upClr,
      borderDownColor:  downClr,
      wickUpColor:      upClr,
      wickDownColor:    downClr,
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

    chartRef.current       = chart;
    seriesRef.current      = candleSeries;
    ema20SeriesRef.current = ema20Series;
    ema50SeriesRef.current = ema50Series;

    const observer = new ResizeObserver(() => {
      if (container) chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current       = null;
      seriesRef.current      = null;
      ema20SeriesRef.current = null;
      ema50SeriesRef.current = null;
      priceLinesRef.current  = [];
    };
  }, [bg, textClr, gridClr]);

  // Apply theme changes
  useEffect(() => {
    chartRef.current?.applyOptions({
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: textClr },
      grid:   { vertLines: { color: gridClr }, horzLines: { color: gridClr } },
    });
  }, [bg, textClr, gridClr]);

  // Push data & overlays to chart
  useEffect(() => {
    if (!seriesRef.current || candles.length === 0) return;
    seriesRef.current.setData(candles as any);

    // EMA overlays
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

    // SMC Price lines / markers overlay
    // Clear old lines
    if (seriesRef.current) {
      for (const line of priceLinesRef.current) {
        try {
          seriesRef.current.removePriceLine(line);
        } catch {}
      }
      priceLinesRef.current = [];

      if (showSmc && smcStructures.length > 0) {
        // Take top 4 most relevant structures
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
  }, [candles, showEma20, showEma50, showSmc, smcStructures]);

  return (
    <div className="space-y-4 animate-in fade-in duration-500 h-[calc(100vh-120px)] flex flex-col">
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Live Chart & Overlays</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Real-time candles with EMA and SMC structural zones</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchCandles} disabled={loading}
          className="h-8 text-[10px] font-bold uppercase tracking-widest border-border/50 bg-card/50">
          <RefreshCw className={cn("w-3 h-3 mr-1.5", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* Controls & Overlays Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-4 flex-shrink-0">
        <div className="flex items-center gap-6">
          {/* Pair selector */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Pair</span>
            <div className="flex gap-1 flex-wrap">
              {PAIRS.map(p => (
                <button key={p} onClick={() => setPair(p)}
                  className={cn("px-2 py-1 rounded text-[10px] font-mono font-bold tracking-wide transition-all",
                    pair === p ? "bg-primary text-primary-foreground" : "bg-muted/50 text-muted-foreground hover:bg-muted"
                  )}>
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Timeframe selector */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">TF</span>
            <div className="flex gap-1">
              {TIMEFRAMES.map(t => (
                <button key={t} onClick={() => setTf(t)}
                  className={cn("px-2 py-1 rounded text-[10px] font-mono font-bold tracking-wide transition-all",
                    tf === t ? "bg-primary text-primary-foreground" : "bg-muted/50 text-muted-foreground hover:bg-muted"
                  )}>
                  {t}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Overlays toggle buttons (Section 11.4) */}
        <div className="flex items-center gap-2 bg-card/60 border border-border/50 rounded-lg p-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground px-2 flex items-center gap-1">
            <Layers className="w-3 h-3 text-primary" /> Overlays:
          </span>
          <button
            onClick={() => setShowEma20(v => !v)}
            className={cn("px-2.5 py-1 rounded text-[10px] font-mono font-bold transition-all",
              showEma20 ? "bg-sky-500/20 text-sky-400 border border-sky-500/40" : "text-muted-foreground hover:bg-muted/50"
            )}>
            EMA 20
          </button>
          <button
            onClick={() => setShowEma50(v => !v)}
            className={cn("px-2.5 py-1 rounded text-[10px] font-mono font-bold transition-all",
              showEma50 ? "bg-amber-500/20 text-amber-400 border border-amber-500/40" : "text-muted-foreground hover:bg-muted/50"
            )}>
            EMA 50
          </button>
          <button
            onClick={() => setShowSmc(v => !v)}
            className={cn("px-2.5 py-1 rounded text-[10px] font-mono font-bold transition-all",
              showSmc ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40" : "text-muted-foreground hover:bg-muted/50"
            )}>
            SMC Zones
          </button>
        </div>
      </div>

      {/* Chart */}
      <Card className="flex-1 min-h-0 bg-card/50 border-border/50 shadow-lg overflow-hidden">
        <CardHeader className="border-b border-border/50 pb-3 pt-3 px-5 flex flex-row items-center gap-3">
          <TrendingUp className="w-4 h-4 text-primary" />
          <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            {pair} · {tf}
            {smcStructures.length > 0 && showSmc && (
              <Badge variant="outline" className="text-[9px] border-emerald-500/40 text-emerald-400 font-mono">
                {smcStructures.length} SMC Zones active
              </Badge>
            )}
          </CardTitle>
          {loading && (
            <div className="flex items-center gap-2 ml-auto">
              <RefreshCw className="w-3 h-3 animate-spin text-muted-foreground" />
              <span className="text-[10px] font-mono text-muted-foreground">Loading...</span>
            </div>
          )}
        </CardHeader>
        <CardContent className="p-0 h-full">
          {error ? (
            <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
              <AlertTriangle className="w-10 h-10 text-amber-500" />
              <div className="text-center space-y-2">
                <p className="font-mono font-bold text-sm text-foreground">MT5 DATA UNAVAILABLE</p>
                <p className="text-xs text-muted-foreground max-w-sm">{error}</p>
                <p className="text-[10px] text-muted-foreground/60 font-mono">
                  Live charts require a Windows environment with MT5 terminal connected.
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={fetchCandles}
                className="text-[10px] font-bold uppercase tracking-widest">
                Retry
              </Button>
            </div>
          ) : (
            <div ref={chartContainerRef} className="w-full" style={{ height: "calc(100% - 0px)" }} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
