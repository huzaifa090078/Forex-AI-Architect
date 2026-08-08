/**
 * useWebSocket — single shared WebSocket connection for real-time data.
 *
 * Connects to /api/ws (backend WebSocket endpoint).
 * Automatically reconnects on disconnect (max 5 attempts, exponential backoff).
 * Dispatches typed messages via an onMessage callback.
 *
 * Security: never sends credentials through the WebSocket.
 */

import { useEffect, useRef, useCallback, useState } from "react";

export type WsTickMessage = {
  type:   "tick";
  pair:   string;
  bid:    number;
  ask:    number;
  spread: number;
  time:   string;
};

export type WsStatusMessage = {
  type:              "status";
  bot_status:        string;
  news_filter_ok:    boolean;
  mt5_available:     boolean;
  last_refresh:      string | null;
  time:              string;
};

export type WsMessage = WsTickMessage | WsStatusMessage | { type: "pong"; time: string };

type Options = {
  onMessage?: (msg: WsMessage) => void;
  enabled?:   boolean;
};

const MAX_RECONNECTS = 5;
const BASE_DELAY_MS  = 1500;

function buildWsUrl(): string {
  const base = import.meta.env.BASE_URL?.replace(/\/$/, "") ?? "";
  const host = window.location.host;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${host}${base}/api/ws`;
}

export function useWebSocket({ onMessage, enabled = true }: Options = {}) {
  const wsRef        = useRef<WebSocket | null>(null);
  const attemptsRef  = useRef(0);
  const timerRef     = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef   = useRef(true);
  const [connected, setConnected] = useState(false);

  const onMessageRef = useRef(onMessage);
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return;
    try {
      const url = buildWsUrl();
      const ws  = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return; }
        attemptsRef.current = 0;
        setConnected(true);
        // Send ping immediately
        ws.send(JSON.stringify({ type: "ping" }));
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data) as WsMessage;
          onMessageRef.current?.(msg);
        } catch {/* ignore malformed frames */}
      };

      ws.onclose = () => {
        setConnected(false);
        if (!mountedRef.current || !enabled) return;
        const attempts = attemptsRef.current;
        if (attempts < MAX_RECONNECTS) {
          const delay = BASE_DELAY_MS * Math.pow(2, attempts);
          attemptsRef.current = attempts + 1;
          timerRef.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // WebSocket unavailable (dev env, etc.) — fail silently
    }
  }, [enabled]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) connect();
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect, enabled]);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "ping" }));
    }
  }, []);

  return { connected, sendPing };
}
