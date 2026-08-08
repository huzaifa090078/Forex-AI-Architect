/**
 * Open Trades page — live enriched open positions.
 * Manual close goes through Trade Manager API (useDeleteTrade).
 * SL/TP modification uses useUpdateTrade.
 * No direct MT5 calls from frontend.
 */

import { useState } from "react";
import { useGetTrades, useUpdateTrade, useDeleteTrade } from "@workspace/api-client-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, formatCurrency, formatNumber } from "@/lib/utils";
import { TrendingUp, TrendingDown, X, Edit2, AlertTriangle } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { getGetTradesQueryKey } from "@workspace/api-client-react";

function dirIcon(dir: string) {
  return dir === "buy"
    ? <TrendingUp  className="w-3.5 h-3.5 text-emerald-500" />
    : <TrendingDown className="w-3.5 h-3.5 text-red-500"    />;
}

function pnlClass(pnl?: number | null) {
  if (pnl === undefined || pnl === null) return "text-muted-foreground";
  return pnl >= 0 ? "text-emerald-500" : "text-red-500";
}

function duration(opened?: string | null): string {
  if (!opened) return "---";
  const diff = (Date.now() - new Date(opened).getTime()) / 1000;
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function TradesPage() {
  const queryClient = useQueryClient();
  const { data: paginated, isLoading } = useGetTrades({ status: "open", limit: 100 });
  const trades = paginated?.items ?? [];

  const deleteTrade = useDeleteTrade();
  const updateTrade = useUpdateTrade();

  const [closeId, setCloseId] = useState<string | null>(null);
  const [editId,  setEditId]  = useState<string | null>(null);
  const [editSl,  setEditSl]  = useState("");
  const [editTp,  setEditTp]  = useState("");

  const handleClose = async () => {
    if (!closeId) return;
    try {
      await deleteTrade.mutateAsync({ id: closeId });
      toast.success("Close request sent to Trade Manager.");
      queryClient.invalidateQueries({ queryKey: getGetTradesQueryKey({ status: "open" }) });
    } catch {
      toast.error("Failed to close trade — backend error.");
    } finally {
      setCloseId(null);
    }
  };

  const handleModify = async () => {
    if (!editId) return;
    const payload: any = {};
    if (editSl) payload.stopLoss   = Number(editSl);
    if (editTp) payload.takeProfit = Number(editTp);
    if (!Object.keys(payload).length) { setEditId(null); return; }
    try {
      await updateTrade.mutateAsync({ id: editId, data: payload });
      toast.success("SL/TP update sent to Trade Manager.");
      queryClient.invalidateQueries({ queryKey: getGetTradesQueryKey({ status: "open" }) });
    } catch {
      toast.error("Failed to modify trade — backend error.");
    } finally {
      setEditId(null);
      setEditSl("");
      setEditTp("");
    }
  };

  const openTrade = trades.find(t => t.id === editId);

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Open Trades</h1>
        <p className="text-muted-foreground text-sm mt-0.5">Live positions managed by Trade Manager</p>
      </div>

      <Card className="bg-card/50 border-border/50 shadow-lg">
        <CardHeader className="border-b border-border/50 pb-4">
          <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-500" />
            Active Positions ({isLoading ? "---" : trades.length})
          </CardTitle>
        </CardHeader>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="pl-5">Pair</TableHead>
                <TableHead>Dir</TableHead>
                <TableHead>Entry</TableHead>
                <TableHead className="text-red-400/70">SL</TableHead>
                <TableHead className="text-emerald-400/70">TP</TableHead>
                <TableHead>Lot</TableHead>
                <TableHead>Open Time</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>R:R</TableHead>
                <TableHead className="text-right">PnL</TableHead>
                <TableHead className="text-right pr-5">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 11 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : trades.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={11} className="h-32 text-center text-muted-foreground">
                    <div className="flex flex-col items-center gap-2 opacity-50">
                      <AlertTriangle className="w-8 h-8" />
                      <span className="font-mono text-sm font-bold tracking-widest">NO_OPEN_POSITIONS</span>
                    </div>
                  </TableCell>
                </TableRow>
              ) : trades.map(t => (
                <TableRow key={t.id} className="hover:bg-muted/20 transition-colors">
                  <TableCell className="pl-5 font-bold text-sm">{t.pair}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      {dirIcon(t.direction)}
                      <Badge variant={t.direction === "buy" ? "buy" : "sell"}
                        className="text-[9px] px-1.5 py-0.5 uppercase font-bold">
                        {t.direction}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{t.entryPrice}</TableCell>
                  <TableCell className="font-mono text-xs text-red-400">{t.stopLoss}</TableCell>
                  <TableCell className="font-mono text-xs text-emerald-400">{t.takeProfit}</TableCell>
                  <TableCell className="font-mono text-xs">{t.lotSize}</TableCell>
                  <TableCell className="font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                    {t.openedAt ? new Date(t.openedAt).toLocaleString() : "---"}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {duration(t.openedAt)}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {t.riskRewardRatio ? `1:${formatNumber(t.riskRewardRatio)}` : "---"}
                  </TableCell>
                  <TableCell className={cn("text-right font-mono font-bold text-sm", pnlClass(t.pnl))}>
                    {t.pnl !== null && t.pnl !== undefined ? formatCurrency(t.pnl) : "---"}
                  </TableCell>
                  <TableCell className="text-right pr-5">
                    <div className="flex items-center gap-1.5 justify-end">
                      <Button variant="outline" size="sm"
                        onClick={() => { setEditId(t.id); setEditSl(String(t.stopLoss)); setEditTp(String(t.takeProfit)); }}
                        className="h-7 w-7 p-0 border-border/50 hover:border-primary/50">
                        <Edit2 className="w-3 h-3" />
                      </Button>
                      <Button variant="outline" size="sm"
                        onClick={() => setCloseId(t.id)}
                        className="h-7 w-7 p-0 border-red-500/30 hover:bg-red-500/10 hover:border-red-500/60">
                        <X className="w-3 h-3 text-red-400" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Close Confirmation Dialog */}
      <AlertDialog open={!!closeId} onOpenChange={open => !open && setCloseId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Close Trade</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to close this position?
              The close request will be sent to the Trade Manager → MT5 Connector → Exness.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleClose} className="bg-red-500 hover:bg-red-600">
              Yes, Close Trade
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit SL/TP Dialog */}
      <AlertDialog open={!!editId} onOpenChange={open => !open && setEditId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Modify SL / TP</AlertDialogTitle>
            <AlertDialogDescription>
              {openTrade && `Modifying ${openTrade.pair} ${openTrade.direction.toUpperCase()}. Changes go through Trade Manager.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Stop Loss</label>
              <Input value={editSl} onChange={e => setEditSl(e.target.value)} type="number"
                step="0.00001" className="font-mono text-sm border-red-500/30 focus:border-red-500" />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Take Profit</label>
              <Input value={editTp} onChange={e => setEditTp(e.target.value)} type="number"
                step="0.00001" className="font-mono text-sm border-emerald-500/30 focus:border-emerald-500" />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleModify}>Apply Changes</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
