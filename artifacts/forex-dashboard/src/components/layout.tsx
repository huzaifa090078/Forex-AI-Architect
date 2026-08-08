import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, LineChart, Activity, BarChart2, Newspaper,
  Settings, Terminal, LogOut, Hexagon, Sun, Moon,
  Wifi, WifiOff, Clock, Bell, TrendingUp
} from "lucide-react";
import { useGetDashboardSummary } from "@workspace/api-client-react";
import { useTheme } from "@/components/theme-provider";
import { useEffect, useState } from "react";
import { clearTokens } from "@/lib/auth";
import { useLivePrices } from "@/hooks/use-live-prices";

const NAV_ITEMS = [
  { href: "/",          label: "Dashboard",     icon: LayoutDashboard },
  { href: "/market",    label: "Market Scanner",icon: BarChart2 },
  { href: "/charts",    label: "Charts",        icon: LineChart },
  { href: "/signals",   label: "AI Signals",    icon: Activity },
  { href: "/trades",    label: "Open Trades",   icon: TrendingUp },
  { href: "/history",   label: "Trade History", icon: BarChart2 },
  { href: "/news",      label: "News",          icon: Newspaper },
  { href: "/logs",      label: "Logs",          icon: Terminal },
  { href: "/settings",  label: "Settings",      icon: Settings },
];

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-all duration-200 w-full"
      aria-label="Toggle theme"
    >
      {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
      {isDark ? "Light Mode" : "Dark Mode"}
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
    <div className="flex flex-col items-end gap-0.5">
      <span className="text-[10px] font-mono font-bold text-muted-foreground tracking-widest">{utc} UTC</span>
      <span className="text-[9px] font-mono text-muted-foreground/60 tracking-wider">{local} LOCAL</span>
    </div>
  );
}

export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const { data: summary, isLoading } = useGetDashboardSummary();
  const { connected: wsConnected } = useLivePrices();
  const [, setLocation] = useLocation();

  const isAuthRoute = location.startsWith("/auth");
  if (isAuthRoute) return <div className="min-h-screen bg-background">{children}</div>;

  const botStatus      = isLoading ? null : (summary?.botStatus || "stopped");
  const botStatusColor =
    isLoading           ? "bg-muted" :
    botStatus === "running" ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" :
    botStatus === "paused"  ? "bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]" :
    botStatus === "error"   ? "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]" : "bg-gray-500";

  const handleSignOut = () => {
    clearTokens();
    setLocation("/auth/login");
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* ── Sidebar ── */}
      <aside className="w-60 flex-shrink-0 border-r border-sidebar-border bg-sidebar flex flex-col z-10">
        {/* Logo */}
        <div className="h-14 flex items-center px-5 border-b border-sidebar-border">
          <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <Hexagon className="w-6 h-6 text-primary fill-primary/20" />
            <span className="font-bold text-sidebar-foreground tracking-[0.2em]">NEXUS<span className="text-primary">AI</span></span>
          </Link>
        </div>

        {/* Engine Status */}
        <div className="px-5 py-3 border-b border-sidebar-border bg-sidebar/50">
          <div className="flex items-center justify-between">
            <span className="text-[9px] uppercase text-sidebar-foreground/50 font-bold tracking-widest">Engine</span>
            <div className="flex items-center gap-1.5">
              <div className={cn("w-1.5 h-1.5 rounded-full", botStatusColor)} />
              <span className="text-[10px] font-mono text-sidebar-foreground font-bold uppercase tracking-wider">
                {isLoading ? "---" : (botStatus || "STOPPED")}
              </span>
            </div>
          </div>
          {/* MT5 Status */}
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[9px] uppercase text-sidebar-foreground/50 font-bold tracking-widest">MT5</span>
            <span className="text-[10px] font-mono text-red-400 font-bold uppercase tracking-wider">UNAVAILABLE</span>
          </div>
          {/* WS Status */}
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[9px] uppercase text-sidebar-foreground/50 font-bold tracking-widest">Feed</span>
            <div className="flex items-center gap-1.5">
              {wsConnected
                ? <><Wifi className="w-3 h-3 text-emerald-500" /><span className="text-[10px] font-mono text-emerald-500 font-bold tracking-wider">LIVE</span></>
                : <><WifiOff className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] font-mono text-muted-foreground font-bold tracking-wider">OFFLINE</span></>
              }
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive = location === item.href;
            return (
              <Link key={item.href} href={item.href} className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
              )}>
                <item.icon className={cn("w-4 h-4 flex-shrink-0", isActive ? "text-primary" : "")} />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className="p-3 border-t border-sidebar-border bg-sidebar/50 space-y-0.5">
          <ThemeToggle />
          <button
            onClick={handleSignOut}
            className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-all duration-200 w-full"
          >
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-background relative">
        {/* Top Bar */}
        <div className="h-12 border-b border-border/50 bg-card/30 backdrop-blur-sm flex items-center px-6 gap-4 flex-shrink-0 z-10">
          {/* News filter status */}
          <div className="flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-widest">
            <Bell className="w-3.5 h-3.5 text-muted-foreground/50" />
            <span className="text-muted-foreground/50">News</span>
            <span className="text-amber-500">ACTIVE</span>
          </div>

          <div className="flex-1" />

          {/* Clock */}
          <div className="flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-muted-foreground/40" />
            <LiveClock />
          </div>
        </div>

        {/* Content */}
        <div className="absolute inset-0 top-12 pointer-events-none bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/5 via-background to-background" />
        <div className="flex-1 overflow-y-auto p-6 relative z-0">
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
