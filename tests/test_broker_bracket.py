"""Bracket path: live-equity sizing -> whole-share bracket; trail/time-stop/OCO reconcile."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select

from swing_signals.broker.base import BrokerAccount, BrokerOrder, BrokerPosition
from swing_signals.broker.entries import submit_entries
from swing_signals.broker.manage import reconcile_and_manage
from swing_signals.config_loader import Secrets, load_settings
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Trade
from swing_signals.persistence.repository import create_run, save_signals, upsert_trade
from swing_signals.scoring.engine import Signal as EngineSignal

DAY = date(2024, 2, 20)
NOW = datetime(2024, 2, 20, 17, 0, 0)


class FakeBracketBroker:
    name = "fake"

    def __init__(self, *, equity=200000.0, positions=None, orders=None):
        self.enabled = True
        self._account = BrokerAccount(equity, equity, equity)
        self._positions = {p.symbol: p for p in (positions or [])}
        self._orders = {o.id: o for o in (orders or [])}
        self.submitted: list[BrokerOrder] = []
        self.replaced: list[tuple] = []
        self.canceled: list[str] = []
        self.last_bracket: dict | None = None
        self._n = 2000

    def get_account(self):
        return self._account

    def list_positions(self):
        return list(self._positions.values())

    def get_position(self, s):
        return self._positions.get(s)

    def list_open_orders(self):
        return [o for o in self._orders.values() if o.is_open]

    def get_order_by_id(self, oid):
        return self._orders.get(oid)

    def _new(self, symbol, side, type_, qty, coid, limit_price=None, stop_price=None):
        self._n += 1
        o = BrokerOrder(
            id=f"ord-{self._n}", client_order_id=coid, symbol=symbol, side=side, type=type_,
            status="accepted", qty=qty, notional=None, limit_price=limit_price,
            stop_price=stop_price, filled_qty=0.0, filled_avg_price=None,
        )
        self._orders[o.id] = o
        self.submitted.append(o)
        return o

    def submit_bracket_buy(self, symbol, *, qty, limit_price, take_profit, stop_loss,
                           client_order_id, market=False):
        self.last_bracket = {"qty": qty, "tp": take_profit, "sl": stop_loss, "market": market,
                             "limit": limit_price}
        return self._new(symbol, "buy", "market" if market else "limit", qty, client_order_id,
                         limit_price=limit_price)

    def submit_market_buy(self, symbol, *, qty, client_order_id):
        return self._new(symbol, "buy", "market", qty, client_order_id)

    def submit_limit_buy(self, symbol, *, qty, limit_price, client_order_id):
        return self._new(symbol, "buy", "limit", qty, client_order_id, limit_price=limit_price)

    def submit_sell(self, symbol, *, qty, order_type="market", limit_price=None,
                    stop_price=None, client_order_id):
        return self._new(symbol, "sell", order_type, qty, client_order_id,
                         limit_price=limit_price, stop_price=stop_price)

    def replace_stop(self, order_id, *, stop_price):
        self.replaced.append((order_id, stop_price))
        return None

    def cancel_order(self, oid):
        self.canceled.append(oid)
        if oid in self._orders:
            self._orders[oid] = replace(self._orders[oid], status="canceled")

    def get_latest_price(self, s):
        return None


class FakeLoader:
    def __init__(self, df):
        self._df = df

    def get_ohlcv(self, symbol, start, end, *, offline=False):
        return self._df


def _ord(oid, symbol, side, type_, status, *, qty=333.0, fill=None, stop_price=None,
         limit_price=None, legs=()):
    return BrokerOrder(
        id=oid, client_order_id="", symbol=symbol, side=side, type=type_, status=status,
        qty=qty, notional=None, limit_price=limit_price, stop_price=stop_price,
        filled_qty=qty if status == "filled" else 0.0, filled_avg_price=fill, legs=tuple(legs),
    )


def _ohlcv(*, last_low, last_high, hi=102.0, lo=98.0, close=100.0, n=30):
    idx = pd.bdate_range(end="2024-02-20", periods=n)
    high = [hi] * n
    low = [lo] * n
    high[-1], low[-1] = last_high, last_low
    return pd.DataFrame(
        {"open": [close] * n, "high": high, "low": low, "close": [close] * n,
         "volume": [1_000_000] * n},
        index=idx,
    )


def _settings(tmp_path, **broker):
    s = load_settings()  # equity 200000, entry_class auto, size_from_live_equity True (defaults)
    s.run.db_url = f"sqlite:///{tmp_path}/bracket.db"
    s.broker.enabled = True
    s.exits.mode = "legacy"  # brackets are the legacy path (staged uses simple entries)
    for k, v in broker.items():
        setattr(s.broker, k, v)
    return s


def _secrets(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DATABASE_URL", raising=False)
    return Secrets(_env_file=None)


def _seed_signal(db_url):
    sig = EngineSignal(
        ticker="AAPL", signal_date=DAY, direction="LONG", conviction_score=80.0,
        conviction_tier="High", reference_price=101.0, atr=3.0, entry_zone_low=99.0,
        entry_zone_high=100.0, stop_price=94.0, stop_distance_atr=2.0, target_price=112.0,
        reward_risk=2.0, suggested_risk_pct=0.01, suggested_shares=1.5, chandelier_stop=95.0,
        regime_state="GREEN", rank=1, factor_contributions={}, agreement_score=1.0, flags=[],
    )
    with session_scope(make_engine(db_url)) as s:
        run = create_run(s, run_ts=NOW, trading_day=DAY, status="success")
        save_signals(s, run, [sig], created_at=NOW)


def _seed_trade(db_url, **fields):
    with session_scope(make_engine(db_url)) as s:
        upsert_trade(s, signal_date=DAY, symbol="AAPL", now=NOW, order_class="bracket", **fields)


def _read(db_url):
    with session_scope(make_engine(db_url)) as s:
        t = s.scalar(select(Trade).where(Trade.symbol == "AAPL"))
        return {c.name: getattr(t, c.name) for c in Trade.__table__.columns}


# --- entry: live-equity sizing -> whole-share bracket -------------------------

def test_live_equity_sizing_submits_whole_share_bracket(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed_signal(s.run.db_url)
    broker = FakeBracketBroker(equity=200_000.0)
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=broker)
    assert report.submitted == ["AAPL"]
    # 200000 * 1% risk / $6 risk-per-share = 333.3 -> floor 333 whole shares, as a bracket
    assert broker.last_bracket == {"qty": 333.0, "tp": 112.0, "sl": 94.0, "market": False,
                                   "limit": 100.0}
    t = _read(s.run.db_url)
    assert t["order_class"] == "bracket"
    assert t["qty"] == 333.0


# --- manage: bracket lifecycle ------------------------------------------------

def test_bracket_fill_opens_and_captures_legs(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    legs = [_ord("TP1", "AAPL", "sell", "limit", "held", limit_price=112.0),
            _ord("SL1", "AAPL", "sell", "stop", "held", stop_price=94.0)]
    broker = FakeBracketBroker(orders=[
        _ord("B1", "AAPL", "buy", "limit", "filled", fill=99.5, legs=legs)
    ])
    _seed_trade(s.run.db_url, status="pending_entry", entry_order_id="B1", qty=333.0,
                stop_price=94.0, target_price=112.0)
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(None))
    t = _read(s.run.db_url)
    assert t["status"] == "open"
    assert t["actual_entry"] == 99.5
    assert t["take_profit_order_id"] == "TP1"
    assert t["stop_loss_order_id"] == "SL1"


def test_bracket_stop_leg_holds_when_trail_disabled(tmp_path, monkeypatch):
    """trail_legacy_stop=false (validated combo): the server-side stop leg never moves."""
    s = _settings(tmp_path)
    s.exits.trail_legacy_stop = False
    broker = FakeBracketBroker(positions=[BrokerPosition("AAPL", 333, 100.0, 38628.0, 0.0, 116.0)])
    _seed_trade(s.run.db_url, status="open", qty=333.0, stop_price=94.0, effective_stop=94.0,
                target_price=200.0, entry_fill_date=DAY, actual_entry=100.0, risk_per_share=6.0,
                stop_loss_order_id="SL1")
    df = _ohlcv(last_low=115.0, last_high=117.0, hi=118.0, lo=114.0, close=116.0)
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker, loader=FakeLoader(df))
    t = _read(s.run.db_url)
    assert t["status"] == "open"
    assert t["effective_stop"] == 94.0   # HOLDS — no trail
    assert not broker.replaced           # the server-side stop leg was never moved


def test_bracket_trails_stop_leg_when_flag_enabled(tmp_path, monkeypatch):
    """trail_legacy_stop=true (owner variant): the stop leg trails up to the chandelier."""
    s = _settings(tmp_path)
    s.exits.trail_legacy_stop = True
    broker = FakeBracketBroker(positions=[BrokerPosition("AAPL", 333, 100.0, 38628.0, 0.0, 116.0)])
    _seed_trade(s.run.db_url, status="open", qty=333.0, stop_price=94.0, effective_stop=94.0,
                target_price=200.0, entry_fill_date=DAY, actual_entry=100.0, risk_per_share=6.0,
                stop_loss_order_id="SL1")
    df = _ohlcv(last_low=115.0, last_high=117.0, hi=118.0, lo=114.0, close=116.0)
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker, loader=FakeLoader(df))
    t = _read(s.run.db_url)
    assert t["status"] == "open"
    assert t["effective_stop"] > 94.0
    assert broker.replaced and broker.replaced[0][0] == "SL1"  # trailed the server-side stop


def test_bracket_time_stop_cancels_legs_and_sells(tmp_path, monkeypatch):
    s = _settings(tmp_path, max_hold_bars=20)
    broker = FakeBracketBroker(positions=[BrokerPosition("AAPL", 333, 100.0, 33300.0, 0.0, 100.0)])
    _seed_trade(s.run.db_url, status="open", qty=333.0, stop_price=94.0, effective_stop=94.0,
                target_price=112.0, entry_fill_date=date(2024, 1, 2), actual_entry=100.0,
                risk_per_share=6.0, take_profit_order_id="TP1", stop_loss_order_id="SL1")
    df = _ohlcv(last_low=96.0, last_high=102.0)  # no stop/target -> time-stop
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    assert ("AAPL", "time_exit") in rep.exits_submitted
    assert set(broker.canceled) == {"TP1", "SL1"}  # OCO legs canceled before the market sell
    assert any(o.side == "sell" and o.type == "market" for o in broker.submitted)


def test_bracket_oco_stop_fill_reconciled(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    # position is GONE (server-side stop filled); SL leg shows filled at 94
    broker = FakeBracketBroker(orders=[_ord("SL1", "AAPL", "sell", "stop", "filled", fill=94.0)])
    _seed_trade(s.run.db_url, status="open", qty=333.0, stop_price=94.0, actual_entry=100.0,
                risk_per_share=6.0, entry_fill_date=date(2024, 2, 13),
                stop_loss_order_id="SL1", take_profit_order_id="TP1")
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(None))
    assert rep.closed == ["AAPL"]
    t = _read(s.run.db_url)
    assert t["status"] == "closed"
    assert t["exit_reason"] == "stopped"
    assert t["realized_r"] == -1.0          # (94 - 100) / 6
    assert t["pnl"] == round((94.0 - 100.0) * 333.0, 4)
