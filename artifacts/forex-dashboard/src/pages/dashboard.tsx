import { useState } from "react";
import { useGetDashboardSummary, useGetDashboardPerformance, useGetActiveSignals } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatNumber, formatPercent, cn } from "@/lib/utils";
import {
  Activity,
  DollarSign,
  Target,
  TrendingUp,
  TrendingDown,
  TriangleAlert as AlertTriangle,
  RefreshCw,
  Server,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Wallet,
  ArrowUpRight,
  ArrowDownRight,
  Layers,
  Sliders,
  Percent,
  Lock,
  Zap,
} from "lucide-react";
import { ResponsiveContainer, Area, AreaChart, CartesianGrid, XAxis, YAxis, Tooltip } from "recharts";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";

// ─── MT5 Types ───────────────────────────────────────────────────────────────

type MT5Account = {
  login: number;
  server: string;
  company: string;
  currency: string;
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  margin_level: number;
  leverage: number;
  floating_pnl: number;
  trade_allowed: boolean;
  trade_expert: boolean;
  connected: boolean;
  checked_at: string;
};

type MT5Position = {
  ticket: number;
  symbol: string;
  direction: "buy" | "sell";
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  floating_pnl: number;
  swap: number;
  magic: number;
  open_time: string;
  comment: string;
};

type MT5Deal = {
  ticket: number;
  order: number;
  symbol: string;
  direction: string;
  entry: string;
  volume: number;
  price: number;
  profit: number;
  commission: number;
  swap: number;
  net_profit: number;
  close_time: string;
  magic: number;
  comment: string;
};

type MT5Stats = {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_realized_profit: number;
  total_realized_loss: number;
  net_realized_pnl: number;
  today_realized_pnl: number;
  today_trades_count: number;
  open_positions_count: number;
  total_floating_pnl: number;
  account_balance: number;
  account_equity: number;
  free_margin: number;
  margin_level: number;
  connected: boolean;
};

type MT5Summary = {
  connected: boolean;
  account: MT5Account | null;
  positions: MT5Position[];
  history: MT5Deal[];
  stats: MT5Stats;
  timestamp: string;
};

async function fetchMT5Summary(): Promise<MT5Summary> {
  const token = localStorage.getItem("forex_access_token") || localStorage.getItem("nexus_access_token");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch("/api/v1/mt5/summary?days=30", { headers });
  if (!res.ok) {
    throw new Error(`Failed to fetch MT5 summary: ${res.status}`);
  }
  return res.json();
}

function formatDateTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function DashboardPage() {
  const { data: summary, isLoading: isSummaryLoading } = useGetDashboardSummary();
  const { data: performance, isLoading: isPerfLoading } = useGetDashboardPerformance({ period: "30d" });
  const { data: activeSignals, isLoading: isSignalsLoading } = useGetActiveSignals();

  // MT5 live summary with safe 5-second polling
  const {
    data: mt5Data,
    isLoading: isMT5Loading,
    refetch: refetchMT5,
    isFetching: isMT5Fetching,
  } = useQuery<MT5Summary>({
    queryKey: ["mt5-summary"],
    queryFn: fetchMT5Summary,
    refetchInterval: 5000,
    retry: 2,
  });

  const account = mt5Data?.account;
  const stats = mt5Data?.stats;
  const positions = mt5Data?.positions ?? [];
  const history = mt5Data?.history ?? [];
  const isConnected = mt5Data?.connected ?? false;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
      {/* ─── Top Terminal Header ────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/50 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-foreground font-mono">
              Command Center
            </h1>
            <Badge variant="terminal" className="text-[10px] tracking-widest uppercase">
              LIVE TELEMETRY
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1 font-mono">
            MetaTrader 5 execution bridge · Institutional portfolio metrics · AI algorithmic telemetry
          </p>
        </div>

        <div className="flex items-center flex-wrap gap-2.5">
          {/* MT5 Connection Badge */}
          <div className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs font-mono font-medium transition-all shadow-2xs",
            isConnected
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
              : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
          )}>
            <div className={cn(
              "w-2 h-2 rounded-full",
              isConnected ? "bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]" : "bg-rose-500"
            )} />
            <span>
              {isMT5Loading ? "CONNECTING..." : isConnected ? "MT5 CONNECTED" : "MT5 OFFLINE"}
            </span>
            {account && (
              <span className="text-muted-foreground border-l border-border/60 pl-2 text-[11px]">
                {account.server} · #{account.login}
              </span>
            )}
          </div>

          {/* Sync MT5 Action */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetchMT5()}
            disabled={isMT5Fetching}
            className="h-8 gap-1.5 text-xs font-mono border-border/60 bg-card/60 hover:bg-card hover:border-primary/40 cursor-pointer shadow-2xs"
            title="Refresh MT5 data from terminal"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", isMT5Fetching && "animate-spin text-primary")} />
            <span>{isMT5Fetching ? "SYNCING..." : "SYNC"}</span>
          </Button>

          {/* Bot Engine State */}
          <div className="flex items-center gap-2 px-2.5 py-1.5 bg-card/60 border border-border/50 rounded-md shadow-2xs text-xs font-mono">
            <div className={cn(
              "w-2 h-2 rounded-full",
              isSummaryLoading ? "bg-muted-foreground" :
              summary?.botStatus === "running" ? "bg-emerald-500 animate-pulse" :
              summary?.botStatus === "paused" ? "bg-amber-500" : "bg-rose-500"
            )} />
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              {isSummaryLoading ? "---" : summary?.botStatus || "ACTIVE"}
            </span>
          </div>
        </div>
      </div>

      {/* ─── MT5 Account Snapshot Bar ─────────────────────────────────────── */}
      <Card className="border-border/60 bg-card/60 backdrop-blur-sm shadow-sm overflow-hidden">
        <CardHeader className="py-2.5 px-5 border-b border-border/40 bg-muted/20 flex flex-row items-center justify-between">
          <div className="flex items-center gap-2">
            <Server className="w-3.5 h-3.5 text-primary" />
            <span className="text-[11px] font-mono font-bold uppercase tracking-widest text-muted-foreground">
              MetaTrader 5 Account Telemetry
            </span>
          </div>
          {account && (
            <div className="hidden sm:flex items-center gap-4 text-[11px] font-mono text-muted-foreground">
              <span>Login: <strong className="text-foreground">#{account.login}</strong></span>
              <span>Server: <strong className="text-foreground">{account.server}</strong></span>
              <span>Leverage: <strong className="text-foreground">1:{account.leverage}</strong></span>
              <span>Company: <strong className="text-foreground">{account.company || "Exness"}</strong></span>
            </div>
          )}
        </CardHeader>
        <CardContent className="p-4 sm:p-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            <MT5MetricItem
              label="BALANCE"
              value={account ? `$${account.balance.toFixed(2)}` : "---"}
              sub="Closed Funds"
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="EQUITY"
              value={account ? `$${account.equity.toFixed(2)}` : "---"}
              sub="Live Capital"
              highlight
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="FREE MARGIN"
              value={account ? `$${account.free_margin.toFixed(2)}` : "---"}
              sub="Available"
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="FLOATING P/L"
              value={account ? (account.floating_pnl > 0 ? `+$${account.floating_pnl.toFixed(2)}` : `$${account.floating_pnl.toFixed(2)}`) : "---"}
              sub="Open Positions"
              valueColor={
                !account || account.floating_pnl === 0 ? "text-muted-foreground" :
                account.floating_pnl > 0 ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"
              }
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="TODAY REALIZED"
              value={stats ? (stats.today_realized_pnl > 0 ? `+$${stats.today_realized_pnl.toFixed(2)}` : `$${stats.today_realized_pnl.toFixed(2)}`) : "---"}
              sub="Closed Today"
              valueColor={
                !stats || stats.today_realized_pnl === 0 ? "text-muted-foreground" :
                stats.today_realized_pnl > 0 ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"
              }
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="NET REALIZED"
              value={stats ? (stats.net_realized_pnl > 0 ? `+$${stats.net_realized_pnl.toFixed(2)}` : `$${stats.net_realized_pnl.toFixed(2)}`) : "---"}
              sub="30d Closed P/L"
              valueColor={
                !stats || stats.net_realized_pnl === 0 ? "text-muted-foreground" :
                stats.net_realized_pnl > 0 ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"
              }
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="WIN RATE"
              value={stats ? `${stats.win_rate}%` : "---"}
              sub={`${stats?.winning_trades || 0}W / ${stats?.losing_trades || 0}L`}
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="OPEN TRADES"
              value={stats ? `${stats.open_positions_count}` : "---"}
              sub="Active in MT5"
              loading={isMT5Loading}
            />
          </div>
        </CardContent>
      </Card>

      {/* ─── P/L Distinction & Risk Controls Banner ────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Floating P/L Explainer */}
        <div className="flex items-start gap-3 p-3.5 rounded-lg border border-primary/25 bg-card/40 text-xs font-mono">
          <Layers className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <div className="font-bold text-foreground tracking-wide">FLOATING P/L (Unrealized)</div>
            <p className="text-muted-foreground leading-relaxed text-[11px]">
              Fluctuates in real time with live broker ticks on active open positions. Does not affect account balance until position is closed.
            </p>
          </div>
        </div>

        {/* Realized P/L Explainer */}
        <div className="flex items-start gap-3 p-3.5 rounded-lg border border-emerald-500/25 bg-card/40 text-xs font-mono">
          <ShieldCheck className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <div className="font-bold text-foreground tracking-wide">REALIZED P/L (Settled)</div>
            <p className="text-muted-foreground leading-relaxed text-[11px]">
              Confirmed profit or loss from completed MT5 deals, including commissions and swaps. Settled permanently into account balance.
            </p>
          </div>
        </div>

        {/* Risk Management Overview Card */}
        <div className="flex items-start gap-3 p-3.5 rounded-lg border border-border/60 bg-card/40 text-xs font-mono">
          <Sliders className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="space-y-1 w-full">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground tracking-wide">RISK CONTROLS</span>
              <span className="text-[10px] text-emerald-500 dark:text-emerald-400 font-bold">FAIL-CLOSED</span>
            </div>
            <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[11px] text-muted-foreground pt-0.5">
              <span>Risk/Trade: <strong className="text-foreground">1.0%</strong></span>
              <span>Target R:R: <strong className="text-foreground">1:2.0</strong></span>
              <span>Max Trades: <strong className="text-foreground">5 Open</strong></span>
              <span>Daily Loss: <strong className="text-foreground">5.0% Limit</strong></span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── MT5 Open Positions Section ───────────────────────────────────── */}
      <Card className="border-border/60 bg-card/60 backdrop-blur-sm shadow-sm overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between py-3 px-5 border-b border-border/40 bg-muted/20">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            <CardTitle className="text-xs font-mono font-bold uppercase tracking-wider text-foreground">
              Live Open Positions (MetaTrader 5)
            </CardTitle>
            <Badge variant="terminal" className="text-[10px] ml-1">
              {positions.length} ACTIVE
            </Badge>
          </div>
          <div className="text-xs font-mono text-muted-foreground flex items-center gap-2">
            <span>Floating Net:</span>
            <span className={cn(
              "font-bold text-sm",
              (stats?.total_floating_pnl ?? 0) > 0 ? "text-emerald-500 dark:text-emerald-400" :
              (stats?.total_floating_pnl ?? 0) < 0 ? "text-rose-500 dark:text-rose-400" : "text-muted-foreground"
            )}>
              {(stats?.total_floating_pnl ?? 0) > 0 ? `+$${(stats?.total_floating_pnl ?? 0).toFixed(2)}` : `$${(stats?.total_floating_pnl ?? 0).toFixed(2)}`}
            </span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30 border-b border-border/40">
                <TableHead className="w-[100px] pl-5 font-mono text-[11px]">Ticket</TableHead>
                <TableHead className="font-mono text-[11px]">Symbol</TableHead>
                <TableHead className="font-mono text-[11px]">Direction</TableHead>
                <TableHead className="font-mono text-[11px]">Volume</TableHead>
                <TableHead className="font-mono text-[11px]">Open Price</TableHead>
                <TableHead className="font-mono text-[11px]">Current Price</TableHead>
                <TableHead className="font-mono text-[11px]">Stop Loss</TableHead>
                <TableHead className="font-mono text-[11px]">Take Profit</TableHead>
                <TableHead className="font-mono text-[11px]">Swap</TableHead>
                <TableHead className="font-mono text-[11px]">Floating P/L</TableHead>
                <TableHead className="pr-5 font-mono text-[11px]">Open Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isMT5Loading ? (
                Array.from({ length: 2 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-5"><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-14" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-14" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell className="pr-5"><Skeleton className="h-4 w-24" /></TableCell>
                  </TableRow>
                ))
              ) : positions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={11} className="h-24 text-center text-muted-foreground border-dashed">
                    <div className="flex flex-col items-center justify-center gap-1.5 opacity-80">
                      <Clock className="w-5 h-5 text-muted-foreground/60" />
                      <span className="font-mono text-xs font-semibold text-foreground">NO OPEN POSITIONS IN MT5</span>
                      <span className="text-[11px] text-muted-foreground font-mono">Demo account ready. Algorithmic trade scanner running.</span>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                positions.map((p) => (
                  <TableRow key={p.ticket} className="font-mono text-xs hover:bg-muted/30 transition-colors">
                    <TableCell className="pl-5 font-bold text-foreground">#{p.ticket}</TableCell>
                    <TableCell className="font-bold text-primary">{p.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={p.direction === "buy" ? "buy" : "sell"} className="text-[10px] uppercase font-bold px-2 py-0.5">
                        {p.direction}
                      </Badge>
                    </TableCell>
                    <TableCell>{p.volume.toFixed(2)} lots</TableCell>
                    <TableCell>{p.open_price.toFixed(5)}</TableCell>
                    <TableCell>{p.current_price.toFixed(5)}</TableCell>
                    <TableCell className="text-muted-foreground">{p.sl > 0 ? p.sl.toFixed(5) : "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{p.tp > 0 ? p.tp.toFixed(5) : "—"}</TableCell>
                    <TableCell>{p.swap ? `$${p.swap.toFixed(2)}` : "$0.00"}</TableCell>
                    <TableCell className={cn(
                      "font-bold text-sm",
                      p.floating_pnl > 0 ? "text-emerald-500 dark:text-emerald-400" :
                      p.floating_pnl < 0 ? "text-rose-500 dark:text-rose-400" : "text-muted-foreground"
                    )}>
                      {p.floating_pnl > 0 ? `+$${p.floating_pnl.toFixed(2)}` : `$${p.floating_pnl.toFixed(2)}`}
                    </TableCell>
                    <TableCell className="pr-5 text-muted-foreground text-[11px]">
                      {formatDateTime(p.open_time)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ─── MT5 Closed Trade History Section ─────────────────────────────── */}
      <Card className="border-border/60 bg-card/60 backdrop-blur-sm shadow-sm overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between py-3 px-5 border-b border-border/40 bg-muted/20">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
            <CardTitle className="text-xs font-mono font-bold uppercase tracking-wider text-foreground">
              Closed Trade History (MT5 Deals)
            </CardTitle>
            <Badge variant="terminal" className="text-[10px] ml-1">
              {history.length} EXECUTED
            </Badge>
          </div>
          <div className="text-xs font-mono text-muted-foreground flex items-center gap-2">
            <span>Net Realized:</span>
            <span className={cn(
              "font-bold text-sm",
              (stats?.net_realized_pnl ?? 0) > 0 ? "text-emerald-500 dark:text-emerald-400" :
              (stats?.net_realized_pnl ?? 0) < 0 ? "text-rose-500 dark:text-rose-400" : "text-muted-foreground"
            )}>
              {(stats?.net_realized_pnl ?? 0) > 0 ? `+$${(stats?.net_realized_pnl ?? 0).toFixed(2)}` : `$${(stats?.net_realized_pnl ?? 0).toFixed(2)}`}
            </span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30 border-b border-border/40">
                <TableHead className="w-[100px] pl-5 font-mono text-[11px]">Deal ID</TableHead>
                <TableHead className="font-mono text-[11px]">Order ID</TableHead>
                <TableHead className="font-mono text-[11px]">Symbol</TableHead>
                <TableHead className="font-mono text-[11px]">Type</TableHead>
                <TableHead className="font-mono text-[11px]">Entry</TableHead>
                <TableHead className="font-mono text-[11px]">Volume</TableHead>
                <TableHead className="font-mono text-[11px]">Price</TableHead>
                <TableHead className="font-mono text-[11px]">Commission</TableHead>
                <TableHead className="font-mono text-[11px]">Swap</TableHead>
                <TableHead className="font-mono text-[11px]">Realized P/L</TableHead>
                <TableHead className="font-mono text-[11px]">Net Profit</TableHead>
                <TableHead className="pr-5 font-mono text-[11px]">Execution Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isMT5Loading ? (
                Array.from({ length: 2 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-5"><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell className="pr-5"><Skeleton className="h-4 w-24" /></TableCell>
                  </TableRow>
                ))
              ) : history.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={12} className="h-24 text-center text-muted-foreground border-dashed">
                    <div className="flex flex-col items-center justify-center gap-1.5 opacity-80">
                      <CheckCircle2 className="w-5 h-5 text-muted-foreground/60" />
                      <span className="font-mono text-xs font-semibold text-foreground">NO CLOSED TRADES IN HISTORY</span>
                      <span className="text-[11px] text-muted-foreground font-mono">No closed deal settlements logged yet for this account.</span>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                history.map((d) => (
                  <TableRow key={d.ticket} className="font-mono text-xs hover:bg-muted/30 transition-colors">
                    <TableCell className="pl-5 font-bold text-foreground">#{d.ticket}</TableCell>
                    <TableCell className="text-muted-foreground">#{d.order}</TableCell>
                    <TableCell className="font-bold text-primary">{d.symbol || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={d.direction === "buy" ? "buy" : "sell"} className="text-[10px] uppercase font-bold px-2 py-0.5">
                        {d.direction}
                      </Badge>
                    </TableCell>
                    <TableCell className="uppercase text-muted-foreground">{d.entry}</TableCell>
                    <TableCell>{d.volume.toFixed(2)} lots</TableCell>
                    <TableCell>{d.price.toFixed(5)}</TableCell>
                    <TableCell className="text-muted-foreground">{d.commission ? `$${d.commission.toFixed(2)}` : "$0.00"}</TableCell>
                    <TableCell className="text-muted-foreground">{d.swap ? `$${d.swap.toFixed(2)}` : "$0.00"}</TableCell>
                    <TableCell className={cn(
                      "font-semibold",
                      d.profit > 0 ? "text-emerald-500 dark:text-emerald-400" :
                      d.profit < 0 ? "text-rose-500 dark:text-rose-400" : "text-muted-foreground"
                    )}>
                      {d.profit > 0 ? `+$${d.profit.toFixed(2)}` : `$${d.profit.toFixed(2)}`}
                    </TableCell>
                    <TableCell className={cn(
                      "font-bold text-sm",
                      d.net_profit > 0 ? "text-emerald-500 dark:text-emerald-400" :
                      d.net_profit < 0 ? "text-rose-500 dark:text-rose-400" : "text-muted-foreground"
                    )}>
                      {d.net_profit > 0 ? `+$${d.net_profit.toFixed(2)}` : `$${d.net_profit.toFixed(2)}`}
                    </TableCell>
                    <TableCell className="pr-5 text-muted-foreground text-[11px]">
                      {formatDateTime(d.close_time)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ─── Performance Chart & Active Signals Section ────────────────────── */}
      <div className="grid gap-6 md:grid-cols-7">
        {/* Equity Curve */}
        <Card className="md:col-span-5 border-border/60 bg-card/60 backdrop-blur-sm shadow-sm overflow-hidden">
          <CardHeader className="py-3 px-5 border-b border-border/40 bg-muted/20 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-mono font-bold uppercase tracking-widest text-muted-foreground">
              Portfolio Equity Curve (30-Day Window)
            </CardTitle>
            <span className="text-[10px] font-mono text-muted-foreground">DYNAMIC RE-INDEXED</span>
          </CardHeader>
          <CardContent className="p-4 sm:p-5">
            <div className="h-[300px] w-full">
              {isPerfLoading ? (
                <Skeleton className="w-full h-full" />
              ) : performance && performance.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={performance} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} opacity={0.4} />
                    <XAxis
                      dataKey="date"
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(val) => new Date(val).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                      dy={8}
                    />
                    <YAxis
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(val) => `$${val}`}
                      domain={["auto", "auto"]}
                      dx={-8}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        borderColor: "hsl(var(--border))",
                        borderRadius: "6px",
                        boxShadow: "0 4px 14px rgba(0,0,0,0.25)",
                        fontFamily: "var(--font-mono)",
                        fontSize: "12px",
                      }}
                      itemStyle={{ color: "hsl(var(--foreground))", fontWeight: "bold" }}
                      labelStyle={{ color: "hsl(var(--muted-foreground))", fontSize: "11px", marginBottom: "4px" }}
                      formatter={(value: number) => [formatCurrency(value), "Equity"]}
                      labelFormatter={(label) => new Date(label).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
                    />
                    <Area
                      type="monotone"
                      dataKey="equity"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorEquity)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-muted-foreground font-mono text-xs border border-dashed border-border/40 rounded-lg">
                  No historical equity points recorded in this window
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Active Signals Card */}
        <Card className="md:col-span-2 border-border/60 bg-card/60 backdrop-blur-sm shadow-sm flex flex-col overflow-hidden">
          <CardHeader className="py-3 px-5 border-b border-border/40 bg-muted/20 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-mono font-bold uppercase tracking-widest text-muted-foreground">
              Active AI Signals
            </CardTitle>
            <span className="text-[10px] font-mono text-muted-foreground">SMC / EMA</span>
          </CardHeader>
          <CardContent className="flex-1 overflow-auto p-3.5 space-y-2.5">
            {isSignalsLoading ? (
              <div className="space-y-2.5">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
              </div>
            ) : activeSignals && activeSignals.length > 0 ? (
              activeSignals.slice(0, 6).map((signal) => (
                <div
                  key={signal.id}
                  className="p-2.5 rounded-md border border-border/50 bg-background/40 hover:bg-muted/30 transition-colors space-y-2 font-mono"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-xs text-foreground">{signal.pair}</span>
                      <span className="text-[10px] text-muted-foreground">{signal.timeframe || "M15"}</span>
                    </div>
                    <Badge
                      variant={
                        signal.direction?.toLowerCase() === "buy" ? "buy" :
                        signal.direction?.toLowerCase() === "sell" ? "sell" : "neutral"
                      }
                      className="text-[10px] px-2 py-0.5"
                    >
                      {signal.direction || "NO_TRADE"}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="truncate max-w-[130px]">{signal.smcPattern || "Order Flow"}</span>
                    <span className="font-bold text-foreground">
                      {formatPercent(signal.confidence, 0)} conf
                    </span>
                  </div>

                  {/* Confidence mini bar */}
                  <div className="w-full h-1 bg-muted rounded-full overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        signal.direction?.toLowerCase() === "buy" ? "bg-emerald-500" :
                        signal.direction?.toLowerCase() === "sell" ? "bg-rose-500" : "bg-primary"
                      )}
                      style={{ width: `${Math.min(100, Math.max(0, (signal.confidence || 0) * 100))}%` }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <div className="flex flex-col items-center justify-center h-full min-h-[160px] text-muted-foreground text-xs gap-2 opacity-75">
                <AlertTriangle className="w-6 h-6 text-muted-foreground/60" />
                <span className="font-mono text-xs font-semibold">AWAITING_HIGH_CONFIDENCE_SIGNALS</span>
                <span className="text-[10px] text-center font-mono">Scanner is evaluating 4-hour and 15-minute institutional order blocks.</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MT5MetricItem({
  label,
  value,
  sub,
  highlight,
  valueColor,
  loading,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
  valueColor?: string;
  loading?: boolean;
}) {
  return (
    <div className={cn(
      "flex flex-col gap-1 p-3 rounded-lg border transition-all shadow-2xs",
      highlight
        ? "bg-primary/10 border-primary/40 shadow-xs"
        : "bg-background/40 border-border/50 hover:border-border/80"
    )}>
      <span className="text-[10px] font-bold font-mono tracking-wider text-muted-foreground uppercase">
        {label}
      </span>
      {loading ? (
        <Skeleton className="h-6 w-20 mt-1" />
      ) : (
        <span className={cn("text-lg font-bold font-mono tracking-tight", valueColor || "text-foreground")}>
          {value}
        </span>
      )}
      {sub && (
        <span className="text-[10px] font-mono text-muted-foreground/80 truncate">
          {sub}
        </span>
      )}
    </div>
  );
}
