/**
 * Charts page — live candlestick chart using lightweight-charts (TradingView).
 *
 * Data comes from GET /api/v1/candles — the same backend pipeline used by the bot.
 * No synthetic candles. MT5 unavailable → error state shown clearly.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, ColorType, CandlestickSeries } from "lightweight-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { RefreshCw, Maximize2, AlertTriangle, TrendingUp } from "lucide-react";
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

function buildUrl(pair: string, tf: string): string {
  const base = import.meta.env.BASE_URL?.replace(/\/$/, "") ?? "";
  return `${base}/api/v1/candles?pair=${pair}&timeframe=${tf}&count=300`;
}

export default function ChartsPage() {
  const { theme } = useTheme();
  const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef         = useRef<ReturnType<InstanceType<typeof CandlestickSeries>["applyOptions"]> | null>(null);

  const [pair, setPair]       = useState("EURUSD");
  const [tf, setTf]           = useState("H1");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);

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

    const candleSeries = chart.addCandlestickSeries({
      upColor:          upClr,
      downColor:        downClr,
      borderUpColor:    upClr,
      borderDownColor:  downClr,
      wickUpColor:      upClr,
      wickDownColor:    downClr,
    });

    chartRef.current   = chart;
    seriesRef.current  = candleSeries;

    const observer = new ResizeObserver(() => {
      if (container) chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current  = null;
      seriesRef.current = null;
    };
  }, [bg, textClr, gridClr]);

  // Apply theme changes
  useEffect(() => {
    chartRef.current?.applyOptions({
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: textClr },
      grid:   { vertLines: { color: gridClr }, horzLines: { color: gridClr } },
    });
  }, [bg, textClr, gridClr]);

  // Push data to chart
  useEffect(() => {
    if (!seriesRef.current || candles.length === 0) return;
    seriesRef.current.setData(candles as any);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  return (
    <div className="space-y-4 animate-in fade-in duration-500 h-[calc(100vh-120px)] flex flex-col">
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Live Chart</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Candlestick data from backend market pipeline</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchCandles} disabled={loading}
          className="h-8 text-[10px] font-bold uppercase tracking-widest border-border/50 bg-card/50">
          <RefreshCw className={cn("w-3 h-3 mr-1.5", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-6 flex-shrink-0">
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

      {/* Chart */}
      <Card className="flex-1 min-h-0 bg-card/50 border-border/50 shadow-lg overflow-hidden">
        <CardHeader className="border-b border-border/50 pb-3 pt-3 px-5 flex flex-row items-center gap-3">
          <TrendingUp className="w-4 h-4 text-primary" />
          <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            {pair} · {tf}
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
