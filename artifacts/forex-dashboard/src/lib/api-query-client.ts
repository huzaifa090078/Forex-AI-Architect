/**
 * Shared QueryClient with global 401 → redirect to /auth/login.
 * Import this instead of creating a new QueryClient in App.tsx.
 */

import { QueryClient } from "@tanstack/react-query";
import { clearTokens } from "@/lib/auth";

let _redirecting = false;

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 5000,
      retry: (failureCount, error: any) => {
        // On 401, clear tokens + redirect — but never when already on auth pages
        if (error?.status === 401 || error?.response?.status === 401) {
          const onAuthPage = window.location.pathname.includes("/auth/");
          if (!_redirecting && !onAuthPage) {
            _redirecting = true;
            clearTokens();
            setTimeout(() => {
              const base = (import.meta.env.BASE_URL ?? "/").replace(/\/$/, "");
              window.location.href = `${base}/auth/login`;
              _redirecting = false;
            }, 100);
          }
          return false;
        }
        return failureCount < 1;
      },
    },
    mutations: {
      retry: false,
    },
  },
});
