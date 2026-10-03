import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, LineChart, Activity, BarChart2, Newspaper,
  Settings, Terminal, Hexagon, Sun, Moon,
  Wifi, WifiOff, Clock, Bell, TrendingUp, ShieldCheck, Cpu
} from "lucide-react";
import { useGetDashboardSummary } from "@workspace/api-client-react";
import { useTheme } from "@/components/theme-provider";
import { useEffect, useState } from "react";
import { clearTokens } from "@/lib/auth";
import { useLivePrices } from "@/hooks/use-live-prices";

const NAV_ITEMS = [
  { href: "/",          label: "Command Center", icon: LayoutDashboard },
  { href: "/market",    label: "Market Scanner", icon: BarChart2 },
  { href: "/charts",    label: "Advanced Charts",icon: LineChart },
  { href: "/signals",   label: "AI Signals",     icon: Activity },
  { href: "/trades",    label: "Open Positions", icon: TrendingUp },
  { href: "/history",   label: "Trade History",  icon: ShieldCheck },
  { href: "/news",      label: "News Feed",      icon: Newspaper },
  { href: "/logs",      label: "System Logs",    icon: Terminal },
  { href: "/settings",  label: "Risk & Config",  icon: Settings },
];

function HeaderThemeToggle() {
  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark" || (theme === "system" && (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches));
  
  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs font-mono font-medium border border-border/60 bg-card/60 hover:bg-card hover:border-primary/40 text-foreground transition-all duration-150 shadow-2xs cursor-pointer"
      title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
      aria-label="Toggle theme mode"
    >
      {isDark ? (
        <>
          <Sun className="w-3.5 h-3.5 text-amber-400" />
          <span className="hidden sm:inline text-[11px] font-semibold text-muted-foreground hover:text-foreground">LIGHT</span>
        </>
      ) : (
        <>
          <Moon className="w-3.5 h-3.5 text-primary" />
          <span className="hidden sm:inline text-[11px] font-semibold text-muted-foreground hover:text-foreground">DARK</span>
        </>
      )}
    </button>
  );
}

function LiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const utc   = now.toUTCString().replace(/.*(\d\d:\d\d:\d\d).*/, "$1");
  const local = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (
    <div className="flex items-center gap-2.5 text-right font-mono text-[11px] text-muted-foreground/90">
      <div className="flex items-center gap-1 bg-muted/40 px-2 py-0.5 rounded border border-border/40">
        <span className="text-foreground font-bold">{utc}</span>
        <span className="text-[9px] text-muted-foreground/70">UTC</span>
      </div>
      <div className="hidden md:flex items-center gap-1 bg-muted/30 px-2 py-0.5 rounded border border-border/30">
        <span className="text-muted-foreground font-medium">{local}</span>
        <span className="text-[9px] text-muted-foreground/60">LOC</span>
      </div>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";

async function fetchMT5Summary() {
  const token = localStorage.getItem("forex_access_token") || localStorage.getItem("nexus_access_token");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch("/api/v1/mt5/summary?days=30", { headers });
  if (!res.ok) throw new Error("Failed to fetch MT5 summary");
  return res.json();
}

export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const { data: summary, isLoading } = useGetDashboardSummary();
  const { connected: wsConnected } = useLivePrices();

  // Unified MT5 live status shared with dashboard
  const { data: mt5Data } = useQuery({
    queryKey: ["mt5-summary"],
    queryFn: fetchMT5Summary,
    refetchInterval: 5000,
    retry: 2,
  });

  const isMt5Active = Boolean(
    mt5Data?.connected ||
    (summary as any)?.mt5Connected ||
    (summary as any)?.mt5_connected
  );
  const mt5Account = mt5Data?.account;

  const botStatus = isLoading ? null : (summary?.botStatus || (isMt5Active ? "running" : "stopped"));

  return (
    <div className="flex h-screen overflow-hidden bg-background font-sans text-foreground selection:bg-primary/20 selection:text-primary">
      {/* ── Sidebar ── */}
      <aside className="w-60 flex-shrink-0 border-r border-sidebar-border bg-sidebar flex flex-col z-20 shadow-sm">
        {/* Logo / Terminal Branding */}
        <div className="h-14 flex items-center px-4 border-b border-sidebar-border gap-2.5 bg-sidebar/80">
          <div className="w-8 h-8 rounded-md bg-primary/10 border border-primary/30 flex items-center justify-center text-primary shadow-xs">
            <Cpu className="w-4 h-4" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="font-mono text-xs font-black tracking-widest text-foreground">
              FOREX<span className="text-primary">·AI</span>
            </span>
            <span className="text-[9px] font-mono tracking-wider text-muted-foreground font-medium">
              TERMINAL ARCHITECT
            </span>
          </div>
        </div>

        {/* Engine Telemetry Strip */}
        <div className="p-3 border-b border-sidebar-border bg-sidebar-accent/30 space-y-2">
          {/* Engine */}
          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="text-muted-foreground font-semibold uppercase text-[9px] tracking-wider">Bot Engine</span>
            <div className="flex items-center gap-1.5">
              <span className={cn(
                "w-1.5 h-1.5 rounded-full",
                isLoading ? "bg-muted-foreground" :
                botStatus === "running" ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)]" :
                botStatus === "paused"  ? "bg-amber-500" : "bg-rose-500"
              )} />
              <span className={cn(
                "font-bold text-[10px] tracking-wider uppercase",
                botStatus === "running" ? "text-emerald-500 dark:text-emerald-400" : "text-muted-foreground"
              )}>
                {isLoading ? "---" : (botStatus || "STOPPED")}
              </span>
            </div>
          </div>

          {/* MT5 Bridge */}
          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="text-muted-foreground font-semibold uppercase text-[9px] tracking-wider">MT5 Terminal</span>
            <div className="flex items-center gap-1.5">
              <span className={cn(
                "w-1.5 h-1.5 rounded-full",
                isMt5Active ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)]" : "bg-amber-500"
              )} />
              <span className={cn(
                "font-bold text-[10px] tracking-wider uppercase",
                isMt5Active ? "text-emerald-500 dark:text-emerald-400" : "text-amber-500 dark:text-amber-400"
              )}>
                {isMt5Active ? "CONNECTED" : "OFFLINE"}
              </span>
            </div>
          </div>

          {/* Feed */}
          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="text-muted-foreground font-semibold uppercase text-[9px] tracking-wider">Market Feed</span>
            <div className="flex items-center gap-1.5">
              {wsConnected ? (
                <>
                  <Wifi className="w-3 h-3 text-emerald-500 dark:text-emerald-400" />
                  <span className="font-bold text-[10px] text-emerald-500 dark:text-emerald-400 tracking-wider">LIVE</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-3 h-3 text-muted-foreground/60" />
                  <span className="font-bold text-[10px] text-muted-foreground/60 tracking-wider">STANDBY</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2.5 px-2 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = location === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-xs font-mono font-medium transition-all duration-150 relative",
                  isActive
                    ? "bg-primary/10 text-primary border-l-2 border-primary font-bold shadow-2xs"
                    : "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-foreground border-l-2 border-transparent"
                )}
              >
                <item.icon className={cn("w-4 h-4 flex-shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
                <span className="truncate tracking-wide">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-sidebar-border bg-sidebar/50 flex items-center justify-between text-[10px] font-mono text-muted-foreground/70">
          <span>STABLE v2.4.0</span>
          <span className="text-primary font-semibold">DEMO TEST</span>
        </div>
      </aside>

      {/* ── Main Area ── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-background relative">
        {/* Terminal Top Command Bar */}
        <header className="h-14 border-b border-border/60 bg-card/40 backdrop-blur-md flex items-center justify-between px-6 gap-4 flex-shrink-0 z-10">
          {/* Left: Terminal Status Pills */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold tracking-wider text-foreground">
                COMMAND CENTER
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-primary/30 bg-primary/10 text-primary font-bold">
                INSTITUTIONAL
              </span>
            </div>

            <div className="hidden sm:flex items-center gap-2 border-l border-border/60 pl-3">
              {/* MT5 Pill */}
              <div className={cn(
                "flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold border",
                isMt5Active
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                  : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30"
              )}>
                <span className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  isMt5Active ? "bg-emerald-500 animate-pulse shadow-[0_0_6px_rgba(16,185,129,0.7)]" : "bg-amber-500"
                )} />
                <span>MT5: {isMt5Active ? "CONNECTED" : "OFFLINE"}</span>
              </div>

              {/* News Pill */}
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-muted/40 text-muted-foreground border border-border/40">
                <Bell className="w-2.5 h-2.5 text-amber-500" />
                <span>NEWS GUARD ON</span>
              </div>
            </div>
          </div>

          {/* Right: Live Clocks & Theme Switcher */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-muted-foreground/60 hidden sm:inline" />
              <LiveClock />
            </div>

            {/* Prominent Theme Toggle Button at Top-Right */}
            <HeaderThemeToggle />
          </div>
        </header>

        {/* Subtle Ambient Gradient Overlay */}
        <div className="absolute inset-0 top-14 pointer-events-none bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/5 via-background to-background" />

        {/* Content Viewport */}
        <div className="flex-1 overflow-y-auto p-6 relative z-0">
          <div className="max-w-7xl mx-auto space-y-6">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}

