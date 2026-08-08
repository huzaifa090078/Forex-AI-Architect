/**
 * Shared QueryClient — no auth redirect (auth bypassed until bot goes live).
 */

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 5000,
      retry: 1,
    },
    mutations: {
      retry: false,
    },
  },
});
