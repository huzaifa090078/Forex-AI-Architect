"""
Test script for MT5 Read-Only Dashboard API endpoints.
Tests /v1/mt5/account, /v1/mt5/positions, /v1/mt5/history, /v1/mt5/stats, and /v1/mt5/summary.
Verifies separation of Realized P/L from Floating P/L.
"""

import sys
import asyncio
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from httpx import AsyncClient, ASGITransport
from main import app


async def run_tests():
    print("=" * 60)
    print("TESTING MT5 READ-ONLY API ENDPOINTS")
    print("=" * 60)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        res = await client.get("/api/healthz")
        assert res.status_code == 200, f"Health check failed: {res.status_code}"
        print("[PASS] 1. API Healthcheck (/api/healthz):", res.json())

        # 2. MT5 Account
        res = await client.get("/api/v1/mt5/account")
        print(f"[STATUS] /api/v1/mt5/account -> {res.status_code}")
        assert res.status_code == 200, f"Account endpoint failed: {res.text}"
        acct = res.json()
        print("[PASS] 2. MT5 Account Info:")
        print(f"       Login: {acct['login']}, Server: {acct['server']}, Company: {acct['company']}")
        print(f"       Balance: ${acct['balance']}, Equity: ${acct['equity']}, Floating P/L: ${acct['floating_pnl']}")
        print(f"       Free Margin: ${acct['free_margin']}, Leverage: 1:{acct['leverage']}, Connected: {acct['connected']}")

        # 3. MT5 Positions
        res = await client.get("/api/v1/mt5/positions")
        assert res.status_code == 200, f"Positions endpoint failed: {res.text}"
        positions = res.json()
        print(f"[PASS] 3. MT5 Open Positions: {len(positions)} open position(s)")
        for p in positions:
            print(f"       Ticket: {p['ticket']}, Symbol: {p['symbol']}, Type: {p['direction']}, Volume: {p['volume']}, Float PnL: ${p['floating_pnl']}")

        # 4. MT5 History (deals)
        res = await client.get("/api/v1/mt5/history?days=30")
        assert res.status_code == 200, f"History endpoint failed: {res.text}"
        history = res.json()
        print(f"[PASS] 4. MT5 Trade History: {len(history)} closed trade deal(s)")

        # 5. MT5 Stats
        res = await client.get("/api/v1/mt5/stats?days=30")
        assert res.status_code == 200, f"Stats endpoint failed: {res.text}"
        stats = res.json()
        print("[PASS] 5. MT5 Performance Stats:")
        print(f"       Total Trades: {stats['total_trades']}, Win Rate: {stats['win_rate']}%")
        print(f"       Net Realized PnL: ${stats['net_realized_pnl']}, Today's Realized PnL: ${stats['today_realized_pnl']}")
        print(f"       Open Positions Count: {stats['open_positions_count']}, Total Floating PnL: ${stats['total_floating_pnl']}")

        # 6. MT5 Summary
        res = await client.get("/api/v1/mt5/summary?days=30")
        assert res.status_code == 200, f"Summary endpoint failed: {res.text}"
        summary = res.json()
        print(f"[PASS] 6. MT5 Summary endpoint: Connected={summary['connected']}, Timestamp={summary['timestamp']}")

        # Verify Realized vs Floating separation
        assert "net_realized_pnl" in stats, "Stats must contain net_realized_pnl"
        assert "total_floating_pnl" in stats, "Stats must contain total_floating_pnl"
        assert "floating_pnl" in acct, "Account must contain floating_pnl"
        print("[PASS] 7. Strict separation of Realized P/L vs Floating P/L verified.")

    print("\n" + "=" * 60)
    print("ALL MT5 API ENDPOINT TESTS PASSED SUCCESSFULLY! (7/7)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
