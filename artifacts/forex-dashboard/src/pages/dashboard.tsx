import { useState } from "react";
import { useGetDashboardSummary, useGetDashboardPerformance, useGetActiveSignals } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* ─── Top Header ────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-extrabold tracking-tight">Command Center</h1>
            <Badge variant="outline" className="text-[11px] font-mono border-primary/30 text-primary">
              DEMO MODE
            </Badge>
          </div>
          <p className="text-muted-foreground mt-1 text-sm">
            Live MetaTrader 5 execution bridge, real-time portfolio metrics & algorithmic telemetry.
          </p>
        </div>

        <div className="flex items-center flex-wrap gap-3">
          {/* MT5 Connection Badge */}
          <div className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs font-mono font-semibold transition-all shadow-sm",
            isConnected
              ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-400"
              : "bg-red-950/40 border-red-500/40 text-red-400"
          )}>
            <div className={cn(
              "w-2.5 h-2.5 rounded-full",
              isConnected ? "bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]" : "bg-red-400"
            )} />
            <span>
              {isMT5Loading ? "CONNECTING..." : isConnected ? "MT5 CONNECTED" : "MT5 DISCONNECTED"}
            </span>
            {account && (
              <span className="text-muted-foreground border-l border-border/50 pl-2">
                {account.server}
              </span>
            )}
          </div>

          {/* Refresh Action */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetchMT5()}
            disabled={isMT5Fetching}
            className="h-8 gap-1.5 text-xs font-mono border-border/60 bg-card/40 hover:bg-card"
            title="Refresh MT5 data"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", isMT5Fetching && "animate-spin text-primary")} />
            <span>{isMT5Fetching ? "SYNCING..." : "SYNC"}</span>
          </Button>

          {/* Bot State */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-card/60 border border-border/50 rounded-md shadow-sm">
            <div className={cn("w-2 h-2 rounded-full",
              isSummaryLoading ? "bg-muted" :
              summary?.botStatus === "running" ? "bg-emerald-500 animate-pulse" :
              summary?.botStatus === "paused" ? "bg-amber-500" : "bg-red-500"
            )} />
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">
              {isSummaryLoading ? "---" : summary?.botStatus || "ACTIVE"}
            </span>
          </div>
        </div>
      </div>

      {/* ─── MT5 Account Snapshot Bar ─────────────────────────────────────── */}
      <Card className="bg-gradient-to-r from-card/80 via-card/50 to-background border-border/60 shadow-lg">
        <CardHeader className="py-3 px-6 border-b border-border/40 flex flex-row items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Server className="w-4 h-4 text-primary" />
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              MetaTrader 5 Account Details
            </span>
          </div>
          {account && (
            <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground">
              <span>Login: <strong className="text-foreground">{account.login}</strong></span>
              <span>Server: <strong className="text-foreground">{account.server}</strong></span>
              <span>Company: <strong className="text-foreground">{account.company || "Exness"}</strong></span>
              <span>Leverage: <strong className="text-foreground">1:{account.leverage}</strong></span>
            </div>
          )}
        </CardHeader>
        <CardContent className="p-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-4">
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
                account.floating_pnl > 0 ? "text-emerald-400" : "text-red-400"
              }
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="TODAY REALIZED"
              value={stats ? (stats.today_realized_pnl > 0 ? `+$${stats.today_realized_pnl.toFixed(2)}` : `$${stats.today_realized_pnl.toFixed(2)}`) : "---"}
              sub="Closed Today"
              valueColor={
                !stats || stats.today_realized_pnl === 0 ? "text-muted-foreground" :
                stats.today_realized_pnl > 0 ? "text-emerald-400" : "text-red-400"
              }
              loading={isMT5Loading}
            />
            <MT5MetricItem
              label="NET REALIZED"
              value={stats ? (stats.net_realized_pnl > 0 ? `+$${stats.net_realized_pnl.toFixed(2)}` : `$${stats.net_realized_pnl.toFixed(2)}`) : "---"}
              sub="Total P/L"
              valueColor={
                !stats || stats.net_realized_pnl === 0 ? "text-muted-foreground" :
                stats.net_realized_pnl > 0 ? "text-emerald-400" : "text-red-400"
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

      {/* ─── P/L Distinction Banner ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="flex items-center gap-3 p-3.5 rounded-lg border border-blue-500/20 bg-blue-950/20 text-blue-300 text-xs font-mono">
          <Layers className="w-4 h-4 text-blue-400 shrink-0" />
          <div>
            <strong className="text-blue-200">FLOATING P/L (Unrealized):</strong> Dynamically fluctuates with live market ticks on active open positions. Does not change account balance until closed.
          </div>
        </div>
        <div className="flex items-center gap-3 p-3.5 rounded-lg border border-emerald-500/20 bg-emerald-950/20 text-emerald-300 text-xs font-mono">
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          <div>
            <strong className="text-emerald-200">REALIZED P/L (Closed):</strong> Confirmed profits/losses from closed trade deals including commissions & swaps. Settled into account balance.
          </div>
        </div>
      </div>

      {/* ─── MT5 Open Positions Section ───────────────────────────────────── */}
      <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg">
        <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-border/40">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-bold uppercase tracking-wider">
              Live Open Positions (MetaTrader 5)
            </CardTitle>
            <Badge variant="secondary" className="font-mono text-xs ml-2">
              {positions.length} Active
            </Badge>
          </div>
          <div className="text-xs font-mono text-muted-foreground flex items-center gap-2">
            <span>Floating Net:</span>
            <span className={cn(
              "font-bold",
              (stats?.total_floating_pnl ?? 0) > 0 ? "text-emerald-400" :
              (stats?.total_floating_pnl ?? 0) < 0 ? "text-red-400" : "text-muted-foreground"
            )}>
              ${(stats?.total_floating_pnl ?? 0).toFixed(2)}
            </span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="w-[110px] pl-6">Ticket</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead>Volume</TableHead>
                <TableHead>Open Price</TableHead>
                <TableHead>Current Price</TableHead>
                <TableHead>Stop Loss</TableHead>
                <TableHead>Take Profit</TableHead>
                <TableHead>Swap</TableHead>
                <TableHead>Floating P/L</TableHead>
                <TableHead className="pr-6">Open Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isMT5Loading ? (
                Array.from({ length: 2 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-6"><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-14" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-14" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell className="pr-6"><Skeleton className="h-4 w-24" /></TableCell>
                  </TableRow>
                ))
              ) : positions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={11} className="h-28 text-center text-muted-foreground border-dashed">
                    <div className="flex flex-col items-center justify-center gap-1.5 opacity-70">
                      <Clock className="w-5 h-5 text-muted-foreground" />
                      <span className="font-mono text-xs">NO_OPEN_POSITIONS_IN_MT5</span>
                      <span className="text-[11px] text-muted-foreground">Demo account is ready. No trades currently open.</span>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                positions.map((p) => (
                  <TableRow key={p.ticket} className="font-mono text-xs hover:bg-muted/30 transition-colors">
                    <TableCell className="pl-6 font-bold text-foreground">#{p.ticket}</TableCell>
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
                      p.floating_pnl > 0 ? "text-emerald-400" :
                      p.floating_pnl < 0 ? "text-red-400" : "text-muted-foreground"
                    )}>
                      {p.floating_pnl > 0 ? `+$${p.floating_pnl.toFixed(2)}` : `$${p.floating_pnl.toFixed(2)}`}
                    </TableCell>
                    <TableCell className="pr-6 text-muted-foreground text-[11px]">
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
      <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg">
        <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-border/40">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <CardTitle className="text-sm font-bold uppercase tracking-wider">
              Closed Trade History (MT5 Deals)
            </CardTitle>
            <Badge variant="secondary" className="font-mono text-xs ml-2">
              {history.length} Executed Deals
            </Badge>
          </div>
          <div className="text-xs font-mono text-muted-foreground flex items-center gap-2">
            <span>Net Realized:</span>
            <span className={cn(
              "font-bold",
              (stats?.net_realized_pnl ?? 0) > 0 ? "text-emerald-400" :
              (stats?.net_realized_pnl ?? 0) < 0 ? "text-red-400" : "text-muted-foreground"
            )}>
              ${(stats?.net_realized_pnl ?? 0).toFixed(2)}
            </span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="w-[110px] pl-6">Deal ID</TableHead>
                <TableHead>Order ID</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Entry</TableHead>
                <TableHead>Volume</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Commission</TableHead>
                <TableHead>Swap</TableHead>
                <TableHead>Realized P/L</TableHead>
                <TableHead>Net Profit</TableHead>
                <TableHead className="pr-6">Execution Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isMT5Loading ? (
                Array.from({ length: 2 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-6"><Skeleton className="h-4 w-16" /></TableCell>
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
                    <TableCell className="pr-6"><Skeleton className="h-4 w-24" /></TableCell>
                  </TableRow>
                ))
              ) : history.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={12} className="h-28 text-center text-muted-foreground border-dashed">
                    <div className="flex flex-col items-center justify-center gap-1.5 opacity-70">
                      <CheckCircle2 className="w-5 h-5 text-muted-foreground" />
                      <span className="font-mono text-xs">NO_CLOSED_TRADES_IN_HISTORY</span>
                      <span className="text-[11px] text-muted-foreground">No completed trade executions recorded yet in this testing period.</span>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                history.map((d) => (
                  <TableRow key={d.ticket} className="font-mono text-xs hover:bg-muted/30 transition-colors">
                    <TableCell className="pl-6 font-bold text-foreground">#{d.ticket}</TableCell>
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
                      d.profit > 0 ? "text-emerald-400" :
                      d.profit < 0 ? "text-red-400" : "text-muted-foreground"
                    )}>
                      {d.profit > 0 ? `+$${d.profit.toFixed(2)}` : `$${d.profit.toFixed(2)}`}
                    </TableCell>
                    <TableCell className={cn(
                      "font-bold text-sm",
                      d.net_profit > 0 ? "text-emerald-400" :
                      d.net_profit < 0 ? "text-red-400" : "text-muted-foreground"
                    )}>
                      {d.net_profit > 0 ? `+$${d.net_profit.toFixed(2)}` : `$${d.net_profit.toFixed(2)}`}
                    </TableCell>
                    <TableCell className="pr-6 text-muted-foreground text-[11px]">
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
        <Card className="md:col-span-5 bg-card/50 backdrop-blur border-border/50 shadow-lg">
          <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-border/50">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
              Equity Curve (30d)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[320px] w-full mt-6">
              {isPerfLoading ? (
                <Skeleton className="w-full h-full" />
              ) : performance && performance.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={performance}>
                    <defs>
                      <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} opacity={0.5} />
                    <XAxis
                      dataKey="date"
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(val) => new Date(val).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                      dy={10}
                    />
                    <YAxis
                      stroke="hsl(var(--muted-foreground))"
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(val) => `$${val}`}
                      domain={["auto", "auto"]}
                      dx={-10}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: "hsl(var(--card))", borderColor: "hsl(var(--border))", borderRadius: "8px", boxShadow: "0 4px 12px rgba(0,0,0,0.15)" }}
                      itemStyle={{ color: "hsl(var(--foreground))", fontFamily: "var(--font-mono)", fontWeight: "bold" }}
                      labelStyle={{ color: "hsl(var(--muted-foreground))", fontSize: "12px", marginBottom: "4px" }}
                      formatter={(value: number) => [formatCurrency(value), "Equity"]}
                      labelFormatter={(label) => new Date(label).toLocaleDateString()}
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
                <div className="flex h-full items-center justify-center text-muted-foreground font-mono text-sm border border-dashed border-border/50 rounded-lg">
                  No performance data available
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-2 bg-card/50 backdrop-blur border-border/50 shadow-lg flex flex-col">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
              Active Signals
            </CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-auto p-4">
            {isSignalsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
              </div>
            ) : activeSignals && activeSignals.length > 0 ? (
              <div className="space-y-3">
                {activeSignals.slice(0, 6).map((signal) => (
                  <div key={signal.id} className="flex items-center justify-between p-3 rounded-md border border-border/50 bg-background/30 hover:bg-muted/30 transition-colors">
                    <div className="flex flex-col gap-1.5">
                      <span className="font-bold text-sm tracking-wide">{signal.pair}</span>
                      <span className="text-[10px] uppercase text-muted-foreground font-semibold">{signal.smcPattern || "Signal"}</span>
                    </div>
                    <div className="flex flex-col items-end gap-1.5">
                      <Badge variant={signal.direction === "buy" ? "buy" : "sell"} className="text-[10px] px-2 py-0.5 rounded shadow-sm">
                        {signal.direction}
                      </Badge>
                      <span className="text-[10px] font-mono text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                        {formatPercent(signal.confidence, 0)} conf
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground text-sm gap-3 opacity-60">
                <AlertTriangle className="w-8 h-8" />
                <p className="font-mono text-xs">AWAITING_SIGNALS</p>
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
      "flex flex-col gap-1 p-3 rounded-lg border transition-all",
      highlight
        ? "bg-primary/5 border-primary/30"
        : "bg-background/40 border-border/40"
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
        <span className="text-[10px] font-mono text-muted-foreground/70">
          {sub}
        </span>
      )}
    </div>
  );
}
