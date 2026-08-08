/**
 * Trade History page — closed + cancelled trades from backend.
 * Uses correct camelCase field names matching TradeOut/Trade schema.
 */

import { useState } from "react";
import { useGetTrades, useGetTradeStats } from "@workspace/api-client-react";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import { Search, ChevronLeft, ChevronRight, History } from "lucide-react";

const PAGE_SIZE = 20;

function dirBadge(dir: string) {
  return (
    <Badge variant={dir === "buy" ? "buy" : "sell"} className="text-[9px] px-1.5 py-0.5 uppercase font-bold">
      {dir}
    </Badge>
  );
}

function pnlColor(pnl?: number | null) {
  if (pnl === null || pnl === undefined) return "";
  return pnl >= 0 ? "text-emerald-500" : "text-red-500";
}

function duration(opened?: string | null, closed?: string | null): string {
  if (!opened || !closed) return "---";
  const diff = (new Date(closed).getTime() - new Date(opened).getTime()) / 1000;
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function HistoryPage() {
  const [page,   setPage]   = useState(1);
  const [search, setSearch] = useState("");
  const [dir,    setDir]    = useState<"all" | "buy" | "sell">("all");

  const { data: tradesData, isLoading } = useGetTrades({
    page, limit: PAGE_SIZE, status: "closed",
  });
  const { data: stats, isLoading: statsLoading } = useGetTradeStats();

  const trades = tradesData?.items ?? [];
  const total  = tradesData?.total ?? 0;
  const pages  = Math.ceil(total / PAGE_SIZE);

  const filtered = trades.filter(t => {
    if (dir !== "all" && t.direction !== dir) return false;
    if (search && !t.pair.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <History className="w-6 h-6 text-muted-foreground" /> Trade History
          </h1>
          <p className="text-muted-foreground text-sm mt-0.5">All closed and cancelled trade records</p>
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: "Total PnL",     val: stats?.totalPnl != null ? formatCurrency(stats.totalPnl) : "---",
            color: stats?.totalPnl != null && stats.totalPnl < 0 ? "text-red-500" : "text-emerald-500" },
          { label: "Win Rate",      val: stats?.winRate != null ? formatPercent(stats.winRate * 100) : "---" },
          { label: "Profit Factor", val: stats?.profitFactor != null ? formatNumber(stats.profitFactor) : "---" },
          { label: "Avg R:R",       val: stats?.avgRr != null ? formatNumber(stats.avgRr) : "---" },
          { label: "Max Drawdown",  val: stats?.maxDrawdown != null ? formatPercent(stats.maxDrawdown * 100) : "---",
            color: "text-red-500" },
        ].map((s, i) => (
          <Card key={i} className="bg-card/50 border-border/50">
            <CardContent className="p-3 flex flex-col gap-1">
              <span className="text-[9px] uppercase font-bold tracking-widest text-muted-foreground">{s.label}</span>
              {statsLoading
                ? <Skeleton className="h-5 w-16" />
                : <span className={cn("text-base font-mono font-bold tracking-tight", s.color)}>{s.val}</span>
              }
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search pair..." value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
            className="pl-8 h-8 w-36 text-xs bg-card/50 border-border/50" />
        </div>
        {(["all","buy","sell"] as const).map(d => (
          <button key={d} onClick={() => { setDir(d); setPage(1); }}
            className={cn("px-3 py-1.5 rounded text-[10px] font-mono font-bold uppercase tracking-widest transition-all",
              dir === d ? "bg-primary text-primary-foreground" : "bg-muted/40 text-muted-foreground hover:bg-muted"
            )}>
            {d}
          </button>
        ))}
        <span className="text-xs text-muted-foreground ml-auto">{total} trades total</span>
      </div>

      {/* Table */}
      <Card className="bg-card/50 border-border/50 shadow-lg">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="pl-5">Pair</TableHead>
                <TableHead>Dir</TableHead>
                <TableHead>Entry</TableHead>
                <TableHead>SL</TableHead>
                <TableHead>TP</TableHead>
                <TableHead>Lot</TableHead>
                <TableHead>Opened</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>R:R</TableHead>
                <TableHead className="text-right pr-5">PnL</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 10 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : filtered.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={10} className="h-32 text-center text-muted-foreground font-mono text-sm">
                    NO_TRADE_HISTORY
                  </TableCell>
                </TableRow>
              ) : filtered.map(t => (
                <TableRow key={t.id} className="hover:bg-muted/20 transition-colors">
                  <TableCell className="pl-5 font-bold text-sm">{t.pair}</TableCell>
                  <TableCell>{dirBadge(t.direction)}</TableCell>
                  <TableCell className="font-mono text-xs">{t.entryPrice}</TableCell>
                  <TableCell className="font-mono text-xs text-red-400">{t.stopLoss}</TableCell>
                  <TableCell className="font-mono text-xs text-emerald-400">{t.takeProfit}</TableCell>
                  <TableCell className="font-mono text-xs">{t.lotSize}</TableCell>
                  <TableCell className="font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                    {t.openedAt ? new Date(t.openedAt).toLocaleString() : "---"}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {duration(t.openedAt, t.closedAt)}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {t.riskRewardRatio ? `1:${formatNumber(t.riskRewardRatio)}` : "---"}
                  </TableCell>
                  <TableCell className={cn("text-right pr-5 font-mono font-bold text-sm", pnlColor(t.pnl))}>
                    {t.pnl !== null && t.pnl !== undefined ? formatCurrency(t.pnl) : "---"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-end gap-3">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}
            className="h-8 w-8 p-0 border-border/50">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-xs text-muted-foreground font-mono">Page {page} / {pages}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)}
            className="h-8 w-8 p-0 border-border/50">
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
