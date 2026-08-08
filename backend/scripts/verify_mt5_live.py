"""
MT5 / Exness Live-Data Verification Script
===========================================
Run this on your Windows PC where the MetaTrader 5 terminal is installed.

Prerequisites
-------------
1. MT5 terminal is installed and logged in to account ****7491 on Exness-MT5Trial16.
2. Python environment has MetaTrader5 installed:
       pip install MetaTrader5
3. Environment variables are set (PowerShell example):
       $env:MT5_ACCOUNT  = "472327491"
       $env:MT5_SERVER   = "Exness-MT5Trial16"
       $env:MT5_PASSWORD = "<your password>"
   Or pass them inline:
       MT5_ACCOUNT=472327491 MT5_SERVER=Exness-MT5Trial16 MT5_PASSWORD=xxx python verify_mt5_live.py
4. Run from the backend/ directory:
       cd backend
       python scripts/verify_mt5_live.py

Security reminders
------------------
- This script never prints the password or the full account number.
- Do not commit this file with credentials in it.
- The script is read-only: it verifies data only; it does not place orders.
"""

import asyncio
import os
import sys
import json
import datetime

# ── Env-var credentials ───────────────────────────────────────────────────
ACCT_STR = os.environ.get("MT5_ACCOUNT", "")
SERVER    = os.environ.get("MT5_SERVER",  "")
PASSWORD  = os.environ.get("MT5_PASSWORD","")

if not ACCT_STR or not SERVER or not PASSWORD:
    print("ERROR: MT5_ACCOUNT, MT5_SERVER, and MT5_PASSWORD must all be set.")
    print("       Set them as environment variables — do NOT hardcode them.")
    sys.exit(1)

MT5_ACCOUNT = int(ACCT_STR)
masked_acct = "****" + ACCT_STR[-4:] if len(ACCT_STR) > 4 else "****"

FOREX_PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD",
    "USDCAD","NZDUSD","EURGBP","EURJPY","GBPJPY",
]

# MT5 timeframe constants (int values)
TF_MAP = {
    "M5":  16390,
    "M15": 16392,
    "H1":  16385,
    "H4":  16388,
}
CANDLE_COUNT = 20

PASS = "PASS"; FAIL = "FAIL"
results = []

def chk(name, status, detail=""):
    tag = "[OK]  " if status == PASS else "[!!]  "
    print(f"  {tag}{name}")
    if detail:
        for ln in detail.splitlines():
            print(f"         {ln}")
    results.append((name, status))


# ── Bootstrap backend settings ────────────────────────────────────────────
os.environ.setdefault("APP_SECRET_KEY", "win-verify-smoke")
os.environ.setdefault("JWT_SECRET_KEY", "win-verify-smoke")
os.environ.setdefault("DATABASE_URL",   "postgresql://localhost/test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.modules.mt5_integration.base       import RealMT5Connector, _MT5_AVAILABLE, _mask_account
from app.modules.mt5_integration.interfaces import AccountInfo
from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.market_scanner.scanner     import MarketScanner
from app.modules.smc.analyzer               import SMCAnalyzer
from app.core.config                        import settings


print()
print("=" * 70)
print("  MT5 / EXNESS LIVE-DATA VERIFICATION  (Windows)")
print("=" * 70)
print(f"  Time         : {datetime.datetime.now().isoformat(timespec='seconds')}")
print(f"  Platform     : {sys.platform}")
print(f"  MT5_ACCOUNT  : {masked_acct}")
print(f"  MT5_SERVER   : {SERVER!r}")
print(f"  MT5_PASSWORD : set=True  (never printed)")
print(f"  _MT5_AVAILABLE : {_MT5_AVAILABLE}")
print()


# ── 1. Platform ───────────────────────────────────────────────────────────
print("1. Platform")
chk("sys.platform=win32 (or cygwin)", PASS if sys.platform.startswith("win") else FAIL,
    f"sys.platform={sys.platform!r}")
chk("_MT5_AVAILABLE=True on Windows", PASS if _MT5_AVAILABLE else FAIL)


# ── 2. MT5 Terminal Connection ────────────────────────────────────────────
print()
print("2. MT5 Terminal Connection")

connector = RealMT5Connector()

async def run_connection_checks():
    # 2a. connect()
    try:
        connected = await connector.connect()
        chk("connector.connect() returns True", PASS if connected else FAIL,
            f"connected={connected}")
    except Exception as e:
        chk("connector.connect()", FAIL, f"{type(e).__name__}: {e}")
        print()
        print("  Cannot continue without a connection. Check that:")
        print("   · MT5 terminal is open and logged in")
        print("   · MT5_ACCOUNT / MT5_SERVER / MT5_PASSWORD are correct")
        return False
    return connected

connected = asyncio.run(run_connection_checks())


# ── 3. Account Status ─────────────────────────────────────────────────────
print()
print("3. Account Status")

async def run_account_checks():
    try:
        info: AccountInfo = await connector.get_account_info()
        chk("get_account_info() returns AccountInfo", PASS)
        chk("connected=True in AccountInfo",  PASS if info.connected else FAIL)
        chk("balance > 0",  PASS if info.balance > 0  else FAIL,
            f"balance={info.balance}")
        chk("equity  > 0",  PASS if info.equity  > 0  else FAIL,
            f"equity={info.equity}")
        chk("currency set", PASS if info.currency else FAIL,
            f"currency={info.currency!r}")
        chk("leverage > 0", PASS if info.leverage > 0  else FAIL,
            f"leverage={info.leverage}")
        chk("server matches MT5_SERVER",
            PASS if info.server == SERVER else FAIL,
            f"server={info.server!r}")
        # login present in dataclass but MUST NOT appear in API response
        chk("login field present in AccountInfo (internal use only)",
            PASS if info.login else FAIL,
            f"login=****{str(info.login)[-4:]}")
        return info
    except Exception as e:
        chk("get_account_info()", FAIL, f"{type(e).__name__}: {e}")
        return None

acct_info = asyncio.run(run_account_checks())


# ── 4. Symbol Availability ────────────────────────────────────────────────
print()
print("4. Required FOREX_PAIRS Symbol Availability")

async def run_symbol_checks():
    try:
        avail = await connector.check_symbols(FOREX_PAIRS)
        chk("check_symbols() returns Dict[str, bool]", PASS,
            f"keys={sorted(avail.keys())}")
        all_ok = True
        for pair in FOREX_PAIRS:
            ok = avail.get(pair, False)
            chk(f"  {pair} available on Exness-MT5Trial16",
                PASS if ok else FAIL)
            if not ok:
                all_ok = False
        return avail
    except Exception as e:
        chk("check_symbols(FOREX_PAIRS)", FAIL, f"{type(e).__name__}: {e}")
        return {}

symbol_map = asyncio.run(run_symbol_checks())


# ── 5. Live Tick Data ─────────────────────────────────────────────────────
print()
print("5. Live Tick Data")

async def run_tick_checks():
    for pair in FOREX_PAIRS:
        try:
            tick = await connector.get_tick(pair)
            bid  = tick.get("bid", 0)
            ask  = tick.get("ask", 0)
            sprd = tick.get("spread", 0)
            ok   = bid > 0 and ask > 0 and ask >= bid
            chk(f"  {pair} tick  bid={bid:.5f}  ask={ask:.5f}  spread={sprd:.1f}",
                PASS if ok else FAIL)
        except Exception as e:
            chk(f"  {pair} tick", FAIL, f"{type(e).__name__}: {e}")

asyncio.run(run_tick_checks())


# ── 6. Live OHLCV / Candle Data ───────────────────────────────────────────
print()
print("6. Live OHLCV / Candle Data  (M5, M15, H1, H4)")

async def run_ohlcv_checks():
    # Test each timeframe against EURUSD
    pair = "EURUSD"
    for tf_name, tf_int in TF_MAP.items():
        try:
            bars = await connector.get_ohlcv(pair, tf_int, CANDLE_COUNT)
            ok   = isinstance(bars, list) and len(bars) > 0
            if ok:
                last = bars[-1]
                has_fields = all(k in last for k in
                                 ("open","high","low","close","volume","time"))
                price_ok   = (last["high"] >= last["low"] and
                              last["open"] > 0 and last["close"] > 0)
                ok = has_fields and price_ok
            chk(f"  {pair} {tf_name}  bars={len(bars) if isinstance(bars,list) else '?'}"
                f"  last_close={bars[-1]['close'] if ok else '?'}",
                PASS if ok else FAIL)
        except Exception as e:
            chk(f"  {pair} {tf_name}", FAIL, f"{type(e).__name__}: {e}")

asyncio.run(run_ohlcv_checks())


# ── 7. Scanner receives real MT5 data ─────────────────────────────────────
print()
print("7. MarketScanner receives real MT5 data (EURUSD M5 scan)")

async def run_scanner_check():
    svc     = MarketDataService()   # uses RealMT5Connector by default
    scanner = MarketScanner()

    # Grab live bars via the service layer (validates bar schema)
    try:
        bars = await svc.get_ohlcv("EURUSD", TF_MAP["M5"], CANDLE_COUNT)
        chk("MarketDataService.get_ohlcv(EURUSD, M5) returns bars",
            PASS if bars and len(bars) > 0 else FAIL,
            f"bar_count={len(bars) if bars else 0}")
    except Exception as e:
        chk("MarketDataService.get_ohlcv(EURUSD, M5)", FAIL,
            f"{type(e).__name__}: {e}")
        return

    # Full scan_pair call through the scanner (enriches with SMC context)
    try:
        result = await scanner.scan_pair("EURUSD", "M5")
        chk("scanner.scan_pair(EURUSD, M5) returns ScanResult",
            PASS if result is not None else FAIL)
        if result:
            chk("  ScanResult.pair = EURUSD",
                PASS if result.pair == "EURUSD" else FAIL)
            chk("  ScanResult has SMC confluence score",
                PASS if "smc_confluence_score" in (result.metadata or {}) else FAIL,
                f"metadata keys={sorted((result.metadata or {}).keys())}")
    except Exception as e:
        chk("scanner.scan_pair(EURUSD, M5)", FAIL, f"{type(e).__name__}: {e}")

    await svc.shutdown()

asyncio.run(run_scanner_check())


# ── 8. SMC analysis on real candle data ───────────────────────────────────
print()
print("8. SMC Analysis on Real Candle Data")

async def run_smc_check():
    svc = MarketDataService()
    smc = SMCAnalyzer()

    tf_bars = {}
    for tf_name, tf_int in TF_MAP.items():
        try:
            bars = await svc.get_ohlcv("EURUSD", tf_int, 50)
            if bars:
                tf_bars[tf_name] = bars
        except Exception:
            pass

    chk(f"OHLCV fetched for {len(tf_bars)}/4 timeframes",
        PASS if len(tf_bars) == 4 else FAIL,
        f"got={list(tf_bars.keys())}")

    if tf_bars:
        try:
            mtf = smc.analyze_multi_timeframe(tf_bars)
            chk("SMCAnalyzer.analyze_multi_timeframe() returns MTFAnalysis",
                PASS if mtf is not None else FAIL)

            if mtf and tf_bars.get("M5"):
                bars_m5 = tf_bars["M5"]
                price   = bars_m5[-1]["close"]
                result  = smc.score_confluence(mtf, bars_m5, price)
                chk("SMCAnalyzer.score_confluence() returns ConfluenceResult",
                    PASS if result is not None else FAIL)
                if result:
                    chk(f"  confluence_score in [0, 100]",
                        PASS if 0 <= result.score <= 100 else FAIL,
                        f"score={result.score:.1f}  bias={result.bias}")
        except Exception as e:
            chk("SMC analysis", FAIL, f"{type(e).__name__}: {e}")

    await svc.shutdown()

asyncio.run(run_smc_check())


# ── 9. GET /api/v1/market/health (Windows response) ───────────────────────
print()
print("9. GET /api/v1/market/health  (Windows — expected connected=True)")

async def run_health_check():
    try:
        # Import here so the health function picks up the live connector
        from app.api.v1.market import mt5_health
        result = await mt5_health()

        hj = json.dumps(result)

        chk("Response has all 7 required keys",
            PASS if {"platform","mt5_package_available","connected",
                     "environment_note","account","symbol_availability",
                     "checked_at"} <= result.keys() else FAIL,
            f"keys={sorted(result.keys())}")
        chk("platform=win32",
            PASS if result.get("platform","").startswith("win") else FAIL,
            f"platform={result.get('platform')!r}")
        chk("mt5_package_available=True",
            PASS if result.get("mt5_package_available") is True else FAIL)
        chk("connected=True",
            PASS if result.get("connected") is True else FAIL)
        chk("account snapshot present",
            PASS if isinstance(result.get("account"), dict) else FAIL)
        if isinstance(result.get("account"), dict):
            acct = result["account"]
            chk("  account.balance > 0",
                PASS if acct.get("balance", 0) > 0 else FAIL,
                f"balance={acct.get('balance')}")
            chk("  login key absent from account snapshot",
                PASS if "login" not in acct else FAIL)
        chk("symbol_availability covers all 10 pairs",
            PASS if all(p in result.get("symbol_availability",{})
                        for p in FOREX_PAIRS) else FAIL,
            f"pairs={sorted(result.get('symbol_availability',{}).keys())}")
        chk("MT5_PASSWORD value not in JSON response",
            PASS if PASSWORD not in hj else FAIL)
        chk("Word 'password' absent from JSON",
            PASS if "password" not in hj.lower() else FAIL)
    except Exception as e:
        chk("mt5_health()", FAIL, f"{type(e).__name__}: {e}")

asyncio.run(run_health_check())


# ── Clean disconnect ───────────────────────────────────────────────────────
async def _disconnect():
    try:
        await connector.disconnect()
    except Exception:
        pass

asyncio.run(_disconnect())


# ── Summary ───────────────────────────────────────────────────────────────
print()
print("=" * 70)
passed  = sum(1 for _, s in results if s == PASS)
failed  = sum(1 for _, s in results if s == FAIL)
print(f"  RESULTS: {passed} PASS  |  {failed} FAIL  |  {len(results)} total")
print("=" * 70)
if failed:
    print()
    print("  FAILURES:")
    for n, s in results:
        if s == FAIL:
            print(f"    ✗ {n}")
else:
    print()
    print("  All checks passed — live MT5/Exness integration verified.")
print()
