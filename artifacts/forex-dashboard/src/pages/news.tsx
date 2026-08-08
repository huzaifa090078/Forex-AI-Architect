/**
 * News page — uses Section 10 News Filter API.
 * Shows NewsEvent records (event_name, event_time, currency, impact, status).
 * Does NOT fabricate news events.
 */

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Globe, AlertTriangle, RefreshCw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";

type NewsEvent = {
  id:               string;
  event_name:       string;
  currency:         string;
  impact:           string;
  event_time:       string;
  status:           string;
  affected_pairs:   string[];
  minutes_to_event: number | null;
  actual:           string | null;
  forecast:         string | null;
  previous:         string | null;
};

type NewsStatus = {
  provider_available:    boolean;
  filter_enabled:        boolean;
  high_impact_enabled:   boolean;
  cached_event_count:    number;
  high_impact_count:     number;
  pause_before_minutes:  number;
  resume_after_minutes:  number;
};

function buildUrl(path: string) {
  return `${(import.meta.env.BASE_URL ?? "").replace(/\/$/, "")}/api${path}`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${localStorage.getItem("nexus_access_token") ?? ""}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function impactBars(impact: string) {
  return (
    <div className="flex gap-0.5 items-center">
      {[1, 2, 3].map(l => (
        <div key={l} className={cn("w-1.5 h-3.5 rounded-sm",
          impact === "high"   && l <= 3 ? "bg-red-500"    :
          impact === "medium" && l <= 2 ? "bg-amber-500"  :
          impact === "low"    && l <= 1 ? "bg-blue-400"   : "bg-muted/30"
        )} />
      ))}
    </div>
  );
}

function countdown(minutes: number | null): string {
  if (minutes === null) return "---";
  if (minutes < 0)      return "LIVE";
  const h = Math.floor(minutes / 60);
  const m = Math.floor(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function statusBadgeClass(status: string): string {
  if (status === "live")     return "bg-red-500/20 text-red-400 border-red-500/30";
  if (status === "upcoming") return "bg-amber-500/20 text-amber-400 border-amber-500/30";
  return "bg-muted/30 text-muted-foreground border-border/30";
}

export default function NewsPage() {
  const [impact, setImpact] = useState<"all" | "high" | "medium" | "low">("all");

  const { data: events, isLoading, refetch, isFetching } = useQuery<NewsEvent[]>({
    queryKey: ["news-events", impact],
    queryFn:  () => fetchJson<NewsEvent[]>(
      `/v1/news${impact !== "all" ? `?impact=${impact}` : ""}`
    ),
    staleTime: 60_000,
    retry: 1,
  });

  const { data: status } = useQuery<NewsStatus>({
    queryKey: ["news-status"],
    queryFn:  () => fetchJson<NewsStatus>("/v1/news/status"),
    staleTime: 30_000,
    retry: 1,
  });

  const filtered = events ?? [];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Economic Calendar</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Upcoming events mapped against currency pairs</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}
          className="h-8 text-[10px] font-bold uppercase tracking-widest border-border/50 bg-card/50">
          <RefreshCw className={cn("w-3 h-3 mr-1.5", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* System status */}
      {status && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Filter",    val: status.filter_enabled ? "ENABLED" : "DISABLED",      color: status.filter_enabled ? "text-emerald-500" : "text-muted-foreground" },
            { label: "Provider",  val: status.provider_available ? "CONNECTED" : "OFFLINE",  color: status.provider_available ? "text-emerald-500" : "text-amber-500" },
            { label: "Events",    val: `${status.cached_event_count} cached`,                color: "text-foreground" },
            { label: "High",      val: `${status.high_impact_count} high-impact`,            color: "text-red-400" },
          ].map(s => (
            <Card key={s.label} className="bg-card/50 border-border/50">
              <CardContent className="p-3 flex flex-col gap-1">
                <span className="text-[9px] uppercase font-bold tracking-widest text-muted-foreground">{s.label}</span>
                <span className={cn("text-[11px] font-mono font-bold", s.color)}>{s.val}</span>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pause info */}
      {status && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-amber-500 text-[11px] font-mono">
          <ShieldAlert className="w-4 h-4 flex-shrink-0" />
          <span>
            Trading paused <strong>{status.pause_before_minutes} min</strong> before
            and resumed <strong>{status.resume_after_minutes} min</strong> after high-impact events.
          </span>
        </div>
      )}

      {/* Impact filter */}
      <div className="flex gap-2">
        {(["all", "high", "medium", "low"] as const).map(lvl => (
          <button key={lvl} onClick={() => setImpact(lvl)}
            className={cn("px-3 py-1.5 rounded-md text-[10px] font-mono font-bold uppercase tracking-widest transition-all",
              impact === lvl
                ? "bg-primary text-primary-foreground"
                : "bg-muted/40 text-muted-foreground hover:bg-muted/80"
            )}>
            {lvl}
          </button>
        ))}
      </div>

      {/* Events table */}
      <Card className="bg-card/50 border-border/50 shadow-lg">
        <CardHeader className="border-b border-border/50 pb-4">
          <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <Globe className="w-4 h-4 text-blue-500" /> News Events Feed
          </CardTitle>
        </CardHeader>
        <div className="rounded-b-md overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="pl-6 w-[160px]">Time (UTC)</TableHead>
                <TableHead className="w-[80px]">Currency</TableHead>
                <TableHead className="w-[80px]">Impact</TableHead>
                <TableHead>Event</TableHead>
                <TableHead className="w-[120px]">Affected Pairs</TableHead>
                <TableHead className="w-[100px]">Countdown</TableHead>
                <TableHead className="w-[90px]">Status</TableHead>
                <TableHead className="text-right">Actual</TableHead>
                <TableHead className="text-right pr-6">Forecast</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 9 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : filtered.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="h-40 text-center text-muted-foreground">
                    <div className="flex flex-col items-center gap-3">
                      <AlertTriangle className="w-8 h-8 opacity-30" />
                      <span className="font-mono text-sm font-bold tracking-widest opacity-50">NO_EVENTS_FOUND</span>
                      <span className="text-xs opacity-40">
                        No news provider configured — events shown when provider is set up.
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map(ev => (
                  <TableRow key={ev.id} className={cn("group",
                    ev.status === "live" && "bg-red-500/5 border-red-500/20"
                  )}>
                    <TableCell className="pl-6 font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                      {new Date(ev.event_time).toUTCString().replace(/.*(\w{3}, \d+ \w+ \d+ \d+:\d+).*/, "$1")}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-bold text-[10px] px-1.5 py-0">
                        {ev.currency}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        {impactBars(ev.impact)}
                        {ev.impact === "high" && <AlertTriangle className="w-3 h-3 text-red-500" />}
                      </div>
                    </TableCell>
                    <TableCell className="font-medium text-sm">{ev.event_name}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-0.5">
                        {ev.affected_pairs.slice(0, 3).map(p => (
                          <span key={p} className="text-[9px] font-mono bg-muted/50 px-1 rounded">{p}</span>
                        ))}
                        {ev.affected_pairs.length > 3 && (
                          <span className="text-[9px] font-mono text-muted-foreground">+{ev.affected_pairs.length - 3}</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className={cn("font-mono text-[11px] font-bold",
                        ev.status === "live" ? "text-red-400" : "text-amber-400"
                      )}>
                        {countdown(ev.minutes_to_event)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className={cn("text-[9px] font-mono font-bold px-2 py-0.5 rounded border uppercase", statusBadgeClass(ev.status))}>
                        {ev.status}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm font-bold">
                      {ev.actual || <span className="text-muted-foreground/30">---</span>}
                    </TableCell>
                    <TableCell className="text-right pr-6 font-mono text-sm text-muted-foreground">
                      {ev.forecast || <span className="text-muted-foreground/30">---</span>}
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
