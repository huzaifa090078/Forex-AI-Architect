import { useGetDashboardSummary, useGetDashboardPerformance, useGetActiveSignals } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatNumber, formatPercent, cn } from "@/lib/utils";
import { Activity, DollarSign, Target, TrendingUp, AlertTriangle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from "recharts";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export default function DashboardPage() {
  const { data: summary, isLoading: isSummaryLoading } = useGetDashboardSummary();
  const { data: performance, isLoading: isPerfLoading } = useGetDashboardPerformance({ period: "30d" });
  const { data: activeSignals, isLoading: isSignalsLoading } = useGetActiveSignals();

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Command Center</h1>
          <p className="text-muted-foreground mt-1 text-sm">Real-time system overview and portfolio performance.</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-card/50 backdrop-blur border border-border/50 rounded-md shadow-sm">
            <div className={cn("w-2 h-2 rounded-full", 
              isSummaryLoading ? "bg-muted" :
              summary?.botStatus === "running" ? "bg-emerald-500 animate-pulse" :
              summary?.botStatus === "paused" ? "bg-amber-500" : "bg-red-500"
            )} />
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">
              {isSummaryLoading ? "---" : summary?.botStatus || "UNKNOWN"}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard 
          title="Total Equity" 
          value={summary?.equity ? formatCurrency(summary.equity) : undefined}
          icon={DollarSign}
          trend={summary?.totalPnl ? (summary.totalPnl > 0 ? "up" : "down") : undefined}
          trendValue={summary?.totalPnl ? formatCurrency(Math.abs(summary.totalPnl)) : undefined}
          loading={isSummaryLoading}
        />
        <MetricCard 
          title="Today's PnL" 
          value={summary?.todayPnl !== undefined ? formatCurrency(summary.todayPnl) : undefined}
          icon={TrendingUp}
          valueColor={summary?.todayPnl && summary.todayPnl < 0 ? "text-red-500" : "text-emerald-500"}
          loading={isSummaryLoading}
        />
        <MetricCard 
          title="Win Rate" 
          value={summary?.winRate ? formatPercent(summary.winRate) : undefined}
          icon={Target}
          loading={isSummaryLoading}
        />
        <MetricCard 
          title="Open Trades" 
          value={summary?.openTrades?.toString()}
          icon={Activity}
          loading={isSummaryLoading}
        />
      </div>

      <div className="grid gap-6 md:grid-cols-7">
        <Card className="md:col-span-5 bg-card/50 backdrop-blur border-border/50 shadow-lg">
          <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-border/50">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Equity Curve (30d)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[350px] w-full mt-6">
              {isPerfLoading ? (
                <Skeleton className="w-full h-full" />
              ) : performance && performance.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={performance}>
                    <defs>
                      <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} opacity={0.5} />
                    <XAxis 
                      dataKey="date" 
                      stroke="hsl(var(--muted-foreground))" 
                      fontSize={11} 
                      tickLine={false} 
                      axisLine={false} 
                      tickFormatter={(val) => new Date(val).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                      dy={10}
                    />
                    <YAxis 
                      stroke="hsl(var(--muted-foreground))" 
                      fontSize={11} 
                      tickLine={false} 
                      axisLine={false} 
                      tickFormatter={(val) => `$${val}`}
                      domain={['auto', 'auto']}
                      dx={-10}
                    />
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}
                      itemStyle={{ color: 'hsl(var(--foreground))', fontFamily: 'var(--font-mono)', fontWeight: 'bold' }}
                      labelStyle={{ color: 'hsl(var(--muted-foreground))', fontSize: '12px', marginBottom: '4px' }}
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
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Active Signals</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-auto p-4">
            {isSignalsLoading ? (
              <div className="space-y-3">
                {[1,2,3].map(i => <Skeleton key={i} className="h-16 w-full" />)}
              </div>
            ) : activeSignals?.items && activeSignals.items.length > 0 ? (
              <div className="space-y-3">
                {activeSignals.items.slice(0, 6).map(signal => (
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

function MetricCard({ title, value, icon: Icon, trend, trendValue, valueColor, loading }: any) {
  return (
    <Card className="bg-card/50 backdrop-blur border-border/50 shadow-md hover:border-border transition-colors">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground/50" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-24 mt-1" />
        ) : (
          <div className="flex flex-col gap-1.5">
            <div className={cn("text-2xl font-bold font-mono tracking-tight", valueColor)}>
              {value || "---"}
            </div>
            {trend && trendValue && (
              <p className="text-[10px] text-muted-foreground font-mono uppercase tracking-wide">
                <span className={trend === "up" ? "text-emerald-500" : "text-red-500"}>
                  {trend === "up" ? "+" : "-"}{trendValue}
                </span>{" "}
                all time
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
