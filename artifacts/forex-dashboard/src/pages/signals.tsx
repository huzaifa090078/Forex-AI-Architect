import { useGetSignals } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber, formatPercent, formatDate, cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Activity, Target, Shield, Clock } from "lucide-react";

export default function SignalsPage() {
  const { data: signalsData, isLoading } = useGetSignals({ limit: 20 });

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">AI Signals Feed</h1>
        <p className="text-muted-foreground mt-1 text-sm">Real-time market opportunities detected by the core engine.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {isLoading ? (
          Array.from({length: 8}).map((_, i) => (
            <Card key={i} className="bg-card/50 border-border/50">
              <CardContent className="p-5 space-y-4">
                <div className="flex justify-between"><Skeleton className="h-6 w-16" /><Skeleton className="h-6 w-12" /></div>
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-2/3" />
                <div className="pt-4 flex justify-between"><Skeleton className="h-4 w-12" /><Skeleton className="h-4 w-12" /></div>
              </CardContent>
            </Card>
          ))
        ) : signalsData?.items.length === 0 ? (
          <div className="col-span-full py-12 flex flex-col items-center justify-center border border-dashed border-border/50 rounded-lg bg-card/20">
            <Activity className="w-8 h-8 text-muted-foreground opacity-50 mb-3" />
            <span className="font-mono text-sm text-muted-foreground">NO_ACTIVE_SIGNALS</span>
          </div>
        ) : (
          signalsData?.items.map((signal) => (
            <Card key={signal.id} className={cn(
              "bg-card/50 backdrop-blur shadow-md transition-all hover:border-border",
              signal.status === "pending" ? "border-primary/50 shadow-[0_0_15px_rgba(20,184,166,0.1)]" : "border-border/50"
            )}>
              <CardContent className="p-5 flex flex-col h-full">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-lg font-bold tracking-wide">{signal.pair}</span>
                    <Badge variant={signal.direction === "buy" ? "buy" : "sell"} className="w-fit text-[10px] px-2 py-0">
                      {signal.direction}
                    </Badge>
                  </div>
                  <Badge variant="outline" className={cn("text-[10px] font-mono",
                    signal.status === "pending" ? "border-primary/50 text-primary" : "text-muted-foreground"
                  )}>
                    {signal.status}
                  </Badge>
                </div>

                <div className="space-y-3 flex-1">
                  <div className="flex justify-between items-center text-sm border-b border-border/50 pb-2">
                    <span className="text-muted-foreground text-xs uppercase tracking-wider">Confidence</span>
                    <span className="font-mono font-bold text-primary">{formatPercent(signal.confidence, 0)}</span>
                  </div>
                  <div className="flex justify-between items-center text-sm border-b border-border/50 pb-2">
                    <span className="text-muted-foreground text-xs uppercase tracking-wider">Pattern</span>
                    <span className="font-medium text-xs bg-muted/50 px-2 py-0.5 rounded">{signal.smcPattern || "N/A"}</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-2">
                    <div className="flex flex-col gap-1 bg-muted/20 p-2 rounded-md border border-border/30">
                      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider font-bold">
                        <Target className="w-3 h-3" /> Entry
                      </div>
                      <span className="font-mono text-xs font-semibold">
                        {signal.entryZoneLow ? formatNumber(signal.entryZoneLow, 5) : "Market"}
                      </span>
                    </div>
                    <div className="flex flex-col gap-1 bg-muted/20 p-2 rounded-md border border-border/30">
                      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider font-bold">
                        <Shield className="w-3 h-3 text-red-400" /> Stop Loss
                      </div>
                      <span className="font-mono text-xs font-semibold text-red-400/90">
                        {signal.stopLoss ? formatNumber(signal.stopLoss, 5) : "None"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-border/50 flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-3 h-3" />
                    {formatDate(signal.createdAt)}
                  </div>
                  {signal.riskRewardRatio && (
                    <span>RR {formatNumber(signal.riskRewardRatio)}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
