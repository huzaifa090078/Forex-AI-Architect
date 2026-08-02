import { useGetTrades, useGetTradeStats } from "@workspace/api-client-react";
import { Card, CardContent } from "@/components/ui/card";
import { formatCurrency, formatNumber, formatPercent, formatDate, cn } from "@/lib/utils";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function TradesPage() {
  const { data: tradesData, isLoading } = useGetTrades({ limit: 50 });
  const { data: stats, isLoading: isStatsLoading } = useGetTradeStats();

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Trade History</h1>
        <p className="text-muted-foreground mt-1 text-sm">Detailed log of all executed trades and outcomes.</p>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Total PnL", val: stats?.totalPnl !== undefined ? formatCurrency(stats.totalPnl) : "---", color: stats?.totalPnl && stats.totalPnl < 0 ? "text-red-500" : "text-emerald-500" },
          { label: "Win Rate", val: stats?.winRate ? formatPercent(stats.winRate) : "---" },
          { label: "Profit Factor", val: stats?.profitFactor ? formatNumber(stats.profitFactor) : "---" },
          { label: "Avg R:R", val: stats?.avgRr ? formatNumber(stats.avgRr) : "---" },
          { label: "Max Drawdown", val: stats?.maxDrawdown ? formatPercent(stats.maxDrawdown) : "---", color: "text-red-500" }
        ].map((s, i) => (
          <Card key={i} className="bg-card/50 backdrop-blur border-border/50">
            <CardContent className="p-4 flex flex-col gap-1.5">
              <span className="text-[10px] uppercase text-muted-foreground font-bold tracking-widest">{s.label}</span>
              {isStatsLoading ? <Skeleton className="h-6 w-16" /> : (
                <span className={cn("text-lg font-mono font-bold tracking-tight", s.color)}>{s.val}</span>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg">
        <div className="rounded-md overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent bg-muted/30">
                <TableHead className="w-[180px]">Time</TableHead>
                <TableHead>Pair</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Entry</TableHead>
                <TableHead>SL / TP</TableHead>
                <TableHead>Lot</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">PnL</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({length: 10}).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16 ml-auto" /></TableCell>
                  </TableRow>
                ))
              ) : tradesData?.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="h-32 text-center text-muted-foreground border-dashed">
                    <span className="font-mono text-sm">NO_TRADES_FOUND</span>
                  </TableCell>
                </TableRow>
              ) : (
                tradesData?.items.map((trade) => (
                  <TableRow key={trade.id} className="group">
                    <TableCell className="font-mono text-muted-foreground text-xs whitespace-nowrap">
                      {formatDate(trade.createdAt)}
                    </TableCell>
                    <TableCell className="font-bold tracking-wide text-sm">{trade.pair}</TableCell>
                    <TableCell>
                      <Badge variant={trade.direction === "buy" ? "buy" : "sell"} className="px-2 text-[10px]">
                        {trade.direction}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{formatNumber(trade.entryPrice, 5)}</TableCell>
                    <TableCell className="font-mono text-xs">
                      <span className="text-red-400/80">{formatNumber(trade.stopLoss, 5)}</span>
                      <span className="text-muted-foreground/30 mx-1">/</span>
                      <span className="text-emerald-400/80">{formatNumber(trade.takeProfit, 5)}</span>
                    </TableCell>
                    <TableCell className="font-mono text-sm text-muted-foreground">{formatNumber(trade.lotSize, 2)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("px-2 text-[10px] font-bold border", 
                        trade.status === "open" ? "text-blue-500 border-blue-500/30 bg-blue-500/10" :
                        trade.status === "closed" ? "text-muted-foreground border-border bg-muted/20" : "text-muted-foreground opacity-50"
                      )}>
                        {trade.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {trade.pnl !== null && trade.pnl !== undefined ? (
                        <span className={cn("font-mono font-bold text-sm tracking-tight", trade.pnl > 0 ? "text-emerald-500" : trade.pnl < 0 ? "text-red-500" : "")}>
                          {trade.pnl > 0 ? "+" : ""}{formatCurrency(trade.pnl)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground font-mono">---</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}
