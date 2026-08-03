import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ThemeProvider, useTheme } from '@/components/theme-provider';
import NotFound from '@/pages/not-found';
import { Route, Switch, Router as WouterRouter } from 'wouter';
import { Layout } from '@/components/layout';
import { Toaster } from "sonner";

import DashboardPage from '@/pages/dashboard';
import TradesPage from '@/pages/trades';
import SignalsPage from '@/pages/signals';
import MarketPage from '@/pages/market';
import BacktestsPage from '@/pages/backtests';
import NewsPage from '@/pages/news';
import LogsPage from '@/pages/logs';
import SettingsPage from '@/pages/settings';
import LoginPage from '@/pages/auth/login';
import RegisterPage from '@/pages/auth/register';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 5000,
      retry: 1,
    },
  },
});

function Router() {
  return (
    <Layout>
      <Switch>
        <Route path="/" component={DashboardPage} />
        <Route path="/trades" component={TradesPage} />
        <Route path="/signals" component={SignalsPage} />
        <Route path="/market" component={MarketPage} />
        <Route path="/backtests" component={BacktestsPage} />
        <Route path="/news" component={NewsPage} />
        <Route path="/logs" component={LogsPage} />
        <Route path="/settings" component={SettingsPage} />
        <Route path="/auth/login" component={LoginPage} />
        <Route path="/auth/register" component={RegisterPage} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function ThemedToaster() {
  const { theme } = useTheme();
  const resolvedTheme = theme === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme;
  return (
    <Toaster
      theme={resolvedTheme as 'dark' | 'light'}
      position="bottom-right"
      className="font-mono text-[10px] uppercase tracking-wider font-bold"
    />
  );
}

function App() {
  return (
    <ThemeProvider defaultTheme="light" storageKey="nexus-ui-theme">
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
            <Router />
          </WouterRouter>
          <ThemedToaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
