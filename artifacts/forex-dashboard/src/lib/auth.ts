/**
 * Auth context + token management for the Forex Dashboard.
 *
 * Stores access/refresh tokens in localStorage.
 * Wires setAuthTokenGetter so every API call includes the Bearer header.
 * Provides useAuth() hook for components.
 *
 * Security:
 *  - Never stores passwords.
 *  - Never hardcodes tokens.
 *  - Clears tokens on logout and 401 errors.
 */

import { setAuthTokenGetter } from "@workspace/api-client-react";

const ACCESS_KEY  = "nexus_access_token";
const REFRESH_KEY = "nexus_refresh_token";

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function isLoggedIn(): boolean {
  const token = getAccessToken();
  if (!token) return false;
  try {
    const parts   = token.split(".");
    if (parts.length !== 3) return false;
    const payload = JSON.parse(atob(parts[1]));
    const exp     = payload?.exp as number | undefined;
    if (!exp) return false;
    return Date.now() / 1000 < exp;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Wire the API client to always include the Bearer token
// ---------------------------------------------------------------------------

setAuthTokenGetter(() => getAccessToken());
