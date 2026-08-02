import { useGetMarketPairs, useScanMarket } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber, formatPercent, cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Radar, ArrowUpRight, ArrowDownRight, Minus, Search, Activity } from "lucide-react";

export default function MarketPage() {
  const { data: pairsData, isLoading: isPairsLoading } = useGetMarketPairs();
  const { data: scanData, isLoading: isScanLoading } = useScanMarket();

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Market Overview</h1>
        <p className="text-muted-foreground mt-1 text-sm">Live forex rates and real-time scanner opportunities.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left Panel: Live Pairs Table */}
        <Card className="xl:col-span-2 bg-card/50 backdrop-blur border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-500" /> Live Quotes
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30">
                  <TableHead className="w-[120px] pl-6">Symbol</TableHead>
                  <TableHead>Bid / Ask</TableHead>
                  <TableHead>Spread</TableHead>
                  <TableHead>24h Change</TableHead>
                  <TableHead>Trend</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isPairsLoading ? (
                  Array.from({length: 8}).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell className="pl-6"><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-8" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                      <TableCell><Skeleton className="h-6 w-16" /></TableCell>
                    </TableRow>
                  ))
                ) : pairsData?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="h-32 text-center text-muted-foreground border-dashed">
                      <span className="font-mono text-sm">NO_DATA_AVAILABLE</span>
                    </TableCell>
                  </TableRow>
                ) : (
                  pairsData?.map(pair => (
                    <TableRow key={pair.symbol} className="group">
                      <TableCell className="pl-6 font-bold tracking-wide text-sm">{pair.symbol}</TableCell>
                      <TableCell className="font-mono text-sm">
                        <span className="text-muted-foreground/80">{formatNumber(pair.bid, 5)}</span>
                        <span className="text-muted-foreground/30 mx-2">/</span>
                        <span className="text-foreground/90">{formatNumber(pair.ask, 5)}</span>
                      </TableCell>
                      <TableCell className="font-mono text-sm text-muted-foreground font-bold">
                        {pair.spread}
                      </TableCell>
                      <TableCell>
                        <span className={cn("font-mono text-sm font-bold flex items-center gap-1",
                          pair.change24h > 0 ? "text-emerald-500" : pair.change24h < 0 ? "text-red-500" : "text-muted-foreground"
                        )}>
                          {pair.change24h > 0 ? <ArrowUpRight className="w-3 h-3" /> : pair.change24h < 0 ? <ArrowDownRight className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                          {formatPercent(Math.abs(pair.change24h) / 100, 2)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn("px-2 text-[10px] uppercase font-bold border",
                          pair.trend === "bullish" ? "border-emerald-500/30 text-emerald-500 bg-emerald-500/10" :
                          pair.trend === "bearish" ? "border-red-500/30 text-red-500 bg-red-500/10" : "border-border text-muted-foreground"
                        )}>
                          {pair.trend}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Right Panel: Market Scanner */}
        <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg flex flex-col h-[calc(100vh-12rem)] min-h-[500px]">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Radar className="w-4 h-4 text-primary animate-[spin_3s_linear_infinite]" /> Active Scanner
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 flex-1 overflow-auto space-y-4 relative">
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:14px_14px] pointer-events-none" />
            <div className="relative z-10 space-y-4">
              {isScanLoading ? (
                 Array.from({length: 4}).map((_, i) => (
                  <Card key={i} className="bg-background/50 border-border/30 backdrop-blur"><CardContent className="p-4"><Skeleton className="h-16 w-full" /></CardContent></Card>
                 ))
              ) : scanData?.length === 0 ? (
                 <div className="flex flex-col items-center justify-center h-48 text-muted-foreground gap-3 opacity-60">
                   <Search className="w-8 h-8" />
                   <span className="font-mono text-xs font-bold tracking-widest">SCANNER_IDLE</span>
                 </div>
              ) : (
                 scanData?.map((opp, idx) => (
                   <div key={idx} className="p-4 rounded-lg border border-border/50 bg-background/50 backdrop-blur hover:bg-muted/30 transition-colors shadow-sm relative overflow-hidden group">
                     <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary/50 group-hover:bg-primary transition-colors" />
                     <div className="flex justify-between items-start mb-4">
                       <div className="flex flex-col gap-1">
                         <span className="font-bold tracking-wide text-sm">{opp.pair}</span>
                         <span className="text-[10px] font-mono text-primary font-bold bg-primary/10 px-1.5 py-0.5 rounded w-fit uppercase border border-primary/20">
                           {opp.timeframe}
                         </span>
                       </div>
                       <Badge variant={opp.direction === "buy" ? "buy" : "sell"} className="text-[10px] px-2 py-0.5 rounded shadow-sm">
                         {opp.direction}
                       </Badge>
                     </div>
                     
                     <div className="space-y-4">
                       <div>
                         <div className="flex justify-between text-[10px] uppercase font-bold text-muted-foreground mb-1.5">
                           <span className="tracking-widest">Match Score</span>
                           <span className="font-mono text-primary">{opp.score}%</span>
                         </div>
                         <div className="h-1 w-full bg-muted/50 rounded-full overflow-hidden">
                           <div 
                             className="h-full bg-primary transition-all shadow-[0_0_10px_rgba(20,184,166,0.8)]" 
                             style={{ width: `${opp.score}%` }}
                           />
                         </div>
                       </div>
                       
                       <div className="text-xs">
                         <span className="text-[9px] uppercase text-muted-foreground font-bold tracking-widest block mb-1">Detected Pattern</span>
                         <span className="font-medium text-foreground/90">{opp.smcPattern}</span>
                       </div>

                       {opp.confluenceFactors && opp.confluenceFactors.length > 0 && (
                         <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-border/30">
                           {opp.confluenceFactors.map((factor, i) => (
                             <span key={i} className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-muted/30 border border-border/50 text-muted-foreground font-bold">
                               {factor}
                             </span>
                           ))}
                         </div>
                       )}
                     </div>
                   </div>
                 ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
