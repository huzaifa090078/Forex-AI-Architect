/**
 * useLivePrices — subscribes to WebSocket tick messages and maintains
 * a live price map keyed by pair symbol.
 *
 * Falls back gracefully when WebSocket is unavailable.
 * Never fabricates prices.
 */

import { useState, useCallback, useRef } from "react";
import { useWebSocket, WsMessage, WsTickMessage } from "./use-websocket";

export type PriceTick = {
  bid:       number;
  ask:       number;
  spread:    number;
  updatedAt: Date;
};

export type LivePriceMap = Record<string, PriceTick>;

export function useLivePrices(): {
  prices:    LivePriceMap;
  connected: boolean;
  botStatus: string | null;
} {
  const [prices,    setPrices]    = useState<LivePriceMap>({});
  const [botStatus, setBotStatus] = useState<string | null>(null);
  const pendingRef = useRef<LivePriceMap>({});

  const handleMessage = useCallback((msg: WsMessage) => {
    if (msg.type === "tick") {
      const tick = msg as WsTickMessage;
      pendingRef.current = {
        ...pendingRef.current,
        [tick.pair]: {
          bid:       tick.bid,
          ask:       tick.ask,
          spread:    tick.spread,
          updatedAt: new Date(tick.time),
        },
      };
      // Batch state update (rAF avoids excessive re-renders)
      requestAnimationFrame(() => {
        setPrices(prev => ({ ...prev, ...pendingRef.current }));
        pendingRef.current = {};
      });
    } else if (msg.type === "status") {
      setBotStatus((msg as any).bot_status ?? null);
    }
  }, []);

  const { connected } = useWebSocket({ onMessage: handleMessage });

  return { prices, connected, botStatus };
}
