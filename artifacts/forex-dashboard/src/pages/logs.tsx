import { useState } from "react";
import { useGetLogs } from "@workspace/api-client-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Terminal, RefreshCw, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function LogsPage() {
  const [level, setLevel] = useState<any>("all");
  const { data: logsData, isLoading, refetch, isFetching } = useGetLogs({ limit: 100, level: level !== "all" ? level : undefined });

  return (
    <div className="space-y-6 h-[calc(100vh-120px)] flex flex-col animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">System Logs</h1>
          <p className="text-muted-foreground mt-1 text-sm">Raw output stream from the core execution engine.</p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching} className="h-9 text-xs font-bold tracking-wider uppercase border-border/50 bg-card/50 hover:bg-muted/50">
            <RefreshCw className={cn("w-3 h-3 mr-2", isFetching && "animate-spin")} /> Refresh
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3 pb-2">
        <Filter className="w-4 h-4 text-muted-foreground/50" />
        <div className="flex gap-2 overflow-x-auto custom-scrollbar pb-1">
          {["all", "debug", "info", "warning", "error", "critical"].map(l => (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={cn(
                "px-3 py-1.5 rounded-md text-[10px] font-mono font-bold uppercase tracking-widest transition-all",
                level === l 
                  ? "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(20,184,166,0.3)] border border-primary/50" 
                  : "bg-muted/40 text-muted-foreground hover:bg-muted/80 border border-transparent"
              )}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <Card className="flex-1 min-h-0 bg-gray-950 border-border/50 shadow-2xl flex flex-col overflow-hidden rounded-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-gray-900">
          <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground tracking-widest">
            <Terminal className="w-4 h-4 text-primary" /> /var/log/nexus/engine.log
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[10px] font-mono font-bold text-emerald-500 uppercase tracking-widest">Live Stream</span>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-5 custom-scrollbar bg-[linear-gradient(to_bottom,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:100%_24px]">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({length: 15}).map((_, i) => <Skeleton key={i} className="h-5 w-full bg-white/5 rounded-none" />)}
            </div>
          ) : logsData?.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-white/30 font-mono text-sm gap-2">
              <span className="opacity-50">0x000000 EOF</span>
              <span className="text-xs">NO_LOG_ENTRIES_FOUND</span>
            </div>
          ) : (
            <div className="font-mono text-[11px] leading-[24px] tracking-tight">
              {logsData?.items.map(log => (
                <div key={log.id} className="flex flex-col sm:flex-row sm:gap-4 hover:bg-white/5 px-2 -mx-2 rounded-sm transition-colors border-l-2 border-transparent hover:border-white/20">
                  <span className="text-white/30 whitespace-nowrap shrink-0 selection:bg-primary selection:text-primary-foreground">
                    {(() => { try { return new Date(log.createdAt).toISOString().replace('T', ' ').substring(0, 23); } catch { return log.createdAt ?? '---'; } })()}
                  </span>
                  <span className={cn("uppercase font-bold w-[80px] shrink-0", 
                    log.level === "error" || log.level === "critical" ? "text-red-400" :
                    log.level === "warning" ? "text-amber-400" :
                    log.level === "info" ? "text-blue-400" : "text-white/40"
                  )}>
                    [{log.level}]
                  </span>
                  <span className="text-primary/80 w-[140px] shrink-0 truncate font-semibold">
                    {log.module}
                  </span>
                  <span className={cn("break-words selection:bg-primary selection:text-primary-foreground", 
                     log.level === "error" || log.level === "critical" ? "text-red-300 font-medium" : "text-white/70"
                  )}>
                    {log.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
