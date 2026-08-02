import { useGetNews } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Globe, AlertTriangle } from "lucide-react";

export default function NewsPage() {
  const { data: newsData, isLoading } = useGetNews();

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Economic Calendar</h1>
        <p className="text-muted-foreground mt-1 text-sm">Upcoming fundamental events mapped against currency pairs.</p>
      </div>

      <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg">
        <CardHeader className="border-b border-border/50 pb-4">
          <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <Globe className="w-4 h-4 text-blue-500" /> Fundamental Data Feed
          </CardTitle>
        </CardHeader>
        <div className="rounded-b-md overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="w-[180px] pl-6">Schedule (UTC)</TableHead>
                <TableHead className="w-[80px]">Pair</TableHead>
                <TableHead className="w-[120px]">Impact</TableHead>
                <TableHead>Event Descriptor</TableHead>
                <TableHead className="text-right">Actual</TableHead>
                <TableHead className="text-right">Forecast</TableHead>
                <TableHead className="text-right pr-6">Previous</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({length: 10}).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-6"><Skeleton className="h-4 w-24" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-64" /></TableCell>
                    <TableCell className="text-right"><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                    <TableCell className="text-right"><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                    <TableCell className="text-right pr-6"><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                  </TableRow>
                ))
              ) : newsData?.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-48 text-center text-muted-foreground border-dashed">
                    <span className="font-mono text-sm tracking-widest font-bold opacity-50">NO_UPCOMING_EVENTS</span>
                  </TableCell>
                </TableRow>
              ) : (
                newsData?.map(item => (
                  <TableRow key={item.id} className="group">
                    <TableCell className="pl-6 font-mono text-muted-foreground text-[11px] whitespace-nowrap">
                      {formatDate(item.publishedAt)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-bold text-[10px] px-1.5 py-0 border-border bg-muted/20">
                        {item.currency}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="flex gap-0.5">
                          {[1, 2, 3].map(level => (
                            <div key={level} className={cn("w-1.5 h-3.5 rounded-sm",
                              item.impact === "high" && level <= 3 ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]" :
                              item.impact === "medium" && level <= 2 ? "bg-amber-500" :
                              item.impact === "low" && level <= 1 ? "bg-blue-400" : "bg-muted/30"
                            )} />
                          ))}
                        </div>
                        {item.impact === "high" && <AlertTriangle className="w-3 h-3 text-red-500" />}
                      </div>
                    </TableCell>
                    <TableCell className="font-medium text-sm text-foreground/90">
                      {item.headline}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm font-bold text-foreground">
                      {item.actual || <span className="text-muted-foreground/30">---</span>}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm text-muted-foreground">
                      {item.forecast || <span className="text-muted-foreground/30">---</span>}
                    </TableCell>
                    <TableCell className="text-right pr-6 font-mono text-sm text-muted-foreground/50">
                      {item.previous || <span className="text-muted-foreground/30">---</span>}
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
