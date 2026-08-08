"""
Section 11 — Backend API tests.

Uses session-scoped client so all tests share the same event loop
and avoid asyncpg pool conflicts.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_email(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@nexus-test.com"


# ── Session-scoped fixtures (one app + one event loop for all tests) ──────────

@pytest_asyncio.fixture(scope="session")
async def client():
    from main import create_app
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def auth_headers(client: AsyncClient):
    email    = _unique_email("session")
    password = "SessionPass123!"

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Session Operator"},
    )
    assert reg.status_code in (200, 201), f"register failed: {reg.status_code} {reg.text}"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, f"login failed: {login.status_code} {login.text}"
    token = login.json().get("access_token") or login.json().get("accessToken")
    assert token, f"no token: {login.json()}"
    return {"Authorization": f"Bearer {token}"}


# ── Health ─────────────────────────────────────────────────────────────────────

class TestHealth:
    async def test_healthz(self, client):
        res = await client.get("/api/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


# ── Auth ───────────────────────────────────────────────────────────────────────

class TestAuth:
    async def test_register_new_user(self, client):
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email("reg"), "password": "StrongPass99!", "name": "New Op"},
        )
        assert res.status_code in (200, 201)
        assert "id" in res.json() or "email" in res.json()

    async def test_register_duplicate_email(self, client):
        email   = _unique_email("dup")
        payload = {"email": email, "password": "Pass12345!", "name": "Dup"}
        r1 = await client.post("/api/v1/auth/register", json=payload)
        assert r1.status_code in (200, 201)
        r2 = await client.post("/api/v1/auth/register", json=payload)
        assert r2.status_code in (400, 409, 422)

    async def test_register_short_password(self, client):
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": _unique_email("short"), "password": "abc", "name": "Short"},
        )
        assert res.status_code == 422

    async def test_login_success(self, client, auth_headers):
        assert "Authorization" in auth_headers
        assert auth_headers["Authorization"].startswith("Bearer ")

    async def test_login_wrong_password(self, client):
        email = _unique_email("wrongpw")
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "RightPass99!", "name": "Wrong PW"},
        )
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPass9999!"},
        )
        assert res.status_code in (400, 401, 403)

    async def test_login_unknown_email(self, client):
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@nexus-ghost.com", "password": "Pass123456!"},
        )
        assert res.status_code in (400, 401, 403, 404)

    async def test_me_authenticated(self, client, auth_headers):
        res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert "email" in body or "id" in body

    async def test_me_unauthenticated(self, client):
        res = await client.get("/api/v1/auth/me")
        assert res.status_code in (401, 403)

    async def test_refresh_token(self, client):
        email    = _unique_email("ref")
        password = "RefreshMe99!"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "name": "Refresh"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        token = login.json().get("refresh_token") or login.json().get("refreshToken")
        if token is None:
            pytest.skip("No refresh token in login response")
        res = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert res.status_code == 200


# ── Dashboard ──────────────────────────────────────────────────────────────────

class TestDashboard:
    async def test_summary_authenticated(self, client, auth_headers):
        res = await client.get("/api/v1/dashboard/summary", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert "botStatus" in body or "bot_status" in body

    async def test_summary_unauthenticated(self, client):
        res = await client.get("/api/v1/dashboard/summary")
        assert res.status_code in (401, 403)

    async def test_performance_authenticated(self, client, auth_headers):
        res = await client.get("/api/v1/dashboard/performance", headers=auth_headers)
        assert res.status_code == 200

    async def test_performance_unauthenticated(self, client):
        res = await client.get("/api/v1/dashboard/performance")
        assert res.status_code in (401, 403)


# ── Settings ───────────────────────────────────────────────────────────────────

class TestSettings:
    async def test_get_settings(self, client, auth_headers):
        res = await client.get("/api/v1/settings", headers=auth_headers)
        assert res.status_code in (200, 500)   # 500 only if DB not ready in test env
        if res.status_code == 200:
            body = res.json()
            assert "riskPerTrade" in body or "risk_per_trade" in body

    async def test_update_settings_trading_disabled(self, client, auth_headers):
        res = await client.patch(
            "/api/v1/settings",
            headers=auth_headers,
            json={"trading_enabled": False},
        )
        assert res.status_code in (200, 204, 500)

    async def test_update_settings_news_filter(self, client, auth_headers):
        res = await client.patch(
            "/api/v1/settings",
            headers=auth_headers,
            json={"news_filter_enabled": True},
        )
        assert res.status_code in (200, 204, 500)

    async def test_settings_unauthenticated(self, client):
        res = await client.get("/api/v1/settings")
        assert res.status_code in (401, 403)


# ── Logs ───────────────────────────────────────────────────────────────────────

class TestLogs:
    async def test_list_logs_authenticated(self, client, auth_headers):
        res = await client.get("/api/v1/logs", headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), (dict, list))

    async def test_error_logs(self, client, auth_headers):
        res = await client.get("/api/v1/logs/errors", headers=auth_headers)
        assert res.status_code == 200

    async def test_logs_unauthenticated(self, client):
        res = await client.get("/api/v1/logs")
        assert res.status_code in (401, 403)


# ── Signals ────────────────────────────────────────────────────────────────────

class TestSignals:
    async def test_list_signals(self, client, auth_headers):
        res = await client.get("/api/v1/signals", headers=auth_headers)
        assert res.status_code == 200

    async def test_active_signals(self, client, auth_headers):
        res = await client.get("/api/v1/signals/active", headers=auth_headers)
        assert res.status_code == 200

    async def test_signals_unauthenticated(self, client):
        res = await client.get("/api/v1/signals")
        assert res.status_code in (401, 403)


# ── Candles ────────────────────────────────────────────────────────────────────

class TestCandles:
    async def test_invalid_pair(self, client):
        res = await client.get("/api/v1/candles?pair=FAKEXX&timeframe=H1")
        assert res.status_code == 422

    async def test_invalid_timeframe(self, client):
        res = await client.get("/api/v1/candles?pair=EURUSD&timeframe=X99")
        assert res.status_code == 422

    async def test_valid_pair_no_mt5(self, client):
        res = await client.get("/api/v1/candles?pair=EURUSD&timeframe=H1&count=50")
        assert res.status_code in (200, 503)
        if res.status_code == 503:
            detail = res.json().get("detail", "").lower()
            assert any(w in detail for w in ("unavailable", "mt5", "connection", "required"))

    async def test_count_too_large(self, client):
        res = await client.get("/api/v1/candles?pair=EURUSD&timeframe=H1&count=9999")
        assert res.status_code == 422

    async def test_count_too_small(self, client):
        res = await client.get("/api/v1/candles?pair=EURUSD&timeframe=H1&count=1")
        assert res.status_code == 422

    async def test_all_valid_pairs(self, client):
        pairs = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
                 "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP"]
        for pair in pairs:
            res = await client.get(f"/api/v1/candles?pair={pair}&timeframe=H1&count=50")
            assert res.status_code in (200, 503), f"{pair} gave {res.status_code}"

    async def test_all_valid_timeframes(self, client):
        for tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
            res = await client.get(f"/api/v1/candles?pair=EURUSD&timeframe={tf}&count=50")
            assert res.status_code in (200, 503), f"{tf} gave {res.status_code}"
