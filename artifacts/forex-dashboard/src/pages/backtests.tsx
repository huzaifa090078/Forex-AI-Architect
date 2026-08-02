import { useGetBacktests, useCreateBacktest, getGetBacktestsQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatNumber, formatPercent, cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Play, History, Calendar, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

const formSchema = z.object({
  pair: z.string().min(1, "Required"),
  strategyId: z.string().min(1, "Required"),
  fromDate: z.string().min(1, "Required"),
  toDate: z.string().min(1, "Required"),
  initialBalance: z.coerce.number().min(100),
  lotSize: z.coerce.number().min(0.01),
});

export default function BacktestsPage() {
  const { data: backtests, isLoading } = useGetBacktests();
  const createBacktest = useCreateBacktest();
  const queryClient = useQueryClient();

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      pair: "EURUSD",
      strategyId: "SMC_V1",
      fromDate: "2024-01-01",
      toDate: "2024-01-31",
      initialBalance: 10000,
      lotSize: 0.1,
    }
  });

  const onSubmit = async (data: z.infer<typeof formSchema>) => {
    try {
      await createBacktest.mutateAsync({ data });
      toast.success("Simulation initialized successfully");
      queryClient.invalidateQueries({ queryKey: getGetBacktestsQueryKey() });
    } catch (error) {
      toast.error("Failed to start simulation");
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Backtesting Engine</h1>
        <p className="text-muted-foreground mt-1 text-sm">Validate strategies against historical tick data.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Run Form */}
        <Card className="xl:col-span-1 bg-card/50 backdrop-blur border-border/50 shadow-lg h-fit">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Play className="w-4 h-4 text-emerald-500" /> New Simulation
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="pair" className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Pair</Label>
                  <Input id="pair" {...register("pair")} className="font-mono text-xs bg-background/50 h-10 border-border/50 focus:border-primary" />
                  {errors.pair && <span className="text-[10px] text-red-500">{errors.pair.message}</span>}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="strategyId" className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Strategy</Label>
                  <Input id="strategyId" {...register("strategyId")} className="font-mono text-xs bg-background/50 h-10 border-border/50 focus:border-primary" />
                  {errors.strategyId && <span className="text-[10px] text-red-500">{errors.strategyId.message}</span>}
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="fromDate" className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5"><Calendar className="w-3 h-3 text-muted-foreground/70"/> From</Label>
                  <Input id="fromDate" type="date" {...register("fromDate")} className="font-mono text-xs bg-background/50 h-10 border-border/50 focus:border-primary" />
                  {errors.fromDate && <span className="text-[10px] text-red-500">{errors.fromDate.message}</span>}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="toDate" className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5"><Calendar className="w-3 h-3 text-muted-foreground/70"/> To</Label>
                  <Input id="toDate" type="date" {...register("toDate")} className="font-mono text-xs bg-background/50 h-10 border-border/50 focus:border-primary" />
                  {errors.toDate && <span className="text-[10px] text-red-500">{errors.toDate.message}</span>}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="initialBalance" className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Balance (USD)</Label>
                  <Input id="initialBalance" type="number" {...register("initialBalance")} className="font-mono text-xs bg-background/50 h-10 border-border/50 focus:border-primary" />
                  {errors.initialBalance && <span className="text-[10px] text-red-500">{errors.initialBalance.message}</span>}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lotSize" className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Lot Size</Label>
                  <Input id="lotSize" type="number" step="0.01" {...register("lotSize")} className="font-mono text-xs bg-background/50 h-10 border-border/50 focus:border-primary" />
                  {errors.lotSize && <span className="text-[10px] text-red-500">{errors.lotSize.message}</span>}
                </div>
              </div>

              <div className="pt-2">
                <Button type="submit" className="w-full h-12 tracking-widest uppercase font-bold text-[11px] shadow-lg shadow-primary/20" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> INITIALIZING</>
                  ) : "RUN SIMULATION"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* History Table */}
        <Card className="xl:col-span-2 bg-card/50 backdrop-blur border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <History className="w-4 h-4 text-blue-500" /> Execution History
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30">
                  <TableHead className="pl-6 w-[200px]">Simulation Spec</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Win Rate</TableHead>
                  <TableHead>Net PnL</TableHead>
                  <TableHead>Drawdown</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  Array.from({length: 5}).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell className="pl-6"><Skeleton className="h-10 w-full" /></TableCell>
                      <TableCell><Skeleton className="h-6 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                    </TableRow>
                  ))
                ) : backtests?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="h-48 text-center text-muted-foreground border-dashed">
                      <span className="font-mono text-sm tracking-widest font-bold opacity-50">NO_BACKTESTS_FOUND</span>
                    </TableCell>
                  </TableRow>
                ) : (
                  backtests?.map(run => (
                    <TableRow key={run.id} className="group">
                      <TableCell className="pl-6">
                        <div className="flex flex-col gap-1.5">
                          <span className="font-bold text-sm tracking-wide text-foreground/90">{run.strategyId} <span className="text-muted-foreground/70 font-normal">({run.pair})</span></span>
                          <span className="text-[10px] font-mono text-muted-foreground tracking-tight bg-muted/30 px-1.5 py-0.5 rounded w-fit">
                            {run.fromDate} → {run.toDate}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn("px-2.5 py-0.5 text-[10px] uppercase font-bold border gap-1.5",
                          run.status === "completed" ? "border-emerald-500/50 text-emerald-500 bg-emerald-500/10" :
                          run.status === "running" ? "border-blue-500/50 text-blue-500 bg-blue-500/10 animate-pulse" :
                          run.status === "failed" ? "border-red-500/50 text-red-500 bg-red-500/10" : "border-border text-muted-foreground"
                        )}>
                          {run.status === "completed" && <CheckCircle2 className="w-3 h-3" />}
                          {run.status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
                          {run.status === "failed" && <XCircle className="w-3 h-3" />}
                          {run.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-sm font-bold">
                        {run.winRate !== undefined && run.winRate !== null ? formatPercent(run.winRate) : <span className="text-muted-foreground/30">---</span>}
                      </TableCell>
                      <TableCell className="font-mono text-sm font-bold">
                        {run.netPnl !== undefined && run.netPnl !== null ? (
                          <span className={run.netPnl > 0 ? "text-emerald-500" : run.netPnl < 0 ? "text-red-500" : ""}>
                            {run.netPnl > 0 ? "+" : ""}{formatCurrency(run.netPnl)}
                          </span>
                        ) : <span className="text-muted-foreground/30">---</span>}
                      </TableCell>
                      <TableCell className="font-mono text-sm font-bold text-red-400/80">
                        {run.maxDrawdown !== undefined && run.maxDrawdown !== null ? formatPercent(run.maxDrawdown) : <span className="text-muted-foreground/30">---</span>}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
