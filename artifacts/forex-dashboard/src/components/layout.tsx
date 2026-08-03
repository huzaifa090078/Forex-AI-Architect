import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import { 
  LayoutDashboard, 
  LineChart, 
  Activity, 
  BarChart2, 
  History, 
  Newspaper, 
  Settings, 
  TerminalSquare,
  LogOut,
  Hexagon,
  Sun,
  Moon,
} from "lucide-react";
import { useGetDashboardSummary } from "@workspace/api-client-react";
import { useTheme } from "@/components/theme-provider";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/trades", label: "Trades", icon: LineChart },
  { href: "/signals", label: "Signals", icon: Activity },
  { href: "/market", label: "Market", icon: BarChart2 },
  { href: "/backtests", label: "Backtests", icon: History },
  { href: "/news", label: "News", icon: Newspaper },
  { href: "/logs", label: "Logs", icon: TerminalSquare },
  { href: "/settings", label: "Settings", icon: Settings },
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

export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  
  // Safe fetch if user might not be logged in, we let it fail gracefully
  const { data: summary, isLoading } = useGetDashboardSummary({ query: { retry: false } });

  const isAuthRoute = location.startsWith("/auth");

  if (isAuthRoute) {
    return <div className="min-h-screen bg-background">{children}</div>;
  }

  const botStatusColor = 
    isLoading ? "bg-muted" :
    summary?.botStatus === "running" ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" :
    summary?.botStatus === "paused" ? "bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]" :
    summary?.botStatus === "error" ? "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]" : "bg-gray-500";

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-sidebar-border bg-sidebar flex flex-col z-10">
        <div className="h-16 flex items-center px-6 border-b border-sidebar-border">
          <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <Hexagon className="w-6 h-6 text-primary fill-primary/20" />
            <span className="font-bold text-sidebar-foreground tracking-[0.2em]">NEXUS<span className="text-primary">AI</span></span>
          </Link>
        </div>

        <div className="px-6 py-4 border-b border-sidebar-border bg-sidebar/50">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase text-sidebar-foreground/50 font-bold tracking-widest">Engine Status</span>
            <div className="flex items-center gap-2">
              <div className={cn("w-2 h-2 rounded-full", botStatusColor)} />
              <span className="text-xs font-mono text-sidebar-foreground font-medium uppercase tracking-wider">
                {isLoading ? "---" : (summary?.botStatus || "STOPPED")}
              </span>
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = location === item.href;
            return (
              <Link key={item.href} href={item.href} className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-200",
                isActive 
                  ? "bg-primary/10 text-primary shadow-sm" 
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
              )}>
                <item.icon className={cn("w-4 h-4", isActive ? "text-primary" : "")} />
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-sidebar-border bg-sidebar/50 space-y-1">
          <ThemeToggle />
          <Link href="/auth/login" className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-all duration-200">
            <LogOut className="w-4 h-4" />
            Sign Out
          </Link>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-background relative">
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/5 via-background to-background" />
        <div className="flex-1 overflow-y-auto p-8 relative z-0">
          <div className="max-w-7xl mx-auto space-y-8">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
