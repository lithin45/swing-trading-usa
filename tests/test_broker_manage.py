"""Manage flow: fill sync, chandelier ratchet, exits, fallback, close (fake broker)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select

from swing_signals.broker.base import BrokerAccount, BrokerOrder, BrokerPosition
from swing_signals.broker.manage import reconcile_and_manage
from swing_signals.config_loader import Secrets, load_settings
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import AccountSnapshot, Trade
from swing_signals.persistence.repository import upsert_trade

DAY = date(2024, 2, 20)
NOW = datetime(2024, 2, 20, 17, 0, 0)


# --- fakes --------------------------------------------------------------------

class FakeBroker:
    name = "fake"

    def __init__(self, *, equity=500.0, positions=None, orders=None):
        self.enabled = True
        self._account = BrokerAccount(equity, equity, equity)
        self._positions = {p.symbol: p for p in (positions or [])}
        self._orders = {o.id: o for o in (orders or [])}
        self.submitted: list[BrokerOrder] = []
        self._n = 1000

    def get_account(self):
        return self._account

    def list_positions(self):
        return list(self._positions.values())

    def get_position(self, symbol):
        return self._positions.get(symbol)

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

    def submit_limit_buy(self, symbol, *, qty, limit_price, client_order_id):
        return self._new(symbol, "buy", "limit", qty, client_order_id, limit_price=limit_price)

    def submit_market_buy(self, symbol, *, qty, client_order_id):
        return self._new(symbol, "buy", "market", qty, client_order_id)

    def submit_sell(self, symbol, *, qty, order_type="market", limit_price=None,
                    stop_price=None, client_order_id):
        return self._new(symbol, "sell", order_type, qty, client_order_id,
                         limit_price=limit_price, stop_price=stop_price)

    def cancel_order(self, oid):
        o = self._orders.get(oid)
        if o is not None and not o.is_filled:  # Alpaca: canceling a filled order is a no-op
            self._orders[oid] = replace(o, status="canceled")

    def get_latest_price(self, symbol):
        return None


class FakeLoader:
    def __init__(self, df):
        self._df = df

    def get_ohlcv(self, symbol, start, end, *, offline=False):
        return self._df


def _order(oid, symbol, side, type_, status, *, qty=1.5, fill=None, stop_price=None):
    return BrokerOrder(
        id=oid, client_order_id="", symbol=symbol, side=side, type=type_, status=status,
        qty=qty, notional=None, limit_price=None, stop_price=stop_price,
        filled_qty=qty if status == "filled" else 0.0, filled_avg_price=fill,
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


# --- harness ------------------------------------------------------------------

def _settings(tmp_path, **broker):
    s = load_settings()
    s.run.db_url = f"sqlite:///{tmp_path}/manage.db"
    s.broker.enabled = True
    s.exits.mode = "legacy"  # default to legacy here; the staged tests opt in via _staged()
    for k, v in broker.items():
        setattr(s.broker, k, v)
    return s


def _secrets(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DATABASE_URL", raising=False)
    return Secrets(_env_file=None)


def _seed(db_url, **fields):
    with session_scope(make_engine(db_url)) as s:
        upsert_trade(s, signal_date=DAY, symbol=fields.pop("symbol", "AAPL"), now=NOW, **fields)


def _read(db_url, symbol="AAPL"):
    with session_scope(make_engine(db_url)) as s:
        t = s.scalar(select(Trade).where(Trade.symbol == symbol))
        return {c.name: getattr(t, c.name) for c in Trade.__table__.columns}


def _snapshots(db_url):
    with session_scope(make_engine(db_url)) as s:
        return [x.equity for x in s.scalars(select(AccountSnapshot))]


# --- tests --------------------------------------------------------------------

def test_pending_fill_becomes_open(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="pending_entry", entry_order_id="E1", qty=1.5,
          limit_price=100.0, stop_price=94.0, target_price=112.0)
    broker = FakeBroker(orders=[_order("E1", "AAPL", "buy", "limit", "filled", fill=99.5)])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(None))
    t = _read(s.run.db_url)
    assert t["status"] == "open"
    assert t["actual_entry"] == 99.5
    # Fill deviated >0.1% from the planned 100.0 entry -> stop/target re-anchor to the
    # actual fill at the SAME dollar distances (6 below, 12 above), preserving sized risk.
    assert t["stop_price"] == 93.5
    assert t["target_price"] == 111.5
    assert t["risk_per_share"] == 6.0
    assert t["entry_fill_date"] == DAY


def test_open_stop_exit(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="open", qty=1.5, stop_price=94.0, effective_stop=94.0,
          target_price=112.0, entry_fill_date=DAY, actual_entry=100.0, risk_per_share=6.0)
    pos = BrokerPosition("AAPL", 1.5, 100.0, 141.0, -10.5, 93.0)
    broker = FakeBroker(positions=[pos])
    df = _ohlcv(last_low=93.0, last_high=101.0)  # low 93 <= eff 94 -> stop
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    assert ("AAPL", "stopped") in rep.exits_submitted
    t = _read(s.run.db_url)
    assert t["status"] == "closing"
    assert t["exit_reason"] == "stopped"
    assert any(o.side == "sell" for o in broker.submitted)


def test_chandelier_ratchets_and_protects(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="open", qty=1.5, stop_price=94.0, effective_stop=94.0,
          target_price=200.0, entry_fill_date=DAY, actual_entry=100.0, risk_per_share=6.0)
    pos = BrokerPosition("AAPL", 1.5, 100.0, 174.0, 24.0, 116.0)
    broker = FakeBroker(positions=[pos])
    # price has run up to ~116; chandelier should lift the stop well above 94
    df = _ohlcv(last_low=115.0, last_high=117.0, hi=118.0, lo=114.0, close=116.0)
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    t = _read(s.run.db_url)
    assert t["status"] == "open"  # not exited
    assert t["effective_stop"] > 94.0  # ratcheted up
    assert rep.protective_placed == ["AAPL"]
    assert any(o.type == "stop" and o.side == "sell" for o in broker.submitted)


def test_time_exit(tmp_path, monkeypatch):
    s = _settings(tmp_path, max_hold_bars=20)
    _seed(s.run.db_url, status="open", qty=1.5, stop_price=94.0, effective_stop=94.0,
          target_price=112.0, entry_fill_date=date(2024, 1, 2), actual_entry=100.0,
          risk_per_share=6.0)
    broker = FakeBroker(positions=[BrokerPosition("AAPL", 1.5, 100.0, 150.0, 0.0, 100.0)])
    df = _ohlcv(last_low=96.0, last_high=102.0)  # no stop, no target -> time-stop fires
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    assert ("AAPL", "time_exit") in rep.exits_submitted


def test_closing_finalizes_pnl(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="closing", exit_order_id="X1", exit_reason="target_hit",
          qty=1.5, filled_qty=1.5, actual_entry=100.0, risk_per_share=6.0,
          entry_fill_date=date(2024, 2, 13))
    broker = FakeBroker(orders=[_order("X1", "AAPL", "sell", "market", "filled", fill=112.0)])
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(None))
    assert rep.closed == ["AAPL"]
    t = _read(s.run.db_url)
    assert t["status"] == "closed"
    assert t["exit_price"] == 112.0
    assert t["realized_r"] == 2.0          # (112 - 100) / 6
    assert t["pnl"] == 18.0                # (112 - 100) * 1.5
    assert t["pct_return"] == 0.12


def test_pending_aged_market_fallback(tmp_path, monkeypatch):
    s = _settings(tmp_path, max_pending_days=3, market_fallback=True)
    _seed(s.run.db_url, status="pending_entry", entry_order_id="E2", qty=1.5,
          limit_price=100.0, stop_price=94.0, pending_days=2)  # +1 -> 3 == max
    broker = FakeBroker(orders=[_order("E2", "AAPL", "buy", "limit", "expired")])
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(None))
    assert rep.fallback_market == ["AAPL"]
    t = _read(s.run.db_url)
    assert t["entry_order_type"] == "market"
    assert any(o.type == "market" and o.side == "buy" for o in broker.submitted)


def test_pending_reprices_when_young(tmp_path, monkeypatch):
    s = _settings(tmp_path, max_pending_days=3, entry_reprice_each_day=True)
    _seed(s.run.db_url, status="pending_entry", entry_order_id="E3", qty=1.5,
          limit_price=100.0, stop_price=94.0, pending_days=0)
    broker = FakeBroker(orders=[_order("E3", "AAPL", "buy", "limit", "expired")])
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(None))
    assert rep.repriced == ["AAPL"]
    assert any(o.type == "limit" and o.side == "buy" for o in broker.submitted)


def test_snapshot_written(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="pending_entry", entry_order_id="E9", qty=1.5, limit_price=100.0)
    broker = FakeBroker(equity=512.0, orders=[_order("E9", "AAPL", "buy", "limit", "accepted")])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(None))
    assert _snapshots(s.run.db_url) == [512.0]


def test_dry_run_changes_nothing(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="pending_entry", entry_order_id="E1", qty=1.5,
          limit_price=100.0, stop_price=94.0)
    broker = FakeBroker(orders=[_order("E1", "AAPL", "buy", "limit", "filled", fill=99.5)])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(None), dry_run=True)
    assert _read(s.run.db_url)["status"] == "pending_entry"  # unchanged
    assert _snapshots(s.run.db_url) == []                    # no snapshot


# --- staged-mode exits (exits.mode=staged) ------------------------------------

def _staged(tmp_path, **broker):
    s = _settings(tmp_path, **broker)
    s.exits.mode = "staged"
    return s


def test_staged_partial_scale_out_and_breakeven(tmp_path, monkeypatch):
    s = _staged(tmp_path)
    _seed(s.run.db_url, status="open", order_class="simple", qty=2.0, stop_price=94.0,
          effective_stop=94.0, target_price=112.0, entry_fill_date=DAY, actual_entry=100.0,
          risk_per_share=6.0)
    broker = FakeBroker(positions=[BrokerPosition("AAPL", 2.0, 100.0, 226.0, 26.0, 113.0)])
    df = _ohlcv(last_low=108.0, last_high=113.0, close=113.0)  # high 113 >= target 112 -> partial
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    t = _read(s.run.db_url)
    assert t["partial_done"] is True
    assert t["partial_qty"] == 1.0            # 50% of 2 shares
    assert t["partial_fill_price"] == 112.0
    assert t["effective_stop"] == 100.0       # ratcheted to breakeven (entry)
    assert t["status"] == "open"              # remainder still open
    assert ("AAPL", "target_partial") in rep.exits_submitted
    assert any(o.side == "sell" and o.type == "market" for o in broker.submitted)
    assert any(o.type == "stop" and o.qty == 1.0 for o in broker.submitted)  # remainder protected


def test_staged_stagnant_trade_is_time_cut(tmp_path, monkeypatch):
    s = _staged(tmp_path)
    s.exits.stagnation_bars = 15
    _seed(s.run.db_url, status="open", order_class="simple", qty=2.0, stop_price=94.0,
          effective_stop=94.0, target_price=130.0, entry_fill_date=date(2024, 1, 2),
          actual_entry=100.0, risk_per_share=6.0)
    broker = FakeBroker(positions=[BrokerPosition("AAPL", 2.0, 100.0, 202.0, 2.0, 101.0)])
    df = _ohlcv(last_low=99.0, last_high=102.0, close=101.0)  # ~+0.17R after ~35 bars -> stagnant
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    assert ("AAPL", "time_stop_stagnant") in rep.exits_submitted
    assert _read(s.run.db_url)["status"] == "closing"


def test_staged_working_trade_is_not_time_cut(tmp_path, monkeypatch):
    s = _staged(tmp_path)
    s.exits.stagnation_bars = 15
    _seed(s.run.db_url, status="open", order_class="simple", qty=2.0, stop_price=94.0,
          effective_stop=94.0, target_price=130.0, entry_fill_date=date(2024, 1, 2),
          actual_entry=100.0, risk_per_share=6.0)
    broker = FakeBroker(positions=[BrokerPosition("AAPL", 2.0, 100.0, 216.0, 16.0, 108.0)])
    df = _ohlcv(last_low=107.0, last_high=109.0, close=108.0)  # +1.33R -> working, rides
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    assert rep.exits_submitted == []
    assert _read(s.run.db_url)["status"] == "open"


def test_staged_bracket_transitions_to_self_managed(tmp_path, monkeypatch):
    s = _staged(tmp_path)
    _seed(s.run.db_url, status="open", order_class="bracket", qty=2.0, stop_price=94.0,
          effective_stop=94.0, target_price=130.0, entry_fill_date=DAY, actual_entry=100.0,
          risk_per_share=6.0, take_profit_order_id="TP1", stop_loss_order_id="SL1")
    broker = FakeBroker(
        positions=[BrokerPosition("AAPL", 2.0, 100.0, 210.0, 10.0, 105.0)],
        orders=[_order("TP1", "AAPL", "sell", "limit", "accepted"),
                _order("SL1", "AAPL", "sell", "stop", "accepted")],
    )
    df = _ohlcv(last_low=104.0, last_high=106.0, close=105.0)  # no exit; just transition
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker, loader=FakeLoader(df))
    t = _read(s.run.db_url)
    assert t["order_class"] == "simple"
    assert t["take_profit_order_id"] is None and t["stop_loss_order_id"] is None
    assert broker._orders["TP1"].status == "canceled"
    assert broker._orders["SL1"].status == "canceled"


def test_staged_blended_realized_r_on_close(tmp_path, monkeypatch):
    # Closing trade that had a +2R partial; remainder stops at breakeven -> blended +1R.
    s = _staged(tmp_path)
    _seed(s.run.db_url, status="closing", exit_order_id="X1", exit_reason="stopped",
          order_class="simple", qty=2.0, filled_qty=2.0, actual_entry=100.0, risk_per_share=6.0,
          entry_fill_date=date(2024, 2, 13), partial_done=True, partial_qty=1.0,
          partial_fill_price=112.0)
    broker = FakeBroker(orders=[_order("X1", "AAPL", "sell", "market", "filled", fill=100.0)])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(None))
    t = _read(s.run.db_url)
    assert t["status"] == "closed"
    assert t["realized_r"] == 1.0    # avg exit (112+100)/2 = 106 -> (106-100)/6
    assert t["pnl"] == 12.0          # 1*(112-100) + 1*(100-100)


# --- fill-state edge cases: partial fills, races, orphans, stale data ----------

def _order2(oid, symbol, side, type_, status, *, qty=1.5, filled_qty=0.0, fill=None,
            coid="", stop_price=None):
    """Like _order but with independent filled_qty (partial-fill states)."""
    return BrokerOrder(
        id=oid, client_order_id=coid, symbol=symbol, side=side, type=type_, status=status,
        qty=qty, notional=None, limit_price=None, stop_price=stop_price,
        filled_qty=filled_qty, filled_avg_price=fill,
    )


def test_partial_fill_then_expired_is_adopted_not_rebought(tmp_path, monkeypatch):
    """A DAY limit that part-fills then expires must NOT re-order the full size."""
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="pending_entry", entry_order_id="E1", qty=10.0,
          limit_price=100.0, stop_price=94.0, target_price=112.0, pending_days=0)
    broker = FakeBroker(orders=[_order2("E1", "AAPL", "buy", "limit", "expired",
                                        qty=10.0, filled_qty=4.0, fill=100.0)])
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(None))
    t = _read(s.run.db_url)
    assert t["status"] == "open"
    assert t["filled_qty"] == 4.0
    assert t["actual_entry"] == 100.0
    assert [o for o in broker.submitted if o.side == "buy"] == []  # no full-size re-buy
    assert "AAPL" in rep.filled_entries


def test_market_fallback_fill_reanchors_stop_and_target(tmp_path, monkeypatch):
    """A fallback fill far above the plan re-bases stop/target at the same R distances."""
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="pending_entry", entry_order_id="E1", qty=2.0,
          limit_price=100.0, stop_price=94.0, target_price=112.0, effective_stop=94.0)
    broker = FakeBroker(orders=[_order2("E1", "AAPL", "buy", "market", "filled",
                                        qty=2.0, filled_qty=2.0, fill=106.0)])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(None))
    t = _read(s.run.db_url)
    assert t["stop_price"] == 100.0      # 106 - 6
    assert t["target_price"] == 118.0    # 106 + 12
    assert t["effective_stop"] == 100.0
    assert t["risk_per_share"] == 6.0


def test_protective_restop_same_day_uses_fresh_coid(tmp_path, monkeypatch):
    """A same-day re-placement must not reuse the canceled stop's client_order_id."""
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="open", qty=1.5, stop_price=80.0, effective_stop=80.0,
          target_price=200.0, entry_fill_date=DAY, actual_entry=100.0, risk_per_share=6.0)
    pos = BrokerPosition("AAPL", 1.5, 100.0, 150.0, 0.0, 100.0)
    broker = FakeBroker(positions=[pos])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(_ohlcv(last_low=99.0, last_high=101.0)))
    # later the same day: tighter, higher bars -> the chandelier ratchets -> re-place
    df2 = _ohlcv(last_low=110.0, last_high=112.0, hi=112.0, lo=109.0, close=111.0)
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(df2))
    stops = [o for o in broker.submitted if o.type == "stop"]
    assert len(stops) == 2
    assert stops[0].client_order_id != stops[1].client_order_id
    assert broker._orders[stops[0].id].status == "canceled"


def test_exit_decision_uses_prior_stop_not_same_bar_ratchet(tmp_path, monkeypatch):
    """Today's ratcheted trail may not claim today's low (mirrors backtest shift(1))."""
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="open", qty=1.5, stop_price=80.0, effective_stop=80.0,
          target_price=200.0, entry_fill_date=DAY, actual_entry=100.0, risk_per_share=6.0)
    pos = BrokerPosition("AAPL", 1.5, 100.0, 150.0, 0.0, 100.0)
    broker = FakeBroker(positions=[pos])
    # Tight range: chandelier ~ 102 - 3*ATR(~4) = 90, ABOVE today's low of 89 -> the
    # pre-ratchet stop (80) must rule: no exit this bar, trail to ~90 for tomorrow.
    df = _ohlcv(last_low=89.0, last_high=101.0)
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    assert rep.exits_submitted == []
    t = _read(s.run.db_url)
    assert t["status"] == "open"
    assert t["effective_stop"] is not None and t["effective_stop"] > 80.0


def test_exit_finalizes_from_stop_fill_when_position_already_gone(tmp_path, monkeypatch):
    """Time-exit wants to sell, but the stop filled in the race window -> no short sell."""
    class RaceBroker(FakeBroker):
        def get_position(self, symbol):
            return None  # flattened between the run-start snapshot and the re-check

    s = _settings(tmp_path)
    _seed(s.run.db_url, status="open", qty=1.5, stop_price=94.0, effective_stop=94.0,
          target_price=200.0, entry_fill_date=date(2024, 1, 2), actual_entry=100.0,
          risk_per_share=6.0, protective_order_id="PS1", filled_qty=1.5)
    pos = BrokerPosition("AAPL", 1.5, 100.0, 141.0, 0.0, 94.0)
    broker = RaceBroker(positions=[pos],
                        orders=[_order2("PS1", "AAPL", "sell", "stop", "filled",
                                        qty=1.5, filled_qty=1.5, fill=93.8)])
    df = _ohlcv(last_low=95.0, last_high=101.0)  # no price exit; ~35 bars -> time exit
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    t = _read(s.run.db_url)
    assert t["status"] == "closed"
    assert t["exit_price"] == 93.8
    assert t["exit_reason"] == "stopped"
    assert [o for o in broker.submitted if o.side == "sell"] == []
    assert "AAPL" in rep.closed


def test_stale_data_skips_price_exits(tmp_path, monkeypatch):
    """Days-old bars must not trigger stop/target decisions."""
    s = _settings(tmp_path)
    _seed(s.run.db_url, status="open", qty=1.5, stop_price=94.0, effective_stop=94.0,
          target_price=112.0, entry_fill_date=DAY, actual_entry=100.0, risk_per_share=6.0)
    pos = BrokerPosition("AAPL", 1.5, 100.0, 141.0, 0.0, 100.0)
    broker = FakeBroker(positions=[pos])
    idx = pd.bdate_range(end="2024-02-09", periods=30)  # 7 business days stale
    df = pd.DataFrame({"open": [100.0] * 30, "high": [101.0] * 30, "low": [90.0] * 30,
                       "close": [100.0] * 30, "volume": [1_000_000] * 30}, index=idx)
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(df))
    assert rep.exits_submitted == []  # low 90 <= stop 94, but the bar is a week old
    assert _read(s.run.db_url)["status"] == "open"


def test_orphan_position_adopted_with_synth_stop(tmp_path, monkeypatch):
    """A live position with no trade row (crash before commit) is adopted + stopped."""
    s = _settings(tmp_path)
    pos = BrokerPosition("MSFT", 3.0, 200.0, 612.0, 12.0, 204.0)
    broker = FakeBroker(positions=[pos])
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(_ohlcv(last_low=203.0, last_high=205.0)))
    assert "MSFT" in rep.orphans_adopted
    t = _read(s.run.db_url, symbol="MSFT")
    assert t["status"] == "open"
    assert t["qty"] == 3.0 and t["actual_entry"] == 200.0
    assert t["entry_order_type"] == "adopted"
    assert t["stop_price"] is not None and t["stop_price"] < 200.0


def test_orphan_swing_buy_order_canceled(tmp_path, monkeypatch):
    """A resting swing-* buy with no trade row would fill into an unmanaged position."""
    s = _settings(tmp_path)
    orphan = _order2("OB1", "NVDA", "buy", "limit", "accepted", qty=2.0,
                     coid="swing-20240220-NVDA-entry")
    broker = FakeBroker(orders=[orphan])
    rep = reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                               loader=FakeLoader(None))
    assert "NVDA" in rep.orphan_orders_canceled
    assert broker._orders["OB1"].status == "canceled"


def test_staged_partial_fill_syncs_real_price(tmp_path, monkeypatch):
    """The provisional theoretical partial price is replaced by the actual fill."""
    s = _staged(tmp_path)
    _seed(s.run.db_url, status="open", order_class="simple", qty=2.0, filled_qty=2.0,
          stop_price=94.0, effective_stop=100.0, target_price=112.0,
          entry_fill_date=date(2024, 2, 13), actual_entry=100.0, risk_per_share=6.0,
          partial_done=True, partial_qty=1.0, partial_fill_price=112.0,
          partial_fill_date=DAY, partial_order_id="P1")
    broker = FakeBroker(
        positions=[BrokerPosition("AAPL", 1.0, 100.0, 105.0, 5.0, 105.0)],
        orders=[_order2("P1", "AAPL", "sell", "market", "filled",
                        qty=1.0, filled_qty=1.0, fill=111.4)])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(_ohlcv(last_low=104.0, last_high=106.0, close=105.0)))
    t = _read(s.run.db_url)
    assert t["partial_fill_price"] == 111.4
    assert t["partial_order_id"] is None
    assert t["partial_done"]


def test_staged_partial_dead_unfilled_rolls_back(tmp_path, monkeypatch):
    """A scale-out that died unfilled re-arms (partial_done back to False)."""
    s = _staged(tmp_path)
    _seed(s.run.db_url, status="open", order_class="simple", qty=2.0, filled_qty=2.0,
          stop_price=94.0, effective_stop=100.0, target_price=112.0,
          entry_fill_date=date(2024, 2, 13), actual_entry=100.0, risk_per_share=6.0,
          partial_done=True, partial_qty=1.0, partial_fill_price=112.0,
          partial_fill_date=DAY, partial_order_id="P1")
    broker = FakeBroker(
        positions=[BrokerPosition("AAPL", 2.0, 100.0, 210.0, 10.0, 105.0)],
        orders=[_order2("P1", "AAPL", "sell", "market", "expired", qty=1.0, filled_qty=0.0)])
    reconcile_and_manage(s, _secrets(monkeypatch), today=DAY, broker=broker,
                         loader=FakeLoader(_ohlcv(last_low=104.0, last_high=106.0, close=105.0)))
    t = _read(s.run.db_url)
    assert not t["partial_done"]
    assert t["partial_qty"] is None and t["partial_fill_price"] is None
    assert t["partial_order_id"] is None
